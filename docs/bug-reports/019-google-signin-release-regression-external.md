# title: Ultrasonic "Sign in with Google" fails again on the release APK after previously working

# status: mitigated (no code root cause found; hardened against recurrence, external cause suspected)

# reported problem
On the latest release APK, "Sign in with Google" on the welcome screen consistently fails with
"Google sign-in failed". Manual username/password login on the same screen also errors once but
then succeeds after fully closing and reopening the app; Google Sign-In does not recover the same
way. This flow had previously worked end-to-end (bugs 009-013 all already fixed and unchanged since
release 0.0.33/0.0.40).

# investigation
- `NavigationActivity.performWelcomeGoogleSignIn()`, `isServerReachable()`, and
  `showWelcomeDialog()` have not changed since release 0.0.40 - no application-code regression was
  introduced after the last confirmed-working state.
- The backend's `/api/auth/google` handler (`_verify_google_id_token()`,
  `services/music_manager/routers/user_requests.py`) and the CI wiring that injects
  `GOOGLE_WEB_CLIENT_ID`/the release signing keystore (`scripts/ci/ultrasonic-build-upload.sh`)
  have not changed since well before 0.0.33.
- The release signing keystore itself has been stable since release 0.0.21 (see release notes for
  that version) - no evidence of a keystore rotation that would invalidate the release-keystore
  SHA-1 already registered against the Android-type OAuth client (see bug 011).
- No CI/CD variable values or Google Cloud Console state can be inspected from this environment
  (secrets are out of scope for automated access here).

# possible reason
Since no code path changed, the most likely causes are external to this repository:
1. The Android-type OAuth client registration in Google Cloud Console (bug 011) was edited,
   deleted, or the project's OAuth consent screen configuration changed.
2. A Google Play Services update on the test device changed `CredentialManager`/
   `GetSignInWithGoogleOption` behavior - this is not controllable from the app.
3. Whatever the underlying cause, it isn't cleared by an app restart the way the
   username/password failure is, which fits Google Sign-In talking to Play Services/Google's
   backend directly rather than only this app's own (recoverable) local state.

# solution
No code fix was possible without a confirmed code-level root cause. Instead:
- Hardened `performWelcomeGoogleSignIn()`'s failure logging to include the concrete exception class
  and, for a failed `/api/auth/google` call, the HTTP status/body - so the *next* occurrence is
  diagnosable from `adb logcat` without a live repro session.
- The welcome dialog is no longer a hard lockout on login failure regardless of cause: a
  secondary, confirmed "skip" action switches to the app's existing offline mode, and an
  always-visible connectivity status line makes it clear up front whether the *server* or the
  *login* is the problem. See
  `docs/superpowers/specs/2026-07-30-ultrasonic-login-flow-design.md`.

# manual verification still needed (outside this repository)
- In Google Cloud Console, confirm the Android-type OAuth client for `nl.teunschriks.mumamobile`
  still exists and its SHA-1 fingerprint matches the current `SIGNING_STORE_FILE` CI/CD variable
  (`keytool -list -v -keystore <keystore.jks> -storepass <password> -alias <alias> | grep SHA1`,
  see `muma-ops docs/deployment-production.md`'s "Google Sign-In on Ultrasonic (Android)" section).
- Confirm the OAuth consent screen's publishing status and test-user list haven't changed.
- Capture `adb logcat` from a failing device the next time this reproduces, now that the failure
  path logs the concrete exception type/HTTP status.
