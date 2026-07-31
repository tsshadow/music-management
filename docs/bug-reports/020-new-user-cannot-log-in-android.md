# title: New user cannot log in on the Android app: "Google sign-in failed", then "Could not connect to LMS"

# status: partially fixed (app-side messaging + CI debug signing fixed in this repo; two manual,
# external steps remain — see "still required outside this repository")

# reported problem
A new user (`someuser@example.com`) installed the latest Ultrasonic Android app and could not
get in at all:
1. "Sign in with Google" showed *"Inloggen met Google is mislukt"*
   (`welcome_google_signin_failed`).
2. Falling back to username/password showed *"Kon geen verbinding maken met LMS. Controleer je
   gegevens."* (`welcome_connection_failed`), which reads as a server/network outage.

# investigation
The production backend was verified healthy from outside, during the reported outage window:

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

# still required outside this repository
1. **Give the user an account.** Even a fully working Google Sign-In only gets an unknown identity
   as far as the access-request screen; an admin still has to approve the request
   (`/api/user-requests`) or create the account directly. Until then, no login method can succeed.
2. **Check the Google Cloud Console OAuth configuration** for the project holding
   `GOOGLE_CLIENT_ID`:
   - If the OAuth consent screen is still in **Testing** publishing status, only accounts on its
     test-user list can sign in — a brand-new user failing where the owner succeeds is the
     signature of exactly that. Add the user, or publish the consent screen.
   - Confirm the Android OAuth client for `nl.teunschriks.mumamobile` still exists and its SHA-1
     matches the current release keystore, and register the release keystore's SHA-1 for
     `nl.teunschriks.mumamobile.debug` as well (see docs/deployment.md).
