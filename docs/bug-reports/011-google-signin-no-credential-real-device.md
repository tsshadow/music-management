# title: Ultrasonic Google Sign-In still fails with "No Google accounts found" on a real device with a real account

# status: fixed

# reported problem
Even after bug 010's fix (which correctly distinguishes `NoCredentialException` from a real
network error) and after confirming `GOOGLE_WEB_CLIENT_ID` is set to the real production Google
OAuth Web Client ID (not the `"placeholder-id"` default), "Sign in with Google" still fails with
the `google_signin_no_accounts` message ("No Google accounts found on this device.") on both an
Android Studio emulator *and* a real physical phone that has a real Google account already signed
in. Logcat shows Android's `CredentialManager` reaching Google's remote `GoogleIdService` (not
failing purely locally) and getting back `status: CANCELED, source: REMOTE_PROVIDER`, which
`androidx.credentials` then surfaces as `NoCredentialException` — the same exception bug 010's fix
already maps to this message, so the message itself was accurate but misleading about the actual
cause: this is not "no account on the device", it's Google's backend refusing to hand out a
credential to this app at all.

# Possible reason
`docs/deployment.md` and `docs/designs/authentication/technical.md` documented (incorrectly) that
Ultrasonic needs no separate Android OAuth client / SHA-1 registration, on the assumption that
reusing the Web OAuth Client ID as `GetGoogleIdOption`'s `serverClientId` is sufficient by itself.
In practice, two independent gaps combine to produce exactly this symptom:

1. **No Android-type OAuth client registered.** Google's Credential Manager backend for native
   Android "Sign in with Google" will not issue a credential to a calling app unless an
   **Android**-type OAuth client (application package name + signing certificate SHA-1
   fingerprint) also exists in the same Google Cloud project as the Web client ID — even though
   that Android client ID is never referenced anywhere in code. Only a Web client ID had been
   created for this project, so Google's backend had nothing to match the calling app
   (`nl.teunschriks.mumamobile` / `nl.teunschriks.mumamobile.debug`) against, and returned
   `CANCELED` regardless of the device's account state or how correct the rest of the
   configuration was.
2. **Wrong Credential Manager option for a first-time sign-in.** Both call sites
   (`NavigationActivity.performWelcomeGoogleSignIn()`, `EditServerFragment.startGoogleSignIn()`)
   used `GetGoogleIdOption` with `setFilterByAuthorizedAccounts(false)`. In practice
   `GetGoogleIdOption` only reliably returns a credential for an account that has already
   authorized this exact app before; for a genuinely first-time sign-in (this app's real-device
   testing had never succeeded yet) it still throws `NoCredentialException` even with
   `setFilterByAuthorizedAccounts(false)` set. `GetSignInWithGoogleOption` is Google's dedicated,
   newer option for this "not yet authorized" case and reliably shows the account chooser instead.

# solution
- Switched both call sites from `GetGoogleIdOption` to `GetSignInWithGoogleOption(GOOGLE_WEB_CLIENT_ID)`
  (`EditServerFragment.startGoogleSignIn()`, `NavigationActivity.performWelcomeGoogleSignIn()`).
- Corrected `docs/deployment.md`'s "Google Sign-In on Ultrasonic (Android)" section and
  `docs/designs/authentication/technical.md`'s "Cross-App Impact" section, which both previously
  stated no separate Android OAuth client/SHA-1 was needed — this is now documented as a required
  step.
- **Manual, one-time step still required in Google Cloud Console** (not something code/CI can do):
  create two Android-type OAuth client IDs in the same project as the existing Web client
  (`GOOGLE_CLIENT_ID`/`VITE_GOOGLE_CLIENT_ID`):
  - `nl.teunschriks.mumamobile` with the release keystore's SHA-1 fingerprint (official builds).
  - `nl.teunschriks.mumamobile.debug` with the debug keystore's SHA-1 fingerprint (local/debug
    builds).
  Until this manual step is done, Google Sign-In on Ultrasonic will keep failing with
  `google_signin_no_accounts` regardless of the code fix above, since the missing Android OAuth
  client registration is the more fundamental of the two causes.
