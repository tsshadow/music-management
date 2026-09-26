# Explicit Transactions For Multi-Statement Writes — Technical Design

> A fix to existing flows, not a new feature, so there is no separate `functional.md`: nothing a user
> sees changes except that a failed write no longer leaves a table half-written. Background and the
> list of affected writes: [bug report 062](../../bug-reports/062-delete-then-insert-not-atomic.md).

## Data Model

No table or column changes. What changes is how existing writes reach MariaDB.

The music-manager pool (`services/music_manager/database.py`) is a DBUtils `PooledDB` over `pymysql`
with `autocommit=True`. That default stays: most writes are a single statement, and autocommit is
what they rely on. Under autocommit every statement commits on its own, so the `conn.commit()` that
ends many handlers commits nothing extra, and a DELETE followed by the INSERTs that replace it is
two separate, independently visible changes.

`database.transaction(conn)` is a context manager for writes that must land together:

```python
with transaction(conn), conn.cursor() as cursor:
    cursor.execute('DELETE FROM t WHERE owner = %s', (owner,))
    for value in values:
        cursor.execute('INSERT INTO t (owner, value) VALUES (%s, %s)', (owner, value))
```

- `conn.begin()` on entry. DBUtils' `SteadyDBConnection.begin()` marks the connection as in a
  transaction and forwards to `pymysql.Connection.begin()`, which sends `BEGIN`. On MariaDB an
  explicit `BEGIN` suspends autocommit until the matching `COMMIT`/`ROLLBACK`; afterwards the session
  is back in autocommit mode.
- `conn.commit()` when the block finishes, `return` inside the block included.
- `conn.rollback()` when the block raises anything (`HTTPException` for a 404 half-way included), and
  the original exception is re-raised. A failing rollback is logged at `WARNING` and does not replace
  the original exception.
- A failing `commit()` propagates without a rollback: DBUtils already tries to reconnect, and the
  connection is reset on its way back to the pool either way.
- A connection closed with a transaction still open — a crash path that skips the context manager —
  is rolled back by DBUtils when it returns to the pool (`PooledDB(reset=True)`, the default, calls
  `_reset()`, which rolls back any transaction started with `begin()`).

Every statement inside the block must run on the same `conn`. A second connection neither sees the
uncommitted rows nor takes part in the transaction.

## Writes wrapped

