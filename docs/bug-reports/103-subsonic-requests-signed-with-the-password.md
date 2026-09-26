# Subsonic Requests Signed With The Password

# status: fixed

# reported problem
GitLab issue #21, bug report 054 item 2: MuMa Mobile signed every Subsonic request with the login
password as `p=enc:<hex>` -- a reversible encoding, not a hash -- in the URL, because
`StaticServers.FORCE_PLAIN_TEXT_PASSWORD` was `true`. Every stream, cover and API call therefore
put the password into every access log on the way. Looking for every place a Subsonic URL is built
showed the same leak in two more places:

- The web player -- which is also the Android app's UI, in the Capacitor shell -- built every URL
  from `store.authParams` as `u=<name>&p=<password>`, in plain text, not even hex-encoded. That
  covered stream, cover-art and API URLs, and the artist-image URLs it sends through LMS's `/muma`
  bridge.
- `ActiveServerProvider.getRestUrl` built a `p=enc:` URL that was never requested but kept a
  reversible copy of the password in a string used as a cache key.

The crash report copy the app saves to the public Downloads folder was written without redaction,
so any credential in the web UI's action trail or in a crash text reached it verbatim.

# Possible reason
LMS checks the salted form (`t=md5(secret + salt)&s=salt`) against the user's *Subsonic API token*
(`auth_token`, domain `subsonic`), never against the login password, which LMS does not hold in any
form it could salt. The clients only knew the password, so `p=` was the only form LMS accepted
from them; bug report 054 therefore kept it on purpose and recorded the way out. The one way to
obtain a token was `/muma/api/admin/subsonic-token`, which needs an administrator.

# solution
- music-manager: `GET /api/auth/subsonic-token` returns the caller's own token -- the account the
  key resolves to, nothing in the request can name another -- read from LMS's `lms.db`, or issued
  there (32 random bytes) when the user has none. An administrator-issued token is returned as it
  is. The key check runs inside the login rate limiter; the token is never logged.
  `services/music_manager/subsonic_token.py`.
- MuMa Mobile: `SubsonicSigning` configures the Subsonic client with the token and the existing
  per-request-salt MD5 interceptor; `FORCE_PLAIN_TEXT_PASSWORD` is `false`. The token is fetched
  after every sign-in and on every shell start (`SubsonicTokenRefresher`) and kept in
  `SecureSettings`. `getRestUrl` no longer carries the password.
- Web player: `authParams` signs with `t`/`s` (one salt per page session and token, so image URLs
  stay cacheable) once a token for the signed-in name is stored; `signIn` starts the MuMa session
  first (password in the POST body), fetches the token and pings signed with it.
- LMS: the `/muma` bridge accepts `u`/`t`/`s`, checked exactly as `/rest` checks it, so the
  artist-image URLs work without the password.
- Diagnostics: `LogRedaction` also masks credential-named JSON members; the Downloads copy of a
  crash report is redacted like the upload.
- Fallback, deliberately: until a token is stored (an upgraded install before its first fetch, a
  server without the endpoint) the password stays the signing secret, over verified TLS and
  redacted from logs -- today's exposure, bounded to the time before the first successful fetch.
  Failing closed would lock Android Auto out after an upgrade. See
  `docs/designs/subsonic-token-signing/technical.md`.

Bug report 054 item 2 is closed by this report.

Tests: `services/music_manager/tests/test_subsonic_token.py`, `SubsonicTokenSqlTest` in
`tests/integration/test_router_sql.py`, the u/t/s cases in
`services/music-management-server/src/libs/muma/test/Authentication.cpp`, `SubsonicSigningTest`,
`StaticServersTest`, `LogRedactionTest`, `CrashReportManagerTest`, and the frontend's
`store.test.js`, `login.test.js` and `md5.test.js`.
