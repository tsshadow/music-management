# Playback Error Recovery — Functional Design

## Overview

When a track in the queue fails to load or play, MuMa Mobile tries it once more from a fresh copy.
If that fails too, it goes on to the next track. Before this, the first error stopped the player,
and Android Auto showed a play error with the rest of the queue unplayed.

This applies to every way of listening on the phone: the app, the notification and Android Auto.
All three control the same player session, so the car gets no separate rule.

## User Stories

- As a driver, I want a broken track to be skipped, so that the music continues without me
  touching the car screen.
- As a listener, I want a track with a bad downloaded copy to play from the server, so that one
  corrupt file does not cost me the track.
- As a listener with no connection, I want the player to stop after a few failures, so that it does
  not walk through my whole queue in silence.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| A track fails to load or stops with an error. | The app drops the cached copy, if there is one, and starts the track again at the same position from the server. A new download of the track starts. |
| The second attempt of that track fails too. | The player goes on to the next track and plays it. |
| The failed track is the last one in the queue. | The player stops, paused, and shows the error. |
| Three tracks in a row fail after their second attempt (for example, the server is down). | The player stops, paused, after the third track, and shows the error. |
| A track plays after its second attempt, then fails again later. | The player goes on to the next track. There is no third attempt. |
| A track is a saved (pinned) download. | The saved file is never deleted. The second attempt loads the same file again. |
| The app is in offline mode. | Nothing is deleted, because there is no server for a new copy. The second attempt loads the same file again. |
| The player is the server jukebox. | No change: the jukebox switches off on an error, as before. |
| The person presses play after the player stopped. | The track gets a new first and second attempt. |

## Acceptance Criteria

1. In Android Auto, a queue with one track that cannot play continues with the next track, without
   a touch on the car screen.
2. A track whose downloaded file is corrupt plays from the server on its second attempt, and a new
   file is downloaded.
3. With the server down, the player stops after at most three failed tracks and shows the error.
4. A saved (pinned) download is never deleted by this recovery.
5. Each attempt, skip and stop is a line in the diagnostics report (`action player.error`,
   `action player.recover.*`).

## Open Questions / Not Yet Decided

- The number of failed tracks before the player stops is three. Teun can change the number; it is
  one constant (`PlaybackErrorRecovery.MAX_FAILED_ITEMS`).
- The app and the web player in the app still show their "stream failed" message for each error,
  also when the recovery then plays on. Hiding that message during a recovery is not part of this
  change.
