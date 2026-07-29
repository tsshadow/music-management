# title: Ultrasonic welcome-screen Google Sign-In succeeds but the dialog never closes ("keeps requiring login")

# status: fixed

# reported problem
After bug 011's fixes (real Android OAuth client registered, `GetSignInWithGoogleOption` in use),
the Google account picker on the very first welcome screen now opens correctly and the user can
pick an account, but the welcome dialog then never closes — the app keeps behaving as if login is
still required, exactly as before. The expectation (confirmed against the web frontend, where
"Sign in with Google" is a full alternative to username/password login with no extra verification
step) is that a successful Google sign-in should close the dialog immediately, the same as it does
in `EditServerFragment.performMumaGoogleAuth()` elsewhere in the app.

# Possible reason
`NavigationActivity.performWelcomeGoogleSignIn()`'s `"ok"` branch was written by copying the
manual username/password submit handler (`showWelcomeDialog()`'s positive-button click listener,
just above it in the same file), including its `MusicServiceFactory.getMusicService().ping()`
connectivity check gating whether the dialog is allowed to dismiss. That gate makes sense for
manual entry — the app has no other way to know whether arbitrary user-typed credentials are
actually correct. It does not make sense for Google Sign-In: `/api/auth/google` returning
`status: "ok"` already *is* a server-verified, guaranteed-valid credential (the same trust model
`EditServerFragment.performMumaGoogleAuth()` and the web frontend's `handleGoogleResponse()` both
already rely on — neither of them re-verifies with a ping). If that `ping()` call failed for any
transient/unrelated reason (a cold OkHttp client on a fresh app process, first-connection
timing, etc.), the code discarded an already-successful Google sign-in and left the user back at
the login dialog with no useful indication that the actual cause had nothing to do with their
Google account.

# solution
Removed the `ping()`-gated success/failure branching from `performWelcomeGoogleSignIn()`'s `"ok"`
case. It still performs the same server-activation bookkeeping (`Settings.staticUserName/Password`,
`activeServerProvider.invalidateCache()`/`setActiveServerById(0)`, `MusicServiceFactory.resetMusicService()`)
since that's still needed to wire up the newly-created server entry, but a failure there is now
logged (`Timber.e`) rather than blocking dialog dismissal — the dialog now always closes on a
`status: "ok"` response, matching `EditServerFragment.performMumaGoogleAuth()` and the web
frontend exactly.
