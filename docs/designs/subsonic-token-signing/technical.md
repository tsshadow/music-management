# Subsonic Token Signing — Technical Design

Implements [`functional.md`](functional.md). Bug report
[103](../../bug-reports/103-subsonic-requests-signed-with-the-password.md), GitLab issue #21.

## Which scheme LMS accepts

`SubsonicResource::authenticateUser` (services/music-management-server/src/libs/subsonic/impl)
accepts, besides `p`:

- `u` + `t` + `s`: `md5(storedToken + s) == t` for any `auth_token` row of the user in the
  `subsonic` domain (`db::AuthToken::find`). A read transaction, no call to MuMa.
- `apiKey`: the Subsonic token itself, resolved by `AuthTokenService::processAuthToken`.

**Chosen: `t`/`s`.** `apiKey` puts the token in the URL verbatim -- a permanent bearer credential in
every access log, the same class of leak as `p=enc:`. With `t`/`s` a URL only carries a salted
hash: it reveals neither the token nor the password, and it cannot be turned into a different
request. The native client uses a fresh salt per request (the existing `PasswordMD5Interceptor`,
unchanged); the web player draws one salt per page session and token, so the URLs a page builds
stay stable and the browser image cache keeps working. Both need API version >= 1.13.0 client-side
only (`ProxyPasswordInterceptor`); the app's minimum is 1.13.0.

## Data Model

No schema change. Tokens live in LMS's `lms.db`, table `auth_token` (main database since
`migrateFromV115`; plain values, unique on `(domain, value)` since V121). music-manager already
opens `lms.db` directly (`routers.users.lms_db_targets`) and writes only one thing here: an `INSERT`
of a row in the shape `AuthTokenService::createAuthToken` writes -- `version 0, domain 'subsonic',
expiry NULL, use_count 0, last_used NULL, max_use_count NULL`. Nothing is updated or deleted.

The caller's LMS user is `user.muma_id = <MuMa user id>`; when no row carries it, `login_name`
(exact spelling first, then case-insensitive, because of the case forks of bug report 074). The
first token of at least 16 characters (LMS's floor, `minSubsonicTokenLength`) is returned; without
one, `secrets.token_urlsafe(32)` is issued. With several server databases, the first one holding a
token wins and it is added to the others that lack it (added, never replacing another token).

Client-side storage:
- Android: `SecureSettings.subsonicToken` / `subsonicTokenUser` (EncryptedSharedPreferences, next to
  the MuMa tokens; cleared by `ActiveServerProvider.signOut`).
- Web: store `subsonicToken` (`{username, token}`), persisted like the credentials it sits next to
  (`lms_subsonic_token`), cleared by `endRejectedSession` and by logout's account-store reset.

## API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/auth/subsonic-token` (music-manager) | `X-API-Key: <user's own key>`; no parameters are read | `200 {status: "ok", username: <LMS login name>, token}` | 401 no/unknown key; 403 disabled account or system key; 404 account on no server yet; 503 no server database, or it cannot be read (`Retry-After: 5`); 429 after too many failed key checks (login rate limiter, per client) |
| LMS `/muma/*` bridge (`MumaResource`) | now also accepts `u`+`t`+`s` (checked like `/rest`, locally) | unchanged | unchanged |

Not breaking: the new endpoint is additive; the bridge accepts one more credential form; `/rest`
is unchanged. Old apps keep sending `p=` and keep working.

## Cross-App Impact

All in one MR (AGENTS.md rule 7):

- **music-manager**: `services/music_manager/subsonic_token.py`, route in `routers/users.py`.
- **LMS**: `libs/muma/Authentication.*` (`TokenChecker`, `AuthMethod::SubsonicToken`, counted as a
  user caller), `MumaResource.cpp` (`checkSubsonicToken`). Needed because the web player loads
  artist images through `/muma/api/artists/<name>/image?<authParams>` -- an `<img>` cannot send a
  header -- and those URLs would otherwise have kept the password.
- **Web player** (`services/frontend`, also the Android shell's UI): `authParams` signs with the
  token when one is stored for the signed-in name; `signIn` starts the MuMa session first (password
  in the POST body), fetches the token, then pings signed with it; startup and the shell's restore
  path fetch a missing token. `lib/md5.js` (Web Crypto has no MD5).
- **MuMa Mobile**: `SubsonicSigning` decides token vs. password fallback per client build
  (`MusicServiceModule`); `RESTMusicService.refreshSubsonicToken` fetches and stores;
  `SubsonicTokenRefresher` runs it after the shell's `saveCredentials` and on every shell start
  (`MumaSystemPlugin.credentials`), rebuilding the music service when the token changed.
  `StaticServers.FORCE_PLAIN_TEXT_PASSWORD` is `false`.
- **Diagnostics**: `LogRedaction` also masks credential-named JSON members; the crash report copy
  written to Downloads is redacted like the upload.

## Fallback decision

The password stays the fallback while no token is stored for the signed-in user. Failing closed
would lock a listener out of playback whenever the first fetch fails (MuMa briefly down during a
sign-in), and out of Android Auto after an upgrade, since Auto can run without the UI -- the only
place a fetch is started -- ever opening. The fallback is self-ending (every shell start retries),
travels only over verified TLS and is redacted from logs, i.e. exactly today's exposure, bounded to
the time before the first fetch. Removing it later is a follow-up issue.

## Technical Acceptance Criteria

1. `GET /api/auth/subsonic-token` returns the caller's existing token unchanged, or issues one of
   >= 16 characters into `auth_token`; a second call returns the same token
   (`services/music_manager/tests/test_subsonic_token.py`, `tests/integration/test_router_sql.py`).
2. The endpoint never returns another user's token, whatever the request carries; system key 403;
   wrong keys hit the rate limiter; the token is never logged (same unit tests).
3. The LMS bridge accepts `u`/`t`/`s` for the user whose token matches, refuses a forged one, and
   takes the identity from the token's user, never from `u` (`libs/muma/test/Authentication.cpp`).
4. With a stored token the native client's requests carry `t`/`s` with `t = md5(token + s)` and no
   `p`; without one they fall back to `p=enc:` (`SubsonicSigningTest`); `StaticServersTest` pins
   the flag at `false`.
5. The web player's `authParams` and sign-in ping carry no password once a token is known, fall back
   when the endpoint is missing, and drop a token LMS refuses (`store.test.js`, `login.test.js`,
   `md5.test.js`).
6. `LogRedactionTest` and `CrashReportManagerTest` pin the JSON-member and export redaction.

## Related Docs

- [docs/bug-reports/054-app-trusts-any-certificate-and-leaks-secrets.md](../../bug-reports/054-app-trusts-any-certificate-and-leaks-secrets.md), item 2
- [docs/authentication.md](../../authentication.md)
- [docs/api-specification.md](../../api-specification.md)
