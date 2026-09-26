# Parent-Then-Children Deletes Still Ran Without A Transaction

# status: fixed

# reported problem
GitLab issue #31, left over from [bug report 062](062-delete-then-insert-not-atomic.md). The
music-manager pool runs with `autocommit=True`, so every statement commits on its own. 062 wrapped
every delete-then-insert in `database.transaction(conn)` but deliberately left the writes that
remove a parent and its children in sequence with no INSERT after them, on the grounds that a
failure half-way leaves an orphan rather than an empty set. The artist-curation `decide` and `undo`
were wrapped later ([bug report 080](080-artist-redirect-chains-and-portrait-reset.md)).

A sweep of every `DELETE` and every function with two or more writes under `services/` found three
multi-statement deletes still outside a transaction (line numbers after the fix):

| Where | Statements | What a failure in between left behind |
|---|---|---|
| `services/music_manager/routers/news.py:694-695` `delete_source` (`DELETE /api/news/sources/{slug}`) | `DELETE FROM news_bulletins` then `DELETE FROM news_sources` | A source that still records every hour but whose older bulletins are gone from the list, with their audio files still on disk and nothing left to ever prune them. |
| `services/music_manager/routers/radio.py:399-400` `delete_channel` (`DELETE /api/radio/channels/{slug}`) | `DELETE FROM radio_timeline` then `DELETE FROM radio_channels` | A channel that stays on air with its history wiped. |
| `services/music_manager/routers/management.py:820-830` `decide_podcast` merge branch (`POST /api/rules/podcasts/{id}/decide` with `merge_into_podcast_id`) | `INSERT IGNORE INTO rules_podcast_aliases` (keep the name), `UPDATE rules_podcast_aliases` (move the spellings), `DELETE FROM rules_podcasts` | The merged-away show still in the queue with none of its spellings, which already belong to the target: a later decision on it would apply to a show that matches nothing but its own name. |

The request answered 500 in each case, so the curator would retry and the retry would mostly
finish the job -- but the half-done state was visible to every reader in the meantime, and a
retry after the first case found no files to remove.

Checked and **not** a gap:
- Already in a transaction: `scanner.process_file` (including `_write_genres`, `_write_links` and
  the relink), `track_relink.relink_orphaned_tracks`, `orphan_purge.purge_batch`,
  `scrobble_rematch`, `scrobble_reconcile`, `users.delete_user`/`merge_users`,
  `user_requests.approve`/`unapprove`, `festivals.create`/`update`, `curation.set_genre_parents`
  and the external-id writes, `management.decide_genre`, both proposal analyses, and
  `artist_curation.decide`/`undo`.
- Single statement: `festivals.delete_festival` (children go by `ON DELETE CASCADE`, which is atomic
  with the parent), `management.delete_youtube_account` (one of two DELETEs, never both), the
  alias, catalogue-number, genre-rule, redirect, playlist, event and rating deletes, and the
  importer/tagger helper deletes.
- Independent statements, where each one leaves a consistent table on its own:
  `news.prune_bulletins` (one bulletin row per statement, file first), `radio.fill_channel` (append
  the next entries, then trim old history), `rbac.purge_refresh_tokens` and
  `rbac.issue_refresh_token` (a missed prune is repeated by the next login or the daily run),
  `feeds.update_exclusion` (the snapshot purge after it is a cache invalidation), and the batched
  `events_retention` delete.

None of the three is large: a news source keeps at most its `retention_count` bulletins, a radio
timeline holds a few hours of entries, and a show has a handful of spellings. One transaction each
holds its row locks for milliseconds, so no batching was needed.

# Possible reason
Bug report 062 scoped itself to writes that replace a set, where the failure mode is an empty
table. Parent-then-children deletes were judged benign and left for "when next touched"; nothing
in the unit tests tells a multi-statement write from a single one, since the mocked connection
accepts `commit()` either way.

# solution
- Each of the three runs inside `transaction(conn)` (`services/music_manager/database.py`):
  `BEGIN` before the first statement, `COMMIT` after the last, `ROLLBACK` on any exception -- the
  404 for an unknown news source or radio channel included, which rolls back an empty transaction.
  The trailing `conn.commit()` went, since the helper commits. Nothing else changed: same
  statements, same order, same responses; the news files are still removed only after the commit,
  so a rolled-back delete now keeps both its rows and its recordings, and a retry removes them.
- Unit tests, on `tests/scripted_cursor.transaction_log`: for each path one test that every
  statement ran between one `BEGIN` and one `COMMIT`, and one that a failure injected on the last
  DELETE produces a `ROLLBACK` and no `COMMIT` (`test_news.py::NewsManagementTest`,
  `test_radio.py::ChannelAdminTest`, `test_management_router.py::DecidePodcastMergeAtomicityTest`).
  All of them fail against the old code.
- Integration tests on a real MariaDB (`tests/integration/test_router_sql.py`,
  `NewsSqlTest::test_a_failing_source_delete_keeps_the_bulletin_rows` and
  `ParentChildDeleteSqlTest`): the last DELETE is made to raise inside pymysql, and the bulletin
  rows and file, the radio timeline, and the podcast spellings are all still in place afterwards.
- The table in [the db-transactions technical design](../designs/db-transactions/technical.md)
  lists the three writes.
- Multi-statement writes that delete nothing (several two- and three-statement UPDATE/INSERT
  sequences) were out of scope for this issue and are tracked in GitLab issue #85.
