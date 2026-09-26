# Account Settings Merge — Functional Design

## Overview

Some settings follow the account rather than the device: favourite genres, labels and playlists,
the interface language, the home-screen counts, the track page size and where each DJ set was left
off ("set resume"). They are stored on the server as one document per account (the `frontend`
settings blob), and every device signed in to the account writes it: the web player, the app on a
phone, the app on a tablet.

Until now a device could only replace that document whole. Each write read it, changed its own
keys and sent the complete document back, so when two devices saved at about the same time the
second one sent a copy without the first one's change, and that change was gone (GitLab issue #39,
[bug report 116](../../bug-reports/116-account-settings-blob-last-writer-wins.md)). The web player
already made the race rare by batching its own writes ([bug report 041](../../bug-reports/041-web-player-keeps-the-previous-users-state.md)),
but it could not prevent a phone and a browser from overwriting each other.

This change lets a device send only the settings it changed. The server merges them into the stored
document, so a change another device made to a different setting stays.

## User Stories

- As a listener with the web player open on my laptop and the app on my phone, I want a setting I
  change on one of them to stay changed even when the other one saves something at the same moment.
- As a listener using an older app version, I want settings sync to keep working after the server
  update, even before I install the new app.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| The phone saves favourite genres while the browser saves the interface language, at the same moment | Both changes are on the account afterwards; reloading either device shows the new genres and the new language. |
| One device changes a setting another device has open on screen | The other device picks up the change the next time it loads the account's settings (at sign-in or reload), as before. |
| Two devices change **the same** setting at the same moment | The one that reaches the server last wins, as before. Nothing else is lost. |
| An older app version saves its settings the old way (whole document) | Still accepted. It can still overwrite another device's change made at the same moment -- that is what the new version fixes. |
| A new web player or app talks to a server that does not have the per-setting write yet | It falls back to the old whole-document write, so saving keeps working during a rollout. |
| Saving fails (offline, server error) | As before: the web player keeps the change and retries; the app keeps its local copy and retries on its next save or launch. |

## Acceptance Criteria

1. Changing setting A on one device and setting B on another at the same moment leaves both A and
   B changed on the account.
2. A save from the web player or the new app never sends settings it did not change.
3. An older app version that sends the whole document keeps working unchanged.
4. A new client against a server without the per-setting write still saves its change.
5. When two devices change the same setting at once, the last save wins and no other setting is
   affected.

## Open Questions / Not Yet Decided

- None. Deliberately out of scope: merging *inside* one setting. "Set resume" is one setting holding
  the positions of many sets; two devices each saving a different set's position at the same
  moment can still overwrite each other's entry. That needs two devices playing different sets at
  once and costs one resume position, which is why it was not built now.
