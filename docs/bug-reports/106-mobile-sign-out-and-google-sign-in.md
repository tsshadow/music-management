# title: MuMa Mobile: "Uitloggen" does nothing, and "Sign in with Google" is missing from the app

# status: fixed

# reported problem
Reported by Teun on 2026-09-26, app 7.5.2 against server 0.77.0:

1. "Uitloggen werkt 100% niet" -- tapping "Uitloggen" in the profile menu does not sign out.
2. "Inloggen via Google lijkt niet te werken" -- Google sign-in does not seem to work on the phone;
   it was not even clear the app offers it.

# Possible reason

**1. Sign-out: the native half crashed on the wrong thread.** The web UI's logout
(`ProfileButton.handleLogout`) first awaits `platform.system.signOut()`, which is the Capacitor
plugin method `MumaSystemPlugin.signOut`. That method called `mediaPlayerManager.clear()` first,
directly on the thread Capacitor runs plugin methods on -- a background handler thread.
`MediaPlayerManager` wraps a Media3 `MediaController`, and every `MediaController` method throws
`IllegalStateException` ("called from a wrong thread") off its application (main) thread;
`clear()` reads `mediaItemCount` for its log line before anything else, so it threw at once
whenever the controller was connected -- which `MediaPlayerLifecycleSupport` does when the app
starts. The
exception escaped the plugin method; Capacitor 8.5.2's `Bridge.callPluginMethod` logs "Serious
error executing plugin" and rethrows it as a `RuntimeException` (checked in the shipped
`com.capacitorjs:core:8.5.2` bytecode). So:
- `activeServerProvider.signOut()` on the next line never ran: the password, MuMa key and tokens
  stayed on the phone;
- the JavaScript promise never settled, so `handleLogout` never got past its first `await` -- no
  store was cleared and no reload happened; the button visibly did nothing, or the app process died
  and came back signed in from the untouched native credentials.

Every other `MediaPlayerManager` caller in the plugins posts to the main thread
(`MumaPlayerPlugin.onMain`); `signOut` was the one that did not. The existing tests mocked the
bridge on the web side and tested `ActiveServerProvider.signOut` on its own, so neither saw the
thread. A second, latent weakness: even a native failure that did settle left the password on the
phone, and `restoreSession` on the next boot would sign straight back in with it.

**2. Google sign-in: not offered at all in the app.** Established from the shipped artefacts:
- The release APK 7.5.2 (`muma-mobile-v7.5.2-334.apk` from apk-hoster) bundles
  `assets/public/assets/index-CRc5FX-o.js`, the same bundle `frontend:bundle` built for
  `release/0.77.0`. It contains no Google Identity Services script and no `googleBtn`: the login
  page renders its Google button only when `VITE_GOOGLE_CLIENT_ID` is set at build time, and
  `scripts/ci/frontend-bundle.sh` never sets it (only the LMS image build gets it, from
  `PROD_ENV_FILE_LMS`). So the app shows no Google option.
- Setting it would not have helped: Google's web sign-in refuses to run in an embedded WebView
  (`disallowed_useragent`), and the shell's origin `https://localhost` is not an authorised
  JavaScript origin.
- The native implementation that used to exist (`NavigationActivity.performWelcomeGoogleSignIn`,
  `EditServerFragment.startGoogleSignIn`, Credential Manager with `GetSignInWithGoogleOption`) was
  deleted with the legacy Kotlin UI (3a1f811ad, MR !783) without a replacement, while
  `docs/designs/authentication/technical.md` still said the app supports native Google sign-in.
  The dependencies (`androidx.credentials`, `googleid`) and `BuildConfig.GOOGLE_WEB_CLIENT_ID`
  stayed; the release build log of 7.5.2 has no "GOOGLE_CLIENT_ID not found" warning, so the client
  ID is available to release builds.
- Production confirms nobody reached the backend: `docker logs --since 7d music-manager` has no
  `/api/auth/google` request.
- The release APK's signing certificate is `CN=Ultrasonic, OU=MuMa, O=example.com`, SHA-1
  `C2:5C:21:2B:E3:BC:25:00:88:FA:6A:9D:86:C0:2E:AD:EC:B2:D9:5A` (public fingerprint, read with
  `keytool -printcert -jarfile`). Native Google sign-in only works when an Android-type OAuth
  client for `nl.teunschriks.mumamobile` with that SHA-1 exists in the same Google Cloud project as
  the Web client (bug report 011). Whether it still does cannot be read from here.

# solution

Design: [docs/designs/mobile-sign-out-and-google/](../designs/mobile-sign-out-and-google/functional.md).

Sign-out:
- `MumaSystemPlugin.signOut` runs on the main thread through `PluginCallScope`, and the steps live
  in `SessionSignOut`: credentials first (they are what must happen), then the queue, whose failure
  is logged and no longer costs the sign-out. The call always settles.
- `RESTMusicService.refreshSubsonicToken` drops a token that arrives after the password was
  cleared, so a refresh started at boot cannot write the Subsonic token back after a sign-out.
- Web: `handleLogout` bounds its wait for the phone at 5 s and, after resetting every persisted
  store, sets a device-level `signedOut` marker (`muma_signed_out`). `restoreSession` honours it:
  no silent sign-in from the phone's credentials, the phone is asked to sign out once more, and the
  login page appears. The next successful sign-in (password or Google) clears it. Browser logout is
  unchanged apart from the marker, which a browser never reads.

Google sign-in:
- New plugin methods `googleSignInAvailable` and `googleSignIn` (`capacitor/GoogleSignIn.kt`):
  Credential Manager with `GetSignInWithGoogleOption(BuildConfig.GOOGLE_WEB_CLIENT_ID)`, the Google
  ID token parsed from the `CustomCredential`, failures mapped to `cancelled` / `no-credential` /
  `failed:<exception class>`.
- `LoginPage` in the shell shows a native "Inloggen met Google" button (style guide updated) only
  when the build has a client ID, never loads Google's web script there, and sends the token
  through the existing `handleGoogleResponse` → `POST /api/auth/google`. A successful Google
  sign-in now also hands the pair to the phone (`saveCredentials`), so downloads and Android Auto
  share the session -- the "known gap" the old code comment described.
- No backend change: the token's audience is the Web client ID the backend already verifies.
- Outside the repository: the Android OAuth client registration has to be checked in Google Cloud
  Console -- `scripts/prod/person/register-android-google-client.sh` and a `needs-person` GitLab
  issue.

Tests: `SessionSignOutTest`, `MumaSystemPluginSignOutTest` (calls `signOut` from a background
thread and asserts both steps ran on the main thread), `GoogleSignInTest`,
`profileButtonLogout.test.js`, `nativeSession.test.js`, `loginPageNativeGoogle.test.js`,
`platformCapacitor.test.js`.
