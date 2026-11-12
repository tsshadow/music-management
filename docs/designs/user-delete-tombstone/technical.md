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

LMS learns of a delete from its user sync, not from a direct write: music-manager pokes
`notify_server_sync_users()` after the commit, and LMS fetches `GET /api/users/`. The deleted id is
no longer in the list. No change to the list or the poke.

`applyMumaAccounts` (`services/music-management-server/src/libs/services/auth/impl/musicmanagement/`)
now does this (issue #239):

1. First, every LMS user whose `muma_id` is not listed gets `login_name = deleted-<muma_id>`
   (`tombstoneLoginName`), is disabled and loses its auth tokens, in its own transaction. The row,
   its `muma_id` and everything keyed on the user id stay. The pass is idempotent, so a user
   deleted before this change is renamed on the next sync. The guard is unchanged: an empty list,
   or one with an unreadable id, renames nobody.
2. Then the listed accounts. The name fallback after `findByMumaId` adopts only a user without a
   `muma_id`. A user linked to another id is someone else's (a deleted account the list could not
   prove gone), so the write fails and is counted; the next full list renames the old user and
   creates the new one.

`deleted-<digits>` is reserved in music-manager, so no listed account collides with a tombstone.
Every name is unique in LMS (`user_login_name_nocase_unique_idx`); a local LMS user already called
`deleted-<id>` makes the rename fail and is logged.

The renamed user's listens reach music-manager under `deleted-<id>`: `scrobble_reconcile.py` reads
`user.login_name` from `lms.db`, which matches where step 1 above moved the history.
`subsonic_token.py` looks a caller up by `muma_id` first and falls back to the name only when no row
has the id, so a new account no longer resolves to the old LMS user by name.

Tests: `src/libs/services/auth/test/MumaUserSync.cpp` (delete and make the name again in one sync
and in two, a backlog user, an incomplete list that must not hand the user over).

## Technical Acceptance Criteria

1. Unit: each of the six tables gets `SET username = 'deleted-4'` for user 4, inside the delete's
   transaction; a failing `DELETE FROM users` rolls the renames back.
2. Integration (`UserLifecycleTest`): delete "user", make "user" again, find no row under "user" in
   the six tables and one row under `deleted-<id>` in each.
3. `username_taken` is true for `deleted-12` and `Deleted-12`, false for `deleted-anna`.

## Related Docs

- [authentication.md](../../authentication.md)
- [db-transactions](../db-transactions/technical.md)
