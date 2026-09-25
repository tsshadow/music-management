# LMS fork baseline and account lifecycle — Technical Design

Implements [functional.md](functional.md). The fork documentation itself, including the database
version policy, is [`services/music-management-server/FORK.md`](../../../services/music-management-server/FORK.md).

## Data Model

- LMS `user.disabled INTEGER NOT NULL DEFAULT 0` (`db::User::isDisabled()` / `setDisabled()`),
  added by migration step 121 (`migrateFromV121`, database version 121 -> 122). The step checks
  `pragma_table_info` first so it can run twice. Written only by the user synchronizer.
- `db::AuthToken::clearAllUserTokens(session, userId)` deletes a user's tokens in every domain
  (`subsonic`, `ui`).
- Users are never deleted by the sync. Listens, ratings, stars and playlists refer to the user by
  plain id (there is no foreign key in the fork), so a deleted row would orphan them and a
  re-created user would get a new id.

## Sync algorithm

`UserSynchronizer::syncUsers()` fetches `GET <music-management-url>/users/` as before; the body goes
to two free functions in `impl/musicmanagement/MumaUserSync.hpp`:

- `parseMumaAccounts(body)` -> `nullopt` when the body is not a JSON array. Otherwise one
  `MumaAccount {mumaId, username, isAdmin, enabled}` per usable row. A row that is not an object,
  has no positive whole-number `id`, or has no non-empty string `username` is counted in
  `rejectedRows` and skipped. Every readable id goes into `listedIds`, even for a rejected row; a row
  without a readable id clears `everyRowIdentified`. `is_admin` and `enabled` accept JSON booleans
  and MariaDB's 0/1; a missing `enabled` means enabled.
- `applyMumaAccounts(session, list)`:
  1. Per account, in its own write transaction: find by MuMa id, then by name (case-insensitive,
     `User::find`), else create; set MuMa id, name, role. `enabled == false` -> set `disabled` and
     clear every token (tokens last: the delete is raw SQL and not undone by a later throw).
     `enabled == true` on a disabled user -> clear `disabled`.
  2. Unless `listedIds` is empty or `everyRowIdentified` is false: every LMS user with a MuMa id not
     in `listedIds` is disabled and loses its tokens, each in its own transaction. Users without a
     MuMa id are left alone.
  3. A failure in one transaction is flushed inside a try, `discardUnflushed()` drops the dirty
     objects, the failure is logged and counted (`MumaSyncSummary::failed`), and the loop continues.
     Before, one throw ended the loop -- and a throw from the commit in `WriteTransaction`'s
     destructor would have ended the process.

## Enforcement

The sync revokes tokens, but a token can be issued again afterwards (the admin token route does not
check), and the internal/PAM password backends know nothing of MuMa. So a disabled user is refused
everywhere a credential is resolved:

- `AuthTokenService::processAuthToken` (Subsonic `apiKey`, web-UI remember-me): denied in the
  lock-free read path.
- `PasswordServiceBase::checkUserPassword`: a matching password for a disabled user is `Denied`,
  not counted as a bad attempt.
- `HttpHeadersEnvService`: denied.
- `SubsonicResource` salted-token (`t`/`s`) path: a disabled user is skipped.
- `/muma` needs nothing extra: a MuMa user key is verified by MuMa, which refuses disabled accounts,
  and u/p goes through the password service.

## Testability changes (no behaviour change)

- Both `MusicManagementBackend`s (scrobbling, feedback) take an injected `core::http::IClient` and
  API key; the configured constructor delegates to it.
- `MumaResource`'s pure logic moved to `src/libs/muma/Routing.cpp`: `classifyRouteFamily` (the
  `/users/` + `/api/` allow-list), `parseUserSettingsPath`, `buildProxyRelativeUrl`,
  `buildProxyHeaders`. One tightening: a settings path whose user id is not a plain positive number
  is a 400 (`std::stoll` read `12abc` as 12).
- `Db::getTLSSession()` keys the thread's cached session by a per-instance id. It was a bare
  `thread_local` pointer, which dangled once a test suite's database was destroyed and the next
  suite opened another; test binaries with several database suites crashed depending on allocation
  order. Production opens one database, so nothing changes there.

## API Contract

No request or response shape changes. `GET /api/users/` (music-manager) is read as before; its
`enabled` field, which it already returned, is now used. `DELETE /api/users/{id}` pokes the LMS sync
after its commit (see Cross-App Impact).

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `/muma/users/{id}/settings/{app}` | unchanged | unchanged | `400 Invalid User ID` now also for ids with trailing garbage (`12abc`) |

## Cross-App Impact

- music-manager: `DELETE /api/users/{id}` now pokes `/muma/users/sync` after its commit, as enable
  and disable already did. Without it a deleted account was only noticed at the next sync (an
  enable/disable elsewhere, an admin `syncUsers`, or an LMS restart). `GET /api/users/` already
  returned `enabled`.
- Clients: none. A re-enabled account needs a new Subsonic key, which is issued the way any new key
  is (the app's sign-in or `/muma/api/admin/subsonic-token`).

## Technical Acceptance Criteria

1. `test-auth` `MumaUserSync.*`: create, update, case-insensitive link, disabled account (tokens
   revoked in every domain, rating kept, idempotent), re-enable, deleted account, empty list,
   unreadable id, malformed rows skipped, failing write skipped.
2. `test-auth` `DisabledUser.*`: a disabled user's token and correct password are refused; enabling
   restores both.
3. `test-scrobbling` / `test-feedback` `MusicManagement*`: relay payloads, key header, no send for
   unknown objects or stars, and the request flags that decide the send queue's retry/drop.
4. `test-muma` `MumaRouting.*`: allow-list, settings path parsing, proxy URL and headers.
5. `test-database` `Database.migration`: `user.disabled` exists, `NOT NULL DEFAULT 0`, and the step
   survives being run twice.

## Related Docs

- [`services/music-management-server/FORK.md`](../../../services/music-management-server/FORK.md)
- [docs/authentication.md](../../authentication.md)
