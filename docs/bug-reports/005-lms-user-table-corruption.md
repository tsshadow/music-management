# LMS "user" Table Corruption / Login Outage (`no such column: u.password_salt`)

# status: fixed

# reported problem
Production went down: every request touching the player's own `user` table (including
username/password login and delegated Google auth) crashed with:

```
Sqlite3: SELECT ... from user u where (u.login_name = ?): no such column: u.password_salt
```

# Possible reason
Two independent, compounding bugs, both surfaced by an earlier, unrelated fix (release 0.0.16)
that made `music-manager`'s Docker volumes point at the *real* production `lms`/`alpha-lms`
SQLite database files (previously they pointed at a path that never existed, so this code was
silently a no-op):

1. `sync_single_server_db()` (`services/music_manager/routers/users.py`) ran
   `DROP TABLE IF EXISTS user, auth_token, ui_state` directly against that on-disk database file,
   based on an incorrect comment claiming all three tables are purely volatile/in-memory
   server-side state. That is only true for `auth_token`/`ui_state`, which live in the player's
   *private* `ATTACH DATABASE 'file::memory:...' AS volatile` schema (so dropping them through an
   external on-disk connection was always a harmless no-op) — but `user` is a real, persistent,
   non-volatile table (`services/music-management-server/.../database/objects/User.hpp`) that the
   running player process reads/writes directly. Dropping it out from under the live process,
   right as it was also restarting/initializing its own schema, caused a race.
2. `Session::createIndexesIfNeeded()` (`services/music-management-server/.../Session.cpp`) has its
   own raw-SQL `CREATE TABLE IF NOT EXISTS user (...)` fallback that is normally a no-op (the ORM's
   `prepareTablesIfNeeded()` already creates the table first) — but it was missing the
   `password_salt`/`password_hash` legacy columns that `User::persist()` unconditionally reads and
   writes. When the table above got dropped mid-startup, this fallback ran instead and recreated
   `user` with an incomplete/incompatible schema (0 rows, missing both columns), which the running
   binary's compiled queries could no longer satisfy.

# solution
1. Removed the destructive `DROP TABLE` loop from `sync_single_server_db()` entirely — this sync
   never wrote users into that table anyway (`_sync_server_users()` is a no-op by design; users are
   delegated-auth-synced by the player's own `UserSynchronizer`), so the drop served no purpose.
2. Added the missing `password_salt`/`password_hash` columns (with safe `DEFAULT ''`) to the raw
   SQL fallback in `createIndexesIfNeeded()`, matching `User::persist()`.
3. **Production repair** (already applied directly, ahead of the code fix, to restore service):
   stopped the `lms` container, added the missing `password_salt`/`password_hash` columns
   (`DEFAULT ''`) to the live `user` table via `ALTER TABLE`, and restarted `lms` — confirmed clean
   startup logs and a successful login end-to-end. The `alpha-lms` `user` table had been fully
   dropped with no `alpha-lms` container currently running to recreate it; left alone, since the
   next `alpha-lms` startup will recreate it correctly via `prepareTablesIfNeeded()` now that the
   destructive drop is removed.
