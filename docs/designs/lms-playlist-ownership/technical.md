# LMS Playlist Ownership — Technical Design

Implements [functional.md](functional.md). Code: `_sync_server_playlists` in
`services/music_manager/routers/users.py`, called by `sync_single_server_db` for each LMS database
in the hourly `lms-db-sync` loop and by `POST /api/users/sync/muma-server`.

## Data Model

No schema change. `dynamic_playlists` is unique on `(source, remote_id)`. `source` is the name of
the LMS database, `remote_id` is `tracklist.id` in LMS. Rows that music-manager made itself have
`remote_id` NULL and the sync never selects them.

One pass, all inside one `transaction(conn)`:

1. Read the smart playlists from LMS: `SELECT id, user_id, name, smart_params FROM tracklist WHERE
   type = 2`.
2. Map LMS user ids to music-manager accounts with one query on `users.server_user_id`.
3. Upsert each playlist whose owner has an account. `ON DUPLICATE KEY UPDATE` writes `user_id`,
   `name` and `params`, so an owner change in LMS moves the row.
4. Delete the rows of this `source` with a `remote_id` that LMS no longer has.

A playlist whose LMS owner has no account counts as present: its row is not deleted and not
changed. A pass that raises rolls back and logs `WARNING` "Playlist sync failed for <source>" on
the module logger, which the event stream captures. An LMS database without
`tracklist.smart_params` is skipped before the transaction.

## API Contract

No endpoint changes.

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `POST /api/users/sync/muma-server` | unchanged | unchanged | unchanged |

## Cross-App Impact

None. LMS is read only.

## Technical Acceptance Criteria

1. The upsert writes `user_id` on a duplicate key (`test_an_owner_change_on_the_server_moves_the_playlist`).
2. A row whose `remote_id` LMS no longer has is deleted, a row LMS has is kept.
3. The upserts and the delete run between one BEGIN and one COMMIT (`transaction_log`).
4. A failure rolls back and logs a WARNING, and the sync of the other data goes on.

## Related Docs

- [db-transactions](../db-transactions/technical.md)
