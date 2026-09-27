# Subsonic Token Signing — Technical Design

Implements [`functional.md`](functional.md). Bug report
[103](../../bug-reports/103-subsonic-requests-signed-with-the-password.md), GitLab issue #21; the
password fallback was removed by issue #72 (see "Fallback decision").

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
is unchanged. Old apps keep sending `p=` and keep working -- LMS still accepts it; issue #72 only
removed the clients' ability to send it.

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
- **MuMa Mobile**: `SubsonicSigning.tokenFor` picks the stored token for the client build
  (`MusicServiceModule`), or none; `RESTMusicService.refreshSubsonicToken` fetches and stores;
  `SubsonicTokenRefresher` runs it after the shell's `saveCredentials` and on every shell start
  (`MumaSystemPlugin.credentials`), rebuilding the music service when the token changed. Since
  issue #72 there is no password signing at all -- see "Fallback decision".
- **Diagnostics**: `LogRedaction` also masks credential-named JSON members; the crash report copy
  written to Downloads is redacted like the upload.

## Fallback decision

**Removed (issue #72).** Until then the password stayed the signature while no token was stored:
failing closed would have locked a listener out whenever the first fetch failed, and out of Android
Auto after an upgrade, because the only fetch ran when the UI opened. Two things changed that
trade-off. Bug report 111 gave the native client a way to fetch a token from any request thread,
without the UI. And production showed the fallback was not a short transition state: on
2026-09-27 the web shell (`c=spotify`, the phone's WebView) sent 1,200 `/rest` requests with a
plain `p=` over two log windows, while all native requests were token-signed. The cause is in bug
report [124](../../bug-reports/124-web-shell-signs-with-the-password-after-a-failed-token-fetch.md):
the web fetched the token once per page load, silently, and a page whose fetch failed signed with
the password for its whole lifetime -- hours, in a WebView. A fallback that silently covers a
failing token path is how the password stayed in URLs after the fix.

Now every client fails closed:

- **Native** (`:core:subsonic-api`). `TokenSigningInterceptor` replaces `ProxyPasswordInterceptor`,
  `PasswordHexInterceptor` and `PasswordMD5Interceptor`; `SubsonicClientConfiguration` has a
  `token` instead of `password`/`forcePlainTextPassword`. It signs with the token the client was
  built with, or -- when none was stored then -- asks `SubsonicTokenRecovery.obtain()`, which
  `SubsonicTokenRecoverer` implements: under the same lock as recovery it fetches the token
  (`refreshSubsonicToken`, MuMa key first, re-login only if the key is refused), stores it,
  rebuilds the music service and hands it back. When no token can be had the interceptor throws
  `SubsonicTokenUnavailableException` (an `IOException`) and the request is never sent. The
  exception carries a reason: `SIGN_IN_AGAIN` (signed out; MuMa refused the login,
  `MumaLoginRefusedException`; the endpoint answered 401/403/404) or `SERVER_UNREACHABLE` (any
  other I/O failure, a 5xx or a 429). A failed first fetch backs off for 30 s (not the 5 minutes of
  a refused-token refetch: without any token nothing plays); signed out, nothing is fetched and no
  back-off is set, so the sign-in that follows is not held up. Because the stream-URL builder runs
  the request through the same interceptors (`RESTMusicService.getStreamUrl`), no stream URL is
  built without a token either.
- **Before the first request.** `PlaybackService.onCreate` -- also how Android Auto starts the app
  without the UI -- calls `SubsonicTokenRefresher.prefetchIfMissing()`, so the first browse
  normally finds a token. `MediaLibraryBrowser.getChildren` asks `SubsonicAccess.blockingReason()`
  (which fetches if needed, off the main thread) before loading a level, and answers
  `LibraryResult.ofError(SessionError(...))` with `ERROR_SESSION_AUTHENTICATION_EXPIRED` and
  "Sign in again in the MuMa app on your phone", or `ERROR_IO` and "Cannot reach the MuMa
  server", instead of swallowing the failure into empty lists.
- **Web** (`services/frontend`, also the shell's UI).
  - **Signing.** `authParams` is the token query or `""`; there is no `p=` branch, and the password
    is no longer needed to sign (only the name and a token issued for it).
  - **Sign-in.** `signIn` fails without a MuMa session (`rejected` on 401/403, `offline`
    otherwise) or without a token, and never pings with the password. It asks for the token up to
    three times, because 503 (LMS's database locked) and 404 (account not synced yet) pass in a
    second or two; a refusal is final.
  - **`/rest` calls.** `subsonicJson` fetches a missing token before a call and throws
    `SubsonicTokenUnavailableError` without sending anything when none comes. An unsigned call
    would be answered with error 40 and end the session.
  - **Fetching.** `ensureSubsonicToken()` fetches a missing token once for all callers. It runs at
    start-up (`hydrateMumaUserFromApiKey`) and in the shell's `restoreSession`, which first takes
    over the native client's token when the bridge hands one over for the same name
    (`MumaSystemPlugin.credentials` now returns `subsonicToken`/`subsonicTokenUser`;
    `forcePlainTextPassword` is gone).
  - **Retrying.** `keepSubsonicTokenFresh()` (started in `App.svelte`) keeps asking every 30 s, on
    `visibilitychange` and on `online` while no token signs. That is the fix for bug report 124:
    a page is never again stuck with the outcome of the one fetch it made at load.
  - **Errors and names.** `refreshSubsonicToken` records why a fetch failed in
    `subsonicTokenProblem`, and adopts LMS's spelling of the signed-in name when it differs in case
    only.
  - **Notice.** `subsonicAccess` (`none`/`ok`/`pending`/`offline`/`rejected`) drives a notice
    above the content in `App.svelte`: `OfflineNotice` kind `server`, with a retry, or `signIn`,
    which ends the session and shows the login page.
  - **Search thumbnails.** These now carry the signature too; they were sent with no credentials
    at all before.
- **Proof in a real browser.** `services/frontend/tests/browser/subsonic-signing.spec.js`
  (`frontend:browser`, against `docker/compose.test.yml`, whose music-manager shares LMS's
  database) signs in through the UI and checks every `/rest` request -- API, cover art, stream --
  for `t`/`s` and against `p`. It covers four starts:
  - a fresh sign-in;
  - a start with the stored session;
  - a start without a stored token;
  - a start whose token fetch fails (which must also recover without a reload).

  On develop the last two send `p=` (bug report 124); on this branch all four pass.

**The stored password is kept.** After sign-in it signs nothing, native or web. It stays in
`ServerSetting.password` / the web's `credentials.password` for two jobs no token covers yet: it
is what `ensureMumaLogin(force = true)` re-logs in with when MuMa refuses the stored key (the
token fetch, tiles, settings), and a blank password is the "signed out" marker the shell bridge,
`restoreSession` and the native sign-out rely on. Clearing it would need a MuMa-key-only re-auth
path and a separate signed-in flag on both sides; that is a follow-up (issue #101), not
part of removing the fallback.

**What an old install does after updating.** Its first start after the update has no token or a
token stored by the previous build. With one, nothing changes. Without one, the app (or the car)
fetches it with the stored MuMa key before the first request; a stored password is still there for
a re-login if the key was refused. If MuMa is down at that moment, the app shows "server not
reachable" and retries (native: after 30 s, on the next request; web: the notice's retry button,
or the next start) -- it does not play until then. LMS itself is unchanged and still accepts `p=`
from installs that were never updated.

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
- **No fallback.** When recovery brings no new token the stored token stays and the refused answer
  reaches the caller as before (`AuthenticationFailureNotifier` included). There is no password to
  fall back on (issue #72); it would not help anyway: the cases where the refetch fails (MuMa down,
  account disabled) are the ones where LMS's password check, which asks MuMa, fails too.
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
   `p`, on every protocol version (`SubsonicSigningTest`, `SubsonicApiTokenSigningTest`,
   `TokenSigningInterceptorTest`); `StaticServersTest` pins the leftover column at `false`.
5. The web player's `authParams` and sign-in ping never carry the password; without a token
   `authParams` is empty and the sign-in fails instead of falling back, and a token LMS refuses is
   dropped (`store.test.js`, `login.test.js`, `md5.test.js`).
6. `LogRedactionTest` and `CrashReportManagerTest` pin the JSON-member and export redaction.
7. A refused token triggers exactly one refetch and one retry signed with the new token; concurrent
   refusals share one refetch; a second refusal after the refetch is returned, not retried; a client
   built without a token signs with the one it fetched and still recovers once; another Subsonic
   error and a media body are left alone
   (`TokenRecoveryInterceptorTest`, through a real `SubsonicAPIClient` against a server that checks
   `t` like LMS).
8. Back-off after a refetch without a new token, a sign-out (also followed by a new sign-in) during
   the refetch discards the answer, and no token reaches the log (`SubsonicTokenRecovererTest`).
9. End to end in the test stack, where `docker/compose.test.yml` mounts LMS's database directory
   into music-manager at `/app/data/stable` as production does: a normal user's key gets a token
   from music-manager, that token signs a `ping` and a `stream` against LMS, a system key gets 403,
   and a second call returns the same token
   (`tests/contracts/test_lms_subsonic_contract.py::test_music_manager_issues_a_token_that_signs_lms_requests`,
   issue #74).
10. Fail closed (issue #72): a client built without a token fetches one before its first request;
    a failed fetch sends nothing and reports `SIGN_IN_AGAIN` or `SERVER_UNREACHABLE`; a failed fetch
    backs off; signed out nothing is fetched; no stream URL is built without a token
    (`FailClosedSigningTest`). The car answers a browse without a token with a session error and
    message (`SubsonicAccessTest`). The web fetches a missing token once for all callers, keeps
    retrying while none signs, sends no `/rest` call without one, retries the sign-in's fetch,
    reports `offline`/`rejected`, takes over the phone's token, and the notice offers retry / sign
    in again (`store.test.js`, `subsonic.test.js`, `login.test.js`, `nativeSession.test.js`,
    `offlineShell.test.js`, `platformCapacitor.test.js`); end to end in a browser against the test
    stack (`tests/browser/subsonic-signing.spec.js`).

## Related Docs

- [docs/bug-reports/054-app-trusts-any-certificate-and-leaks-secrets.md](../../bug-reports/054-app-trusts-any-certificate-and-leaks-secrets.md), item 2
- [docs/authentication.md](../../authentication.md)
- [docs/api-specification.md](../../api-specification.md)
