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
  token when one is stored for the signed-in name; `signIn` asks for the MuMa session first (password
  in the POST body), fetches the token with its key in one plain request (no 503 retries), pings
  signed with it, and only then publishes the session together with the credentials -- a key
  published earlier let the UI fire Subsonic calls before any credentials existed; startup and the shell's restore
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

## Recovering from a refused token (issue #73)

The refresher above only runs when the web shell starts or signs in. Android Auto runs the media
session without the UI, so after an administrator replaced the user's token
(`PUT /muma/api/admin/subsonic-token`) every browse, stream and cover-art call from the car kept
answering error 40 until the phone's UI was opened once (bug report
[111](../../bug-reports/111-android-auto-keeps-a-replaced-subsonic-token.md)).

- **Where.** `TokenRecoveryInterceptor` (`:core:subsonic-api`) is installed in every native
  Subsonic client: the `SubsonicAPIClient` built by `MusicServiceModule` (all `RESTMusicService`
  calls, the cover-art loaders `CoverArtRequestHandler`/`ImageLoader`, and the stream-URL builder,
  which derives from the same client) and the plain `OkHttpClient` behind Media3's
  `OkHttpDataSource` in `PlaybackService`, which fetches the pre-signed stream URL. It sits behind
  the signing interceptors, so it sees the finished `t`/`s`. The offline client gets none.
- **What counts as a refusal.** HTTP 401, or Subsonic error 40 in a JSON or XML body. LMS answers
  an API call with HTTP 200 and the error inside, a stream or cover-art call with HTTP 400 and the
  same body. Only a JSON/XML body is peeked (at most 8 KiB, not consumed); media is never read.
  Only token-signed requests qualify: a request with `p=` uses the password fallback, which a new
  token cannot repair.
- **What happens.** When `t = md5(storedToken + s)` the stored token itself was refused, and the
  interceptor asks `SubsonicTokenRecoverer` (process-wide, `SubsonicTokenRefresher.recovery`, so its
  state survives the Koin rebuild) for a new one. The recoverer runs
  `RESTMusicService.refreshSubsonicToken` -- the MuMa API key, re-logging in only if the key itself
  is refused, exactly as the shell-triggered refresh does -- and, when a different token got
  stored, rebuilds the music service on the main thread and hands it back. The interceptor re-signs
  the same request with it (fresh salt) and sends it once more; that second answer is returned
  whatever it is. A request signed with an older token than the stored one (a client built before
  the last refresh) is retried with the stored token without a refetch.
- **Single flight and back-off.** One refetch at a time, under a lock; a caller that waited and then
  finds a different token stored uses it without fetching. After a refetch that brought no new
  token -- MuMa unreachable, the endpoint refusing, or the same token again (a revoked account) --
  no refetch runs for 5 minutes; after one that did, not for 30 seconds. A refused account costs
  one MuMa round trip per window, never one per request.
- **Sign-out wins.** `SignOutEpoch` counts sign-outs. `ActiveServerProvider.signOut` clears the
  credentials under its lock; `refreshSubsonicToken` captures the epoch before the fetch and stores
  its answer only through `SignOutEpoch.storeIfUnchanged`, which checks and writes under the same
  lock. This closes the gap the password check of bug report 106 left between check and write, and
  also catches a sign-out followed by a new sign-in during the fetch. The recoverer checks the epoch
  again before retrying or rebuilding.
- **Fallback unchanged.** When recovery brings no new token the stored token stays and the refused
  answer reaches the caller as before (`AuthenticationFailureNotifier` included). The password
  fallback still applies only while *no* token is stored -- dropping a refused token to fall back to
  `p=` would widen the exposure issue #72 is about to narrow, and would not help anyway: the cases
  where the refetch fails (MuMa down, account disabled) are the ones where LMS's password check,
  which asks MuMa, fails too.
- **Logging.** The recoverer logs what happened, never the token or an exception message (which can
  quote a URL); the debug request log redacts `t`/`s`/`p` as before (`LogRedaction`,
  `redactingLoggingInterceptor`).

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
7. A refused token triggers exactly one refetch and one retry signed with the new token; concurrent
   refusals share one refetch; a second refusal after the refetch is returned, not retried; a
   password-signed request, another Subsonic error and a media body are left alone
   (`TokenRecoveryInterceptorTest`, through a real `SubsonicAPIClient` against a server that checks
   `t` like LMS).
8. Back-off after a refetch without a new token, a sign-out (also followed by a new sign-in) during
   the refetch discards the answer, and no token reaches the log (`SubsonicTokenRecovererTest`).

## Related Docs

- [docs/bug-reports/054-app-trusts-any-certificate-and-leaks-secrets.md](../../bug-reports/054-app-trusts-any-certificate-and-leaks-secrets.md), item 2
- [docs/authentication.md](../../authentication.md)
- [docs/api-specification.md](../../api-specification.md)
