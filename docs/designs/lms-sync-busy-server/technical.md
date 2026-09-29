# lms.db sync against a busy server — Technical Design

Implements [functional.md](functional.md). Evidence and history: bug report 129.

## Data Model

None. The same LMS `track` columns are written (`work_id`, `is_canonical`, `version_kind`,
`version_score`, `form`, `performance_date`); only how and when changes.

## API Contract

No endpoint changes. `POST /api/users/sync/muma-server` behaves as before; rows it defers stay in
memory until the next hourly tick recomputes them.

Internal Python contract:

| Function | Change |
|---|---|
| `song_version_sync.sync_song_versions_to_server(..., deferred=None)` | New keyword. Rows refused by a busy server are appended to `deferred` as one `PendingWrites`; `stats['deferred']` counts them. `stats['chunks_skipped']` is gone. |
| `track_form_sync.push_forms_to_server(..., deferred=None)` | Same. |
| `lms_writes.PendingWrites(update_sql)` | `write(conn, cursor, rows)` writes in `WRITE_BATCH` transactions, each opened with `BEGIN IMMEDIATE`; after the first lock refusal it only collects. `retry(conn)` tries the leftovers once more. Non-lock errors are raised. |
| `routers.users.run_lms_db_sync_with_retry(..., deferred_attempts=5, deferred_delay_seconds=300)` | After the unmigrated-server retry, calls `_retry_deferred_writes`. |

## Cross-App Impact

None. LMS is not changed; the columns and their meaning are unchanged.

## Technical Acceptance Criteria

1. Every write transaction into `lms.db` starts with `BEGIN IMMEDIATE` and holds at most
   `WRITE_BATCH` (100) UPDATEs.
2. `PRAGMA busy_timeout` for these writes is 10 s, spelled as a literal statement that a test keeps
   equal to `BUSY_TIMEOUT_MS`.
3. After the first batch refused with "locked"/"busy", no further transaction is opened in that
   pass; every unwritten row is in `PendingWrites.rows`.
4. `_retry_deferred_writes` sleeps `delay + randbelow(61)` seconds before each of at most
   `attempts` tries, opens a fresh connection per server per try, logs one INFO when everything
   landed and exactly one WARNING when rows remain after the last try, then clears the list.
5. `run_lms_db_sync` discards the deferred rows of every server it syncs before syncing it.
6. A transaction left open on the connection after the artist-image sync is rolled back before
   the pushes run.
7. No per-batch WARNING remains in either push.

## Related Docs

- [docs/bug-reports/129-lms-sync-gives-up-on-a-scanning-server.md](../../bug-reports/129-lms-sync-gives-up-on-a-scanning-server.md)
- [docs/designs/song-versions-lms-canonical/](../song-versions-lms-canonical/)
- [docs/designs/track-form/](../track-form/)
