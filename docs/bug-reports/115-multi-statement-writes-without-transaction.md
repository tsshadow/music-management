# Multi-Statement Writes Without A DELETE Still Ran Without A Transaction

# status: fixed

# reported problem
GitLab issue #85, the follow-up to #31 / [bug report 113](113-parent-child-deletes-without-transaction.md).
The music-manager pool runs with `autocommit=True`, so every statement commits on its own and the
`conn.commit()` at the end of a handler commits nothing. 062 and 113 wrapped every multi-statement
write that deletes. A heuristic scan (every function with two or more INSERT/UPDATE/DELETE
statements and no `transaction(`/`begin()` in its body) listed a second group that deletes nothing.
Each one is assessed below. The question was the same every time: if a failure lands between two
statements, does a user or a later job see a state that no finished write would have left?

## Gaps, now wrapped in `transaction(conn)`

| Where | Statements | What a failure in between left behind |
|---|---|---|
| `routers/management.py` `confirm_label_proposal` (`POST /api/label-proposals/{id}/confirm`, the CAT-ID path) | upsert `rules_catid_label`, then `UPDATE rules_label_proposals SET status = 'confirmed'` | The rule was live and the importer moved the release on its next cycle, but the proposal still read as open. Rejecting it afterwards marked the proposal rejected while the rule it produced stayed in force. |
| `routers/management.py` `rename_podcast` (`POST /api/rules/podcasts/{id}/rename`) | `UPDATE rules_podcasts` (the new name), then `INSERT IGNORE` of the old name as an alias | The show was renamed and its old name no longer matched anything. A retry could not fix it: the row already carries the new name, so the retry keeps *that* name as the alias, and the old spelling is gone for good. |
| `routers/artist_images.py` `select_artist_primary_image`, `_store_manual_image` (URL and upload), both through `_set_primary_image` | clear every `is_primary`, set it on the new image, point `library_artists.primary_image_id` at it (the upload INSERTs the image first) | The manager flagged the new image as primary and hid its "choose" button, while the artist still pointed at the old image everywhere else. With only the first UPDATE done, no image was flagged at all. |
| `routers/artist_images.py` `clear_artist_primary_image` | clear every `is_primary`, then null the pointer and set `image_status = 'cleared'` | No image flagged in the manager, while the artist kept its portrait and its `active` status: the clear had not happened, but the manager no longer showed which image was primary. |
| `artist_image_fetcher/fetcher.py` `_set_primary_image` | the same three UPDATEs | As above on the pooled connection (the router's background fetch). On the CLI's own connection (a plain `pymysql.connect`, autocommit off) the first UPDATEs stayed pending, and the next artist's `commit()` published them. |
| `routers/users.py` `revoke_sessions` (`POST /api/users/{id}/sessions/revoke`) | `UPDATE users SET api_key = NULL`, revoke the refresh tokens, INSERT the `audit_events` row | The api_key was cleared but the refresh tokens still worked, which is half a revocation of a security action. Or everything was revoked and the audit log had no row saying so. |
| `song_version_worker.py` `group_once` (one grouping batch) | `assign_works` (INSERT works, UPDATE `library_tracks.work_id`), `split_false_merges` (new works, moved tracks), `recompute_canonicals` | The tracks had their work but the work's canonical was never chosen: `NULL` on a new work, which LMS reads as "every version is canonical", or the old choice on an existing one, or a canonical pointing at a track that had just been split into another work. Nothing repaired it: the next pass only picks tracks *without* a work, so these works were never selected again. The docstrings already described "one commit per batch", but under autocommit that commit did nothing. |

## Not a gap, left as it is

- `routers/management.py` `save_artist_redirect`: `if`/`else`, so it runs one UPDATE *or* one INSERT,
  never both. The scan counted both branches.
- `routers/users.py` `update_dynamic_playlist`: `if`/`elif`/`elif`, one UPDATE per request. Same
  miscount.
- `routers/artist_images.py` `sync_artist_images_to_server`: this writes the LMS SQLite database, not
  MariaDB, and Python's `sqlite3` already opens a transaction per artist and commits it (the per-artist
  commit from the lock-starvation fix). An artist that fails halfway leaves at most an `image` or
  `artwork` row that nothing points at yet. The next hourly pass looks those rows up by path and by
  image id before it inserts, reuses them, and finishes the pointer. Each statement leaves a table
  that is consistent on its own.
