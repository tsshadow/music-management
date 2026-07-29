# title: Ultrasonic Google Sign-In showed a generic network error when no Google account exists on the device

# status: fixed

# reported problem
Testing the "Sign in with Google" flow in an emulator (Genymotion/Android Studio simulator,
no Google account added) surfaced the generic "A network error occurred. Check the server
address and try again later." message, both from the welcome-screen button
(`NavigationActivity.performWelcomeGoogleSignIn()`) and from the server-edit screen
(`EditServerFragment.startGoogleSignIn()`). This is misleading: no network request is even made
in this case, and the actual missing pieces (no Google account on the device, or a missing/
misconfigured `GOOGLE_WEB_CLIENT_ID`) were not distinguishable from a real backend outage.

# Possible reason
`CredentialManager.getCredential()` throws distinct, typed exceptions for different failure
modes, but both call sites only had a single, catch-all `catch (e: Exception)` branch that
always displayed the generic network-error string:
- `NoCredentialException` is thrown when the device has no Google account registered (the
  exact case hit during simulation) — this was indistinguishable from a real network failure.
- `GetCredentialCancellationException` is thrown when the user dismisses the account picker —
  this was also (harmlessly, but incorrectly) reported as a network error.
- Additionally, `GOOGLE_WEB_CLIENT_ID` defaults to `"placeholder-id"` (see `ultrasonic/build.gradle`)
  when the corresponding CI/CD or local `.env`/`local.properties` value is not set, which makes
  every Google Sign-In attempt fail regardless of the device's account state, with no diagnostic
  trace pointing at the misconfiguration.

# solution
Added explicit `catch` branches, in both `NavigationActivity.performWelcomeGoogleSignIn()` and
`EditServerFragment.startGoogleSignIn()`, ordered before the generic `catch (e: Exception)`:
- `GetCredentialCancellationException`: silently return (user-initiated cancellation, not an
  error).
- `NoCredentialException`: log at `Timber.e` and show the new, specific
  `R.string.google_signin_no_accounts` ("No Google accounts found on this device.") message/
  toast instead of the generic network-error string.
- Also added a `Timber.e` warning, logged before the Credential Manager flow starts in both
  call sites, whenever `BuildConfig.GOOGLE_WEB_CLIENT_ID == "placeholder-id"`, so a
  misconfigured build is immediately visible in the logs instead of only manifesting as a
  downstream sign-in failure.

To fully resolve the "no Google account" case end-to-end (as opposed to just reporting it
clearly), a Google account still needs to be added to the test device/emulator, and
`GOOGLE_WEB_CLIENT_ID` must be a real, non-placeholder client ID at build time (see
`docs/deployment.md` / the `release:check-secrets` CI job for where this is wired in from
`PROD_ENV_FILE`'s `GOOGLE_CLIENT_ID`) — those are environment/device setup steps outside of
this app-code fix.
