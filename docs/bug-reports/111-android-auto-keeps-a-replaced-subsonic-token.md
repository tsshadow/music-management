# title: Android Auto keeps signing with a Subsonic token the administrator replaced

# status: fixed

# reported problem
GitLab issue #73, a follow-up to issue #21 / bug report 103. Since app 7.6.0 (MR !1034) MuMa
Mobile signs Subsonic requests with the user's Subsonic token (`t`/`s`) instead of the password.
When an administrator replaces that token (`PUT /muma/api/admin/subsonic-token` clears every token
of the user), the native client keeps signing with the old one. Every request -- browsing the car's
tree, streaming, cover art -- is answered with Subsonic error 40 ("wrong username or password")
until the app's UI is opened once. With only Android Auto in use (the media session runs without
the UI) that can be a whole drive.

# Possible reason
The token is fetched in exactly two places, both driven by the web shell:
`SubsonicTokenRefresher.refreshInBackground` runs after the shell's `saveCredentials` and on every
shell start (`MumaSystemPlugin.credentials`). Nothing on the request path reacts to a refusal: the
Subsonic client is built once with the stored token as its signing secret
(`MusicServiceModule` -> `SubsonicAPIClient` -> `PasswordMD5Interceptor`), so a refused token stays
in use until something rebuilds it, and in the car nothing does. The web player does recover (error
40 -> `endRejectedSession` -> sign in -> fresh token); the native client had no equivalent.

A related gap in the bug report 106 guard: `refreshSubsonicToken` dropped an answer when the password
was already cleared, but checked before writing, not atomically with it, and a sign-out followed by a
new sign-in during the fetch passed the check.

# solution
Design: [docs/designs/subsonic-token-signing/technical.md](../designs/subsonic-token-signing/technical.md),
section "Recovering from a refused token".

- `TokenRecoveryInterceptor` (`:core:subsonic-api`), installed in the `SubsonicAPIClient`
  (all `RESTMusicService` calls, cover art, stream-URL building) and in the `OkHttpClient` behind
  Media3's data source in `PlaybackService`. On HTTP 401 or Subsonic error 40 (HTTP 200 for API
  calls, HTTP 400 for streams and cover art; JSON or XML body peeked, media never read) for a request
  signed with the stored token, it asks for a replacement, re-signs the same request and sends it
  once more. A password-signed request (`p=`) is never retried.
- `SubsonicTokenRecoverer` (process-wide, `SubsonicTokenRefresher.recovery`): single flight -- one
  refetch through `RESTMusicService.refreshSubsonicToken` (MuMa API key), concurrent refusals wait
  and reuse its result; back-off -- 5 minutes after a refetch without a new token (a revoked account
  does not loop), 30 seconds after a successful one; rebuilds the music service after a new token
  was stored.
- `SignOutEpoch`: `ActiveServerProvider.signOut` clears credentials under its lock, and
  `refreshSubsonicToken` stores its answer only if no sign-out happened since it started, checked
  and written under the same lock. The recoverer checks the epoch again before retrying.
- Fallback rules unchanged: without a new token the stored one stays and the refusal reaches the
  caller as before; the password is still used only while no token is stored (issue #72 decides
  whether that fallback goes).
- The token is never logged; the recoverer logs events and exception class names only.

Tests: `TokenRecoveryInterceptorTest` (a real `SubsonicAPIClient` against a MockWebServer that checks
`t = md5(token + s)` like LMS: one refetch and one retry, concurrent refusals share one refetch, a
second 40 is returned, 401 and HTTP-400 stream refusals, password-signed and non-auth errors and media
bodies untouched), `SubsonicTokenRecovererTest` (back-off, sign-out during the refetch, sign-out plus
new sign-in, no token in the log).