- `song_version_worker.py` `rescore_batch` / `rescore_once`: the per-batch design from bug reports
  100/101 stays. A batch that fails halfway keeps its first UPDATEs, because the pool runs
  autocommit, but every value it writes (kind, score, canonical, the cleared pin,
  `previous_canonical_track_id`) is recomputed from what the batch reads, and the signature stamp is
  the last statement. The works stay selected, and the next tick rewrites the same values and
  stamps them. A canonical that was already moved does not count as "changed" again, so
  `previous_canonical_track_id` is not overwritten. The docstring now says this.
- `song_version_worker.py` `split_work` and `recompute_canonicals` on their own: helpers that take a
  cursor. Their only callers are `group_once` (now one transaction), the song routers' `pin_version`
  and `split_track` (already wrapped in 062), `track_relink` and `orphan_purge` (already
  transactional), and `scripts/repair_song_works.py`, an operator script run by hand. It is outside
  this issue.
- `services/common/Helpers/TrustedArtistHelper.py` `add`: `DatabaseConnector` hands out a plain
  pymysql connection with autocommit off. Both INSERTs therefore already sit in one implicit
  transaction, with `commit()` after them and `rollback()` in the `except`. Even a lone first INSERT
  would be harmless: a bare `library_artists` row is exactly what the scanner writes for every name,
  and it counts as pending, not trusted.
- The fetcher's `_save_image_to_db` followed by `_set_primary_image`: two separate commits. A failure
  in between leaves one more unselected image row, which the manager lists and can select. That is
  the same state as a candidate that was fetched and not chosen.

# Possible reason
062 scoped itself to writes that replace a set, and 113 to writes that delete a parent and its
children. Writes that only INSERT and UPDATE were never assessed. The unit tests could not tell the
difference either: a mocked connection accepts `commit()` whether or not anything was pending.
The song-version worker hid the gap best, because its docstrings promised a per-batch commit that
autocommit turned into a no-op.

# solution
- Each gap runs inside `transaction(conn)` (`services/music_manager/database.py`), and the trailing
  `conn.commit()` is gone. Same statements, same order, same responses.
  - `confirm_label_proposal` wraps only the rule upsert and the verdict. The folder move for a
    proposal without a CAT ID happens before the transaction opens, because a move on disk cannot
    be rolled back. The `stale` early return is a single UPDATE and the `conflict` one writes
    nothing; both stay as they were.
  - The router's `_set_primary_image` is now documented as needing its caller's transaction. The
    file-system follow-ups (`publish_primary`, `unpublish_primary`) still run after the commit, so
    a rolled-back selection publishes nothing.
  - The fetcher uses the same helper on its own connection. On the CLI's non-autocommit connection
    the `BEGIN` commits whatever that connection had pending, which was already committed after
    each step anyway.
  - `group_once` is one transaction per batch, which is what its docstrings already described. The
    batch is at most `SONG_VERSION_BATCH` (500) tracks and the worker is a single thread. Another
    writer of the same rows (the scanner, the relink) waits at most one batch's duration, which is
    seconds. `drain_backlog` still commits between batches.
- Unit tests on `scripted_cursor.transaction_log`. For each path, one test checks that every
  statement ran between one `BEGIN` and one `COMMIT`, and one checks that a failure on the last
  statement produces a `ROLLBACK` and no `COMMIT`:
  `test_management_router.py::ConfirmLabelProposalAtomicityTest` (plus: the folder move happens
  before `BEGIN`), `::RenamePodcastAtomicityTest`,
  `test_artist_images_router.py::PrimaryImageAtomicityTest` (select, clear, upload),
  `artist_image_fetcher/tests/test_fetcher.py::SetPrimaryImageAtomicityTest`,
  `test_users_endpoints.py::RevokeSessionsAtomicityTest` and
  `test_song_version_worker.py::GroupOnceAtomicityTest`. All 17 fail against the old code.
- Integration tests on a real MariaDB, in which the last statement is made to raise inside pymysql:
  `tests/integration/test_router_sql.py::MultiStatementWriteSqlTest` (no CAT-ID rule without its
  verdict, and a retry lands both; the old show name kept; the old primary flag and pointer kept for
  select and for clear; the fetcher on a non-autocommit connection whose later commit publishes
  nothing; the api_key and refresh token still valid) and
  `tests/integration/test_song_version_worker.py::test_a_batch_that_fails_before_its_canonicals_assigns_nothing`
  (no track grouped, no work created, and the next pass leaves no work without a canonical). All 7
  fail against the old code.
- [The db-transactions technical design](../designs/db-transactions/technical.md) lists the writes
  and the verdicts.
