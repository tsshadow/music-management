# Mobile sign-out and Google sign-in — Functional Design

See [docs/designs/README.md](../README.md) for the process. Technical half:
[technical.md](technical.md). Bug report: [106](../../bug-reports/106-mobile-sign-out-and-google-sign-in.md).

## Overview

Two things on the MuMa Mobile login were broken after the app's screens moved to the web UI
(Capacitor shell, app 7.x):

- **Logging out did nothing.** Tapping "Uitloggen" left the user signed in (or restarted the app
  signed in).
- **"Sign in with Google" was gone.** The authentication design says the app offers Google sign-in
  ([authentication/technical.md](../authentication/technical.md)), and the old Kotlin screens did.
  The web login page that replaced them only shows Google's web button, which the app's build does
  not include and which Google blocks inside an app's embedded browser anyway.

This design restores both, and makes the logout robust against the phone half failing.

## User Stories

- As a listener on the phone, I want "Uitloggen" to sign me out, so that I can switch accounts or
  hand the phone to someone else.
- As a listener with a Google account, I want to sign in to the app with Google, as I can on the
  website, so that I do not need a separate password.
- As a listener in a browser, I want logging out and Google sign-in to keep working exactly as
  before.

## Functional Flows

### Logging out

| Situation | Observable outcome |
|---|---|
| The user taps "Uitloggen" in the app | Playback stops, the queue is emptied, and the login page appears. Downloads stay. |
| The user closes and reopens the app after logging out | The login page appears; the app does not sign itself back in. |
| The phone's own part of the logout fails or hangs | The login page still appears within a few seconds, and the app still does not sign itself back in on the next start. |
| The user signs in again (password or Google) | The next app start signs in silently again, as before. |
| The user logs out in a browser | Unchanged: the login page appears and nothing of the session is left in the browser. |

### Google sign-in in the app

| Situation | Observable outcome |
|---|---|
| The app was built with Google sign-in configured | The login page shows "Inloggen met Google" below the password form, separated by "OF". |
| The app was built without it | No Google button; the password form only. |
| The user taps the button | Android's own Google account chooser opens over the app. |
| The user closes the chooser | Nothing happens; no error. |
| The Google account belongs to an account | The user is signed in, and downloads and Android Auto use the same session. |
| The Google account is unknown | The access-request screen appears, as on the website. |
| Google gives no account (none on the phone, or the app is not registered with Google) | A message says so in plain words. |
| Anything else fails | A message with the technical reason, so a screenshot is enough to diagnose it. |
| In a browser | Unchanged: Google's own button on the login page. |

## Acceptance Criteria

1. After "Uitloggen" in the app the login page appears, and it still appears after closing and
   reopening the app.
2. Logging out works even when the phone's own sign-out fails or never answers.
3. After signing in again, the app signs in silently on the next start.
4. A release APK built with the Google client ID shows "Inloggen met Google"; tapping it and picking
   a known account signs the user in.
5. A build without the client ID shows no Google button.
6. Browser logout and browser Google sign-in behave as before.

## Open Questions / Not Yet Decided

- Whether the Android-type OAuth client for `nl.teunschriks.mumamobile` and the release certificate
  SHA-1 is still registered in Google Cloud Console cannot be checked from the repository. The code
  works without it only in the sense that it says so: Google answers "no account". A person checks
  it with `register-android-google-client.sh` (GitLab issue #78,
  `needs-person`).
- The style guide asks for a confirmation before logging out; the web UI's logout has never had
  one. Not changed here; GitLab issue #80 (`decision`).
