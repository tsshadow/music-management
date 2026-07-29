# title: Ultrasonic welcome-screen Google Sign-In popup can be completed but the login dialog never closes

# status: fixed

# reported problem
On a real device, tapping "Sign in with Google" on the welcome screen shows the Google account
picker as expected, and selecting an account completes it. The picker closes, but the
underlying Ultrasonic login dialog stays open and the app still demands a manual login —
functionally identical to Google Sign-In just not working, even though the account was
selected successfully.

# Possible reason
`NavigationActivity.performWelcomeGoogleSignIn()` treated a successful `"ok"` response from
MuMa's `/api/auth/google` as only provisional: after populating the username/api-key fields, it
still ran an extra `MusicServiceFactory.getMusicService().ping()` against the freshly-activated
server, and only dismissed the welcome dialog if that ping also succeeded. If the ping was slow,
raced with `activeServerProvider.setActiveServerById(0)` still propagating, or hit any transient
connectivity hiccup, the `catch` block set `pingOk = false`, which left the dialog open showing
"Could not connect to LMS" — even though the Google credential itself had already been verified
server-side by MuMa and the sign-in was, in fact, successful.

This extra verification step was copied from the manual username/password submit path
immediately above it, where a ping genuinely is the only way to check whether user-typed
credentials are valid. For the Google path, that check is redundant: MuMa's `"ok"` response
already proves the credential is valid, so gating on a second, independent network call only
added a new way for the flow to fail after the user had already succeeded.

Neither of the two other places that implement the same Google Sign-In contract behave this
way:
- `EditServerFragment.performMumaGoogleAuth()` (the server-edit screen's Google Sign-In) fills
  in the fields and shows a success toast directly on `"ok"`, with no ping.
- The web frontend's `handleGoogleResponse()` (`LoginPage.svelte`) sets the session as active
  directly on `data.status === 'ok'`, with no ping.

# solution
Removed the `ping()` gate from `NavigationActivity.performWelcomeGoogleSignIn()`'s `"ok"` branch.
Settings/active-server activation still happens the same way, but any failure there is now only
logged (`Timber.e`) instead of blocking the dialog from closing — matching
`EditServerFragment.performMumaGoogleAuth()` and the web frontend's `handleGoogleResponse()`,
neither of which re-verify a successful Google auth response before considering sign-in
complete.
