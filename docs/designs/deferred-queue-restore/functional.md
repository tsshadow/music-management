# Deferred queue restore — Functional Design

## Overview

When the app opens, its web UI rebuilds the queue the phone's player (`PlaybackService`) is
holding: it asks the player for the queued track ids and looks each one up on the server, up to
200. Until issue #113 the app stayed on the boot screen ("Wachtrij herstellen…") until every lookup
had answered, which was the largest part of the start-up wait (follow-up of #107 / MR !1093).

The owner decided (issue #113): show the app first, show the restore in the mini player, fill the
mini player when the restore finishes, and let the listener start something else before then
without a late restore overwriting that choice.

## User Stories

- As a listener opening the app, I want the home screen at once, so that I can start browsing
  without waiting for my old queue to come back.
- As a listener whose music kept playing while the app was closed, I want it to keep playing,
  undisturbed, while the app restores the queue.
- As a listener who taps something new straight after opening the app, I want that to play, and
  not to be replaced a moment later by the queue the app was still restoring.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| App opens, signed in, phone has a queue | The boot screen leaves after "Inloggen…". The mini player shows a spinner and "Wachtrij wordt hersteld…"; then the playing track, with the queue behind it. |
| Music is playing while the app opens | It keeps playing throughout, at the same position. Play/pause on the mini player works during the restore. |
| The player moved on to the next track during the restore | The mini player shows the track that is playing now, not the one that was playing when the app opened. |
| Listener starts a track during the restore | It plays at once. The spinner goes away; the restore's result is discarded when it arrives. |
| Listener uses "add to queue" during the restore | The restore continues; the added track ends up behind the restored queue. |
| The phone's player holds no queue | The queue from the previous session (kept in the browser storage) comes back, paused, as before. |
| Nothing in the phone's queue resolves on the server | The mini player shows "Niets aan het afspelen"; the phone keeps its queue and keeps playing. |
| Offline start ("Offline verder") | Same flow; the tracks come from the downloaded library. |
| Browser tab | Unchanged: there is no restore. |

## Acceptance Criteria

1. The app's home screen appears before the queue restore has finished.
2. While the restore runs, the mini player (and the wide player bar on a tablet) shows a spinner and
   "Wachtrij wordt hersteld…", styled as in the styleguide ("Mini player: restoring the queue").
3. When the restore finishes, the mini player shows the track the phone is playing, and the queue
   view shows the restored queue; playback does not stop, restart or jump.
4. Starting a track during the restore plays it, and it is still playing (and shown) after the
   restore would have finished.
5. During the restore the phone's player is never given an empty or partial queue.
6. Opening the app never starts playback by itself.

## Open Questions / Not Yet Decided

- A batch lookup (one request for every queued id) would shorten the restore itself. LMS has no
  endpoint for it today (`getSongs` filters by cluster, artist, work and form, not by id); adding
  one is an LMS change and was not part of this decision.
- Measured start-up time on a device before and after: to be checked on the phone after release
  (verify issue).
