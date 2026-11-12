# User Delete Tombstone — Technical Design

Implements [functional.md](functional.md). Code: `delete_user_row` in
`services/music_manager/routers/users.py` and `services/music_manager/identity.py`.

## Data Model

No schema change. The username-keyed tables are listed once, in
`identity.USERNAME_KEYED_TABLES`: `rating_tracks`, `scrobble_listens`,
`scrobble_unmatched_listens`, `scrobble_imports`, `feeds_snapshot` and `feeds_profile_exclusions`.
Every other per-account table is keyed by `users.id` and was already deleted.

`delete_user_row` runs one `UPDATE <table> SET username = 'deleted-<id>' WHERE username = <name>`
per table before `DELETE FROM users`. Both callers (`DELETE /api/users/{id}` and the unapprove of a
user request) hold `transaction(conn)`, so the renames and the delete commit together or roll back
together. The comparison uses the column collation (case-insensitive), the same as
`users.username`.

The tombstone name is unique per account id, so the renames cannot hit a unique key.
`username_taken` answers true for any name that matches `deleted-<digits>` in any case, so no
account can take a tombstone name and inherit its rows. The audit row `user.deleted` records
`history_moved_to=deleted-<id>`.

## API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `DELETE /api/users/{user_id}` | unchanged | unchanged | unchanged |
| `POST /api/users` | unchanged | unchanged | new: 409 for a `deleted-<digits>` name |
| `POST /api/user-requests/{id}/approve` | unchanged | unchanged | new: 409 when the e-mail is a `deleted-<digits>` name |

Not a breaking change: the new 409 is the existing "name taken" answer.

## Cross-App Impact

None. LMS keeps its own disabled user (issue #239).

## Technical Acceptance Criteria

1. Unit: each of the six tables gets `SET username = 'deleted-4'` for user 4, inside the delete's
   transaction; a failing `DELETE FROM users` rolls the renames back.
2. Integration (`UserLifecycleTest`): delete "user", make "user" again, find no row under "user" in
   the six tables and one row under `deleted-<id>` in each.
3. `username_taken` is true for `deleted-12` and `Deleted-12`, false for `deleted-anna`.

## Related Docs

- [authentication.md](../../authentication.md)
- [db-transactions](../db-transactions/technical.md)
