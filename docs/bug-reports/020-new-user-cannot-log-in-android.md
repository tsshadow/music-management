# title: New user cannot log in on the Android app: "Google sign-in failed", then "Could not connect to LMS"

# status: root cause found (Cloudflare Access gates the Muma API from outside the LAN); app-side
# messaging + CI debug signing fixed in this repo; the Access policy and the user's account are
# still open — see "still required outside this repository"

# reported problem
A new user (`user@example.org`) installed the latest Ultrasonic Android app and could not
get in at all:
1. "Sign in with Google" showed *"Inloggen met Google is mislukt"*
   (`welcome_google_signin_failed`).
2. Falling back to username/password showed *"Kon geen verbinding maken met LMS. Controleer je
   gegevens."* (`welcome_connection_failed`), which reads as a server/network outage.

# investigation
The production backend was verified healthy during the reported outage window — from inside the
LAN, which turned out to matter a great deal (see the Cloudflare Access section below):

| probe | result |
|---|---|
| `POST https://muma.example.com/api/auth/login` (bogus user) | `401 {"detail":"Invalid username or password"}` |
| `POST https://muma.example.com/api/auth/google` (bogus token) | `401 {"detail":"Invalid Google token: Wrong number of segments..."}` |
| `GET https://music.example.com/rest/ping.view` (bogus creds) | Subsonic `error 40 Wrong username or password` |
| `GET https://muma.example.com/api/auth/setup-status` | `200` |

So neither auth endpoint was down, and `GOOGLE_CLIENT_ID` is configured on the server (otherwise
`_verify_google_id_token()` would answer `500 Google auth is not configured`, not `401`).

Given a healthy server, each symptom resolves to something else:

**Symptom 2 is a mislabeled error, not an outage.** `NavigationActivity.showWelcomeDialog()` probes
the server with `isServerReachable()` after a failed `ping()` precisely to tell connectivity apart
from bad credentials — but then shows `welcome_connection_failed` ("Could not connect to LMS") on
the `reachable == true` branch, i.e. exactly when it *did* connect and the credentials were
rejected. The user has no account on the server (accounts are created only by an admin, or by
admin approval of a Google access request), so the rejection was correct; only the wording was
wrong, and it sent everyone looking for a network problem that never existed.

**Symptom 1 happened before the backend was ever contacted.** The message shown was
`welcome_google_signin_failed`, not `google_signin_no_accounts`, and not
`welcome_server_unreachable` — the failure path re-probes the server and would have said
"unreachable" otherwise. That narrows it to Android's Credential Manager / Google Play Services
refusing to issue a credential (or a non-2xx from `/api/auth/google`, which was verified working).
Note that an *unknown* Google identity is not an error case at all: `/api/auth/google` answers
`200 {"status": "unknown"}` and the app navigates to the access-request screen. Getting an error
instead means the flow never reached that point.

(This reasoning held only because `/api/auth/google` had been probed from inside the LAN. From the
phone's actual vantage point it does *not* answer — see the Cloudflare Access section, which is the
real answer for symptom 1.)

One concrete, in-repo cause for that was found: **CI debug APKs could never do Google Sign-In.**
`scripts/ci/ultrasonic-build-upload.sh` only wrote the signing keystore for `release` builds. Debug
builds therefore fell through to the throwaway debug keystore auto-generated *inside the ephemeral
Android SDK docker container*, i.e. a different signing certificate on every single build. Per bug
report [011](011-google-signin-no-credential-real-device.md), Google only issues a credential to an
app whose package name + certificate SHA-1 match a registered Android-type OAuth client, so a
per-build random certificate can never match anything. Both debug (`develop`) and release builds
are uploaded to the same apk-hoster, and debug uploads are far more frequent, so "the latest
Android app" there is often the debug one — identifiable by its app name, "Ultrasonic Debug".

Whether this user in fact installed the debug build was not confirmed, so it is a cause that
certainly exists but not necessarily *the* cause of this particular report.

