# A login typed in another case forked the account into a second LMS user

# status: fixed

# reported problem

On 2026-09-25, a few hours after 0.73.1 went live, production held two identities for one
person (all measured read-only):

- MuMa `users` has one account: id 1, `user`.
- LMS `stable/lms.db` `user` has two: id 1 `user` (type 1, admin) and id 13 `Teun` (type 0).
  LMS listens: `Teun` 31, all today, the last at 06:18 UTC; `user` 4172, the last on
  2026-09-24 17:47.
- MuMa `scrobble_listens` rows since 2026-09-25 05:05 UTC are all stored as `Teun` (sources
  `mobile` and `auto`); every row before that says `user`.

MuMa's MariaDB collation (`utf8mb4_general_ci`) is case-insensitive, so SQL `=` still finds
both spellings. LMS does not, and neither does anything that groups by username in Python
(the reconcile's per-user split, the relink of ratings, the daily-mix seed).

0.73.1 (~04:55 UTC) contained MR !941, and every web and app session had to sign in again
after the per-account key rotation. The phone was signed in as `Teun`.

# Possible reason

The typed spelling travelled unchanged through every hop, and the one hop that compares
names byte for byte created a user for it. The chain, with the lines as they were on
`develop` at e279a452d:

1. The login screen and the Android shell's boot login both go through `signIn()`
   (`services/frontend/src/lib/login.js:54`). It pings LMS first with the typed pair as
   Subsonic `u=`/`p=` (`login.js:57`, via `subsonicAuthQuery`, `login.js:40`), then stores
   the typed name as the session's username (`login.js:74`). `LoginPage.svelte:58` writes
   the same typed pair to the phone (`ActiveServerProvider.saveCredentials`), and
   `nativeSession.js:95` re-signs in with it on every boot. The native player, Android Auto
   and downloads sign every Subsonic call with that stored name.
2. LMS authenticates `u=Teun` in `SubsonicResource::authenticateUser`
   (`services/music-management-server/src/libs/subsonic/impl/SubsonicResource.cpp:618`) by
   asking the password service, which for this deployment is
   `MusicManagementPasswordService`: it posts the typed name to MuMa's `/api/auth/login`
   (`MusicManagementPasswordService.cpp:112`).
3. MuMa looks the account up with `WHERE username = %s`
   (`services/music_manager/routers/users.py:364`). Under `utf8mb4_general_ci` "Teun" equals
   "user", the password matches, and MuMa answers 200. The answer carries the account's own
   spelling under `user.username`, but LMS only reads the status code.
4. On a match `PasswordServiceBase::checkUserPassword` calls `getOrCreateUser(loginName)`
   with the *typed* name (`PasswordServiceBase.cpp:99`). `AuthServiceBase::getOrCreateUser`
   looks it up with `User::find(session, loginName)` (`AuthServiceBase.cpp:44`, again at
   `:51`), which is `WHERE u.login_name = ?` on SQLite, BINARY collation
   (`database/impl/objects/User.cpp:101`). "Teun" finds nobody, so LMS creates user 13
   (`AuthServiceBase.cpp:58`), `REGULAR` because it is not the first user, with no
   `muma_id`. That matches what production shows: type 0, created this morning.
5. From then on every Subsonic request signed `u=Teun` resolves to user 13. The phone's plays
   are recorded as user 13's listens, and `MusicManagementBackend::sendScrobble` relays each
   one to MuMa's `/api/scrobble/event` with `username = user->getLoginName()`, "Teun"
   (`scrobbling/impl/musicmanagement/MusicManagementBackend.cpp:89`), using the system key.
6. The scrobble endpoint stores the body's `username` verbatim
   (`services/music_manager/routers/scrobbler.py:139` matched, `:156` unmatched). !938's
   self-only rule (`scrobbler.py:120`, comparing exactly at `:340`) does not apply to the
   system key. A user key naming `Teun` would even have been refused, which is how we know
   these rows came through LMS.

Not the cause: MuMa's own LMS user sync. `UserSynchronizer` only creates users from MuMa's
list, which has `user`, and it finds users by `muma_id` first. `lms_db_sync` never writes the
`user` table. The `/muma/api/auth/login` route that !941 sends straight to MuMa creates no
LMS user either. Only the Subsonic password path calls `getOrCreateUser`.

# solution

The rule is now that account names are case-insensitive everywhere and the one spelling is
MuMa's `users.username` (`docs/authentication.md`, "Account names are case-insensitive").

- **LMS never forks again.** `User::find(session, loginName)` compares with `COLLATE NOCASE`
  and prefers the MuMa-linked user, then the oldest (`LIMIT 1`, so an existing fork cannot
  make it throw). Every name-based lookup goes through it: authentication, Subsonic token
  auth, `UserSynchronizer`, the `/muma` target user, and Subsonic `createUser`/the admin UI.
  The last two therefore refuse a case variant of an existing user. With the fix deployed,
  a login typed `Teun` lands on user 1 even before the data is repaired. Tests:
  `DatabaseFixture.User_findByLoginName*` and `CaseInsensitiveLogin.*` (C++).
- **MuMa login** matches with `LOWER(username) = LOWER(%s)` (the same meaning under any
  collation), returns the account's own spelling, and keys its rate-limit bucket on the
  casefolded name, so every capitalisation of one name no longer gets a fresh budget of
  guesses.
- **Clients adopt the returned name.** `signIn()` stores `user.username` from MuMa's answer
  and returns it. `LoginPage` saves that name to the phone. `restoreSession` writes it back
  when the phone stored another case, so a phone signed in before the fix repairs itself on
  its next boot. The native `ensureMumaLogin` does the same for sessions the WebView never
  sees (`MumaStoredCredentials.canonicalUserName`).
- **Creating an account** (`POST /api/users`, approving a Google access request) refuses a
  name that differs only in case from an existing one with 409. The `users.username` unique
  key already refused it through its collation, but as a 500. `test_schema.py` now pins that
  database behaviour.
- **Everything that stores or compares a username** uses the canonical spelling:
  `/api/scrobble/event` and the ListenBrainz import store the authenticated account's own
  spelling for a user key and the canonical spelling for the system key or an admin. The
  self-only rule compares case-insensitively and still refuses another account. The same
  holds for the LMS rating webhook, the `/api/rating/ratings/{username}` and
  `/api/listening` own-account checks, and the feeds' system-key username (the daily picks
  are seeded on it). The listen reconcile maps both sides to the account spelling before it
  classifies and inserts.
- **Data repair** is a separate, re-runnable, guided script that was not run by the change:
  `scripts/prod/repair-username-case.sh`, which drives `tools/repair_username_case.py`
  (tested against a fixture lms.db and a fake cursor). It rewrites MuMa rows under a case
  variant and merges LMS user 13 into user 1, taking listens, ratings, stars, play queue,
  playlists, bookmarks and tokens with it, then deletes user 13. Backups come first and
  there is a dry-run plan. See `docs/open-work.md`.

Left open, on purpose: a unique index on `lower(login_name)` in LMS. A versioned LMS
migration adding it would fail on production for as long as the fork exists, and then
LMS would not start. It belongs in a migration after the repair has run.
The repair ran on 2026-09-25, and the index followed in LMS schema version 124
(`docs/bug-reports/102-lms-login-unique-index.md`).
