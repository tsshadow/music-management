# The Last Admin Could Demote Itself

# status: fixed

# reported problem
A follow-up to the September 2026 authentication audit (bug report 037 and !916/!934) found six
smaller gaps in `services/music_manager`, all still present at 0.72.2:

1. **No last-admin protection on demote and disable.** `DELETE /api/users/{id}` refused to delete
   the last admin, but `PUT /api/users/{id}/role` with `{"role": "user"}` and
   `POST /api/users/{id}/disable` changed the only admin without a check. Either leaves an
   installation where nobody holds `users.assign-role`, and the only way back is SQL on the
   production database. The delete check itself counted *every* admin row, disabled ones included,
   so a disabled second admin let the last usable one be deleted.
2. **The first-time setup could create two admins.** `POST /api/auth/setup` is unauthenticated while
   the users table is empty. It ran `SELECT COUNT(*)` and then `INSERT` with nothing in between, so two
   requests arriving together could both see zero and both create an admin account.
3. **Login timing revealed which usernames exist.** An unknown username was answered with `401` right
   after the lookup; an existing one first ran bcrypt (cost 12, roughly 250 ms). The text was the
   same, the time was not. A disabled account also answered `403 Account disabled` before its password
   was checked, confirming the name to anyone.
4. **A database outage read as a bad key.** `routers/library.py` and `routers/scrobbler.py` still had
   their own `verify_api_key`, wrapping `verify_token` in `except Exception: pass` and answering
   `401 Invalid API key`. A disabled account got 401 there and 403 everywhere else; a MariaDB outage
   told every client its key was wrong. `verify_token` itself answered `403 Invalid API Key` when the
   pool could not be created and let a connection error escape as a 500.
5. **Any account could scrobble into another account's history.** `POST /api/scrobble/event` stored
   the listen under the body's `username` for any valid key. Listens feed the listener's statistics,
   daily mixes and release radar.
6. **`user_refresh_tokens` grew without bound.** Every successful login inserted a row and nothing ever
   removed one -- not revocation (it only stamps `revoked_at`), not expiry (there is none). LMS
   validates Subsonic passwords through `/api/auth/login` whenever its five-minute cache lapses, so
   the table grew by a row per listener every few minutes of listening.

# Possible reason
Each of these is a check written for one path and not the others. The last-admin guard was added to
delete when the delete endpoint was hardened and never extracted, so the two later-written ways to
remove an admin did not get it. The setup endpoint was written as a straight-line "is it empty, then
insert", which is only safe single-threaded. The login early return was written for clarity, not
timing. The two router-local key checks are the remainder of the copies bug report 037 and !916
replaced elsewhere; they predate the 503 handling for `DatabaseBusyError`. The scrobble endpoint was
written when LMS, with the system key, was its only caller. Refresh tokens were introduced for the
mobile client without a housekeeping step.

# solution
- **Last admin** (`routers/users.py`): one check, `ensure_not_last_enabled_admin(cursor, target,
  action)`, used by delete, demote (any role but `admin`) and disable. It returns early for a target
  that is not an enabled admin, and otherwise counts admins with `enabled = TRUE AND id <> target`;
  zero means 409 with a Dutch detail naming the action ("Kan de laatste actieve beheerder niet
  ..."). The check and the write run under `_admin_guard_lock`. Delete's refusal moves from 400 to 409.
  Disable and demote of an unknown id now answer 404 instead of a silent `ok`.
- **Setup**: validation and bcrypt run first; then under `_setup_lock` the COUNT is repeated and the
  insert is `INSERT ... SELECT ... FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM users)`, so a second
  process that the lock cannot see still inserts nothing. `rowcount == 0` and a non-empty COUNT both
  answer `409 Setup already completed` (was 400).
- **Login**: `password_matches` runs one bcrypt check against a cost-12 dummy hash
  (`timing_dummy_hash()`, made once from random bytes, belonging to no account) whenever the account has
  no hash of its own -- an unknown username or a Google-only account. Login calls it with an empty row
  for an unknown user and answers the same `401 Invalid username or password`. The disabled check
  moved after the password check.
- **Key checks**: `library.verify_api_key` and `scrobbler.verify_api_key` delegate to
  `users.verify_api_key`, like every other router. `verify_token` answers `503 Authentication database
  unavailable` (`Retry-After: 5`) when there is no pool, the connection fails or the lookup fails.
  `users.verify_api_key` answers `401` for a key no account holds and `403` only for a disabled
  account: `tests/bdd/features/access_control.feature` requires 401 for an invalid key on the library,
  and a uniform check means every router answers the same. `GET /api/auth/verify` keeps its 403.
  `tests/integration/conftest.py` now also patches `curation`, `downloaders`, `feeds` and `songs`,
  which import `get_db_connection` by value and were missing from its list.
- **Scrobbles**: `POST /api/scrobble/event` uses the ListenBrainz import's rule (renamed
  `_may_write_history_for`): a user key may name only itself (403), admins and the system key anyone.
- **Refresh tokens** (`rbac.py`): `issue_refresh_token` inserts and then deletes that account's rows
  older than its 10th newest (`REFRESH_TOKENS_PER_USER`); both login paths use it.
  `purge_refresh_tokens`, called from the daily `events-retention` tick, applies the same cap to every
  account with a `ROW_NUMBER()` window and removes revoked rows older than 30 days. Both statements
  wrap their subquery in a derived table, which MariaDB needs for a LIMIT subquery on the table being
  deleted from.
- **Tests**: `services/music_manager/tests/test_auth_polish.py` (one class per gap; the setup race
  test runs two threads against a shared fake table and fails without the lock), plus
  `UserLifecycleTest` cases in `tests/integration/test_router_sql.py` that run the guarded INSERT,
  the admin count and both prune statements against MariaDB.
- **Not changed, for a decision** (also in `docs/open-work.md`): `GET /api/scrobble/import/latest`
  (and its `/api` twin in `management.py`) lists every account's last ten ListenBrainz imports --
  username, ListenBrainz name, status, error text -- to any account; and `DELETE /api/users/{id}`
  lets a plain account delete itself. Every other route that takes a `username` or user id was
  checked and is self-or-privileged: feeds and listening pin a user key to its own account, the
  ratings read is self-or-admin, the rating webhook is system-key only, the ListenBrainz import is
  self-or-admin, and the `/api/users/{id}/...` routes are self or `users.update`/`users.read`.