# solution
App-side (`NavigationActivity`, `strings.xml`, `values-nl/strings.xml`):
- The "server reachable but ping failed" branch now shows the new `welcome_invalid_credentials`
  ("Wrong username or password. The server itself was reached, so this is not a connection
  problem — ... or ask the administrator for an account.") instead of `welcome_connection_failed`.
- Google Sign-In failures now name their concrete cause *on screen*
  (`welcome_google_signin_failed_detail`, e.g. "Google sign-in failed (GetCredentialUnknownException)"
  or "(HTTP 401)"), not only in `Timber`/logcat. Bug report 019 added logcat-only diagnostics, which
  are unusable for remote, non-technical users; the exception class / HTTP status is what
  distinguishes a Play Services refusal from an unregistered signing certificate from an OAuth
  client misconfiguration, and a screenshot can now carry it.

CI (`scripts/ci/ultrasonic-build-upload.sh`):
- The keystore is written for debug builds too whenever `SIGNING_STORE_FILE` and
  `SIGNING_STORE_PASSWORD` are both available, giving CI debug APKs a stable, registerable SHA-1.
  It stays a hard requirement for release builds only; a debug build without it still succeeds and
  now logs a warning saying its Google Sign-In will fail. `SIGNING_STORE_PASSWORD` is now also
  checked up front for release builds, instead of failing later inside Gradle.

# actual root cause of the Google Sign-In failure from outside the LAN: Cloudflare Access
Every probe in the table above was run from inside the LAN, where `muma.example.com` resolves to
`192.0.2.30` (Nginx Proxy Manager) and Cloudflare is never involved. From outside, the same
hostnames resolve to Cloudflare (`188.114.96.0` / `188.114.97.0`), and there the picture is
different:

```
$ curl -D - --resolve muma.example.com:443:188.114.97.0 \
       https://muma.example.com/api/auth/setup-status
HTTP/2 302
location: https://example.cloudflareaccess.com/cdn-cgi/access/login/muma.example.com?...
set-cookie: CF_AppSession=...
server: cloudflare
```

`muma.example.com` sits behind **Cloudflare Access** (Zero Trust): every external request, `POST
/api/auth/login` and `POST /api/auth/google` included, is 302'd to an interactive SSO login page.
`music.example.com` is *not* behind Access and answers `200` externally.

That combination produces the reported symptom exactly:
- The welcome dialog's reachability probe hits `music.example.com`, which answers, so the app
  correctly reports the server as reachable and never shows "server unreachable".
- The Google sign-in POST goes to `muma.example.com/api/auth/google`, gets the 302, follows it
  to the Access login page and receives HTML instead of JSON — so `authResult` is null and the app
  falls back to the generic "Google sign-in failed".
- The username/password attempt goes through Subsonic on `music.example.com` instead, which
  is reachable, and failed separately on the missing account.

**Access was the only thing shielding several unauthenticated endpoints.** `POST
/api/tagger/tag/all`, `/tag/file`, `/tag/stop` (these write tags to the actual music files), `POST
/api/scanner/scan/all`, `/scan/file`, `POST /api/scrobbler/import/listenbrainz` and `GET
/api/scrobbler/import/latest` had no auth dependency at all, so a `Bypass` policy covering the
whole hostname exposes them to the internet — confirmed after the bypass was added, with
`GET /api/tagger/health` answering publicly.

They are guarded with `Depends(verify_api_key)` as of this change (see "solution" above); the two
`/health` endpoints are deliberately left open for monitoring. **The guards only take effect once
this is deployed to production** — until then, keep the Access bypass scoped to `/api/auth/*`
rather than the whole hostname.

`POST /api/jobs/register/{job_id}` is deliberately left unguarded: it only writes to an in-memory
job dict, and its callers are external workers that could not be located in this repository, so
guarding it risks breaking their status reporting for very little gain.

# contributing cause on Google's side: consent screen was in Testing
The OAuth consent screen for the project behind `GOOGLE_CLIENT_ID` was in **Testing** publishing
status while this was reported, and the reporting user was not on its test-user list. In Testing,
Google only issues a credential to listed test accounts, so a brand-new user fails while the
project owner succeeds — exactly the reported split, and it happens entirely on Google's side,
before this app's backend is ever contacted, which is why the app could only show its generic
"Google sign-in failed". It has since been switched to **In production** (user type External),
which should let any Google account sign in.

Along the way the other configuration suspects were checked and ruled out, for the project number
`000000000000`:

- The Android OAuth client for `nl.teunschriks.mumamobile` exists, with SHA-1
  `C2:5C:21:2B:E3:BC:25:00:88:FA:6A:9D:86:C0:2E:AD:EC:B2:D9:5A`. It is *not* the local debug
  keystore's fingerprint (`39:2B:26:CF:...`), consistent with it being the release keystore.
- The Web client ID served by the live frontend
  (`000000000000-drld1n0bs77fvk88s0dskf8pp298u14e.apps.googleusercontent.com`) is in that *same*
  project, so the `serverClientId` the app passes and the Android client match up.
- The OAuth user cap sits at **1 / 100**, so the cap has not been exhausted either — that single
  user is the project owner, the only account Testing mode ever let through.

# secondary risk, still open: unapproved sensitive scopes
Switching to production does not necessarily finish the job, because of the consent screen's own
warning: *"Your app requires verification"* /
*"If your users are seeing the 'unverified app' screen, it is because your OAuth request includes
additional scopes that haven't been approved."* The project has unapproved **sensitive or
restricted** scopes configured while unverified.

**Nothing in this repository asks for those scopes.** The web frontend calls
`window.google.accounts.id.initialize({ client_id, callback })` with no `scope` parameter
(`services/frontend/src/lib/LoginPage.svelte`), the Android app uses
`GetSignInWithGoogleOption.Builder(serverClientId)` with no scopes, and
`_verify_google_id_token()` only reads the `sub`/`email`/`name`/`picture` claims out of the ID
token — no Google API is ever called. That is `openid` + `email` + `profile`, all non-sensitive,
which require no verification at all. The sensitive scopes are leftovers on the consent screen.

This matters specifically on Android: on the web an unverified app shows a dismissible "Google
hasn't verified this app" interstitial, but Credential Manager has no such interstitial and can
only refuse — which would surface as the exact same generic "Google sign-in failed" as the Testing
lockout did. So if the first non-owner sign-in still fails now that the app is in production, this
is the next thing to clear, not a new mystery.

# still required outside this repository
1. **Let the Muma API through Cloudflare Access.** Zero Trust → Access → Applications → the
   `muma.example.com` application needs a `Bypass` policy; the API enforces its own
   authentication (`X-API-Key`, bcrypt passwords, Google ID token verification), so Access in front
   of it only breaks non-browser clients. *Done* — `muma.example.com` was added to the existing
   Bypass policy's destinations, and all three auth endpoints were verified answering real JSON
   from outside afterwards. Keep the bypass scoped to `/api/auth/*` until the endpoint guards in
   this branch are deployed, then widen it to the whole hostname — which is needed anyway, since
   the mobile app also uses the Muma API for ratings, settings sync and the management tab.
2. **Remove the unapproved sensitive/restricted scopes** under *Google Auth Platform → Data
   access*, leaving only `openid`, `.../auth/userinfo.email` and `.../auth/userinfo.profile`. That
   drops the verification requirement entirely, since nothing here uses the other scopes.
3. **Give the user an account.** Even a fully working Google Sign-In only gets an unknown identity
   as far as the access-request screen; an admin still has to approve the request
   (`/api/user-requests`) or create the account directly. Until then, no login method can succeed.
4. **Optionally** register the release keystore's SHA-1 for `nl.teunschriks.mumamobile.debug` too,
   so debug builds from apk-hoster can do Google Sign-In at all (see muma-ops docs/deployment-production.md). No such
   Android client currently exists, so Google Sign-In cannot work on a debug APK regardless of the
   above.