Delete-then-insert (the audit's finding C1):

| Where | What is replaced |
|---|---|
| `routers/curation.py` `set_genre_parents` | `rules_subgenre_hierarchy` rows of one genre |
| `routers/curation.py` `set_artist_mbid`, `set_artist_external_id` | `library_artists.mbid` + `artist_external_ids` row |
| `routers/curation.py` `set_label_mbid`, `set_label_external_id` | `library_labels.mbid` + `label_external_ids` row |
| `routers/festivals.py` `create_festival`, `update_festival` | festival row + `rules_festival_aliases` + `rules_festival_editions` |
| `routers/genre_curation.py` `_run_analysis` | all of `rules_genre_proposals` |
| `routers/artist_curation.py` `_run_analysis` | all of `rules_artist_proposals` |
| `routers/management.py` `decide_genre` | `rules_genres` decision + `rules_genre_expansions` |
| `routers/scanner.py` `process_file` | a track's artist, genre, label and channel links, its media-file row, and the relink of the row a retagged file left |
| `scrobble_rematch.py` `rematch_once` | one listen: INSERT into `scrobble_listens`, DELETE from `scrobble_unmatched_listens` (one transaction per listen, as before one commit per listen) |

Other multi-statement writes named by the audit, where a partial write leaves inconsistent data:

| Where | What lands together |
|---|---|
| `routers/user_requests.py` `approve_user_request` | new user + identity + request status + audit row |
| `routers/user_requests.py` `unapprove_user_request` | account or identity removal + request back to pending |
| `routers/users.py` `delete_user` | dependent rows + user row + audit row |
| `routers/users.py` `merge_users` | every moved/deleted row + secondary account delete |
| `routers/songs.py` `pin_version`, `split_track` | pin/new work + track move + canonical recompute |

Parent-then-children deletes, added by [bug report 113](../../bug-reports/113-parent-child-deletes-without-transaction.md)
(062 had left them out because a failure half-way leaves an orphan rather than an empty set):

| Where | What lands together |
|---|---|
| `routers/news.py` `delete_source` | a source's bulletin rows + the source row (the audio files go after the commit) |
| `routers/radio.py` `delete_channel` | a channel's timeline + the channel row |
| `routers/management.py` `decide_podcast` (merge) | the kept name as alias + the moved spellings + the merged-away show row |

Multi-statement writes that delete nothing, added by [bug report 115](../../bug-reports/115-multi-statement-writes-without-transaction.md)
(GitLab issue #85). Each one was checked for whether a failure between its statements leaves a
state that a reader, or a later job, would misread:

| Where | What lands together |
|---|---|
| `routers/management.py` `confirm_label_proposal` | the `rules_catid_label` rule + the proposal's `confirmed` verdict (the folder move for a proposal without a CAT ID runs before the transaction, since a move on disk cannot be rolled back) |
| `routers/management.py` `rename_podcast` | the new show name + the old name kept as an alias |
| `routers/artist_images.py` `select_artist_primary_image`, `_store_manual_image` | (the new image row +) the `is_primary` flags + `library_artists.primary_image_id` |
| `routers/artist_images.py` `clear_artist_primary_image` | the cleared flags + the nulled pointer and `cleared` status |
| `artist_image_fetcher/fetcher.py` `_set_primary_image` | the flags + the pointer, on the fetcher's own connection (pooled from the router, plain pymysql with autocommit off from the CLI) |
| `routers/users.py` `revoke_sessions` | the cleared api_key + the revoked refresh tokens + the audit row |
| `song_version_worker.py` `group_once` | one grouping batch: work assignment, automatic splits and canonical recompute. `drain_backlog` still commits between batches |

Assessed and left alone, with the reasons in bug report 115: `save_artist_redirect` and
`update_dynamic_playlist` (branches, one statement per request), `sync_artist_images_to_server`
(SQLite, already one transaction per artist, and the next pass reuses any leftover row),
`rescore_batch` (every value is recomputed from what the batch reads and the signature stamp comes
last, so a partial batch is redone by the next tick; the per-batch design of bug reports 100/101
stays), and `TrustedArtistHelper.add` (a non-autocommit connection that already commits or rolls
back both INSERTs together).

The artist-curation `decide` and `undo` got theirs in [bug report 080](../../bug-reports/080-artist-redirect-chains-and-portrait-reset.md).

`scanner.process_file` used to open a transaction only when a file moved to a new track row. It now
always opens one, spanning the link rewrites, the media-file upsert and (when moving) the relink. The
`library_artists` and `library_tracks` upserts before it stay outside: they are idempotent single
statements. `_write_links` reads the track's other files from disk inside the transaction, so the
row locks on that one track's link rows are held for the length of those reads; the scanner is
serialised by its own lock, so no scanner write waits on another.

`decide_genre` marks files for a retag after the commit, as before.

No write ran across two connections; nothing needed moving onto one.

## API Contract

No endpoint changes. Responses are identical; the only observable difference is on failure: a
request that fails after its DELETE now leaves the previous rows in place instead of an empty or
half-written set.

## Cross-App Impact

None. music-manager only.

## Technical Acceptance Criteria

1. `transaction(conn)` calls `begin` before the block and `commit` after it; on an exception it calls
   `rollback`, re-raises the same exception object, and never calls `commit`
   (`services/music_manager/tests/test_database_transaction.py`).
2. Each wrapped write runs its DELETE and INSERTs between one `BEGIN` and one `COMMIT`, and a failure
   injected after the DELETE produces a `ROLLBACK` and no `COMMIT` (the `*AtomicityTest` classes in
   the router test modules, built on `tests/scripted_cursor.transaction_log`).
3. Against a real MariaDB, a DELETE inside `transaction()` followed by an exception leaves every row
   in place, and a second connection still sees them mid-transaction
   (`tests/integration/test_router_sql.py::TransactionTest`).
4. A pooled connection handed back after a rollback reports `@@autocommit = 1` and
   `@@in_transaction = 0`, and a connection closed mid-transaction is rolled back by the pool (same
   class).
5. End to end: a festival update whose alias INSERT is refused by MariaDB (an alias longer than the
   column) keeps both the old name and the old alias (same class).
6. For each write of bug report 115, a failure raised inside pymysql on its last statement leaves
   the earlier statements unapplied on MariaDB (`tests/integration/test_router_sql.py::MultiStatementWriteSqlTest`,
   and `tests/integration/test_song_version_worker.py::test_a_batch_that_fails_before_its_canonicals_assigns_nothing`
   for the grouping batch).

## Related Docs

- [Bug report 062](../../bug-reports/062-delete-then-insert-not-atomic.md)
- [Bug report 113](../../bug-reports/113-parent-child-deletes-without-transaction.md) and
  [bug report 115](../../bug-reports/115-multi-statement-writes-without-transaction.md)
- [Bug report 042](../../bug-reports/042-retag-orphans-ratings-and-listens.md) — where the scanner's
  move transaction came from.
