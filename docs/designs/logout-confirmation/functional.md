# Logout confirmation — Functional Design

## Overview

Logging out stops playback, empties the queue and forgets the account's session on this device.
Until now the profile menu's "Log out" row did that on a single tap, which contradicted the style
guide's Session controls rule ("it always confirms first, stating what is lost and what is kept").
Issue #80 asked whether to add the confirmation or drop the rule; the decision was to add it. It
applies to the web player and to the app, which runs the same web UI inside its Capacitor shell.

## User Stories

- As a listener, I want a stray tap on "Log out" to ask before it stops my music, so that I do not
  lose my queue by accident.
- As an app user, I want to know that my downloads stay on the phone when I log out, so that I am
  not afraid to switch accounts.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| Profile menu -> "Log out" | The menu closes and a "Log out?" dialog opens. Nothing else happens yet. |
| Dialog in a browser tab | Says playback stops and the queue is cleared. |
| Dialog in the app | Says the same, plus that downloads stay on this device. |
| "Cancel", Escape, the close button or a tap on the backdrop | The dialog closes; playback, queue and sign-in are untouched. |
| "Log out" in the dialog | The existing logout runs, unchanged: the login page appears. A second tap does nothing extra. |

## Acceptance Criteria

1. No path logs out without the dialog first; the profile menu is the only logout entry point in
   the web UI and the app (Android Auto has none).
2. Cancelling in any way changes nothing.
3. Confirming logs out exactly as before the change.
4. The dialog reads correctly in Dutch and English, on phone, tablet and desktop widths.

## Open Questions / Not Yet Decided

- None. The browser leaves out the "downloads stay" line because a browser tab has no downloads;
  promising something that does not exist there would be wrong.
