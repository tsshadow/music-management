# MuMa Mobile session control & home screen loading — Functional Design

## Overview

Three related complaints about the MuMa Mobile Android client are addressed together, because they
all concern what the app shows when it cannot yet, or can no longer, show real content.

1. **The home screen looks broken while it loads.** After starting the app the home screen stays
   empty and black for several seconds, then everything appears at once. Nothing tells the user the
   app is working.
2. **There is no way to log out.** Once signed in, the only ways out are clearing the app data or
   reinstalling.
3. **A rejected password leaves the app stranded.** If the password stops working while the user is
   signed in (it was changed on the server, or an API key was revoked), every screen fails with an
   error the user cannot act on, and the app never asks for credentials again.

The audience is every user of the Android client; there is no admin-only behavior here.

## User Stories

- As a listener, I want the home screen to show me immediately that content is on its way, so that
  starting the app does not feel like it crashed.
- As a listener, I want each part of the home screen to appear as soon as it is ready, so that a
  slow section does not hold up the rest of the page.
- As a listener, I want a log out button, so that I can leave the account on a shared or handed-over
  device, or sign in as somebody else.
- As a listener, I want to be taken back to the login screen when my password is rejected, so that I
  can sign in again instead of staring at an app where nothing works.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| App is started and the home screen opens | Every home section immediately shows grey placeholder cards ("skeletons") in the shape of the content that is coming, gently pulsing |
| One home section finishes loading | That section replaces its skeleton with real cards and its real title; the other sections keep their skeletons |
| A home section has nothing to show (e.g. no recently opened items yet) | That section disappears entirely, as before |
| A home section fails to load (server error) | That section disappears; the rest of the home screen is unaffected |
| The user returns to the home screen from elsewhere in the app | Sections already on screen stay visible while they refresh; no skeletons flash over existing content |
| The user opens the toolbar overflow menu | A "Log out" entry is shown, above "Exit" |
| The user taps "Log out" | A confirmation dialog explains that playback stops and the login screen returns; the user can cancel |
| The user confirms logging out | Playback stops, the session ends, and the login screen appears with the username still filled in |
| The server rejects the stored password while the app is in use | The session ends automatically and the login screen appears, explaining that the password was rejected |
| The server rejects a request for another reason (not found, no permission) | Nothing changes about the session; the failure is reported by the screen that made the request, as before |
| The user is in offline mode | Nothing above applies; there is no session to end |

## Acceptance Criteria

1. Starting the app on the home screen shows pulsing grey placeholders within a moment, not an empty
   page.
2. Placeholders occupy the same shape and place as the content that replaces them, so the page does
   not jump when content arrives.
3. A section that finishes first is visible while slower sections still show placeholders.
4. Returning to the home screen from another screen does not replace visible content with
   placeholders.
5. "Log out" is present in the toolbar overflow menu and asks for confirmation before acting.
6. After logging out, the login screen is shown, playback has stopped, and the previous username is
   prefilled.
7. After logging out, restarting the app still lands on the login screen (the logout is not undone
   by a restart).
8. Downloaded music is still on the device after logging out.
9. When the server rejects the password during use, the login screen appears with a message saying
   the password was rejected.
10. A permission error or a "not found" error never logs the user out.

## Open Questions / Not Yet Decided

- Logging out deliberately keeps the username so it can be prefilled. If a "clear everything"
  logout is ever wanted (for a genuinely shared device), that is a separate, additional option.
