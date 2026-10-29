# Mobile Scrobbling — Functional Design

## Overview

The app is the only thing that reports what is played on the phone and in the car. Since 0.72.1
the web player inside the app no longer scrobbles (it doubled every listen, bug report 035), and
the app's own scrobbler turned out to lose listens the web player used to cover: a failed send was
dropped, a play only counted once the track was left, a play that outlived its process was never
reported, a playback that started without the app's screen (the car, the notification) was not
watched at all, offline listens were thrown away, radio and news were sent under ids the server
refuses, and a track played twice in a row counted once.

This design makes every qualifying play on the phone reach the server exactly once, however the
play ends and whatever the network is doing. Bug report 071 has the evidence and the causal chain.

## User Stories

- As a listener, I want every track I actually listened to in the app or in the car to appear in
  my history and statistics, even when I skip it, lose the network, or the phone kills the app.
- As a listener, I want each listen to appear once, never twice.
- As the curator of the history, I want a listen to be dated at the moment it started, the same
  moment LMS records, so the two histories can be compared and repaired.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| A track plays for at least 5 seconds, then I skip | One listen, dated at the start of the track, with the seconds actually played |
| A track plays for less than 5 seconds, then I skip | No listen |
| A track plays to the end and the next one starts | One listen for the finished track |
| The last track of the queue ends | One listen for it |
| I pause, wait, and resume | Paused time does not count as played time |
| A restored queue sits paused for hours before I press play | The listen is dated when I pressed play |
| The same track plays twice in a row | Two listens |
| Playback starts from the car or the notification without opening the app | Listens are recorded exactly as when the app is open |
| The phone has no network, or the app is in offline mode | Listens are kept on the phone and sent as soon as the server is reachable again |
| The server answers with an error | The listen is kept and sent again later |
| A send reached the server but the answer got lost | Sending it again changes nothing on the server: still one listen |
| The phone kills the app in the middle of a long set | The set is recorded with the time played up to the last few seconds, the next time the app runs |
| A radio channel plays a track | The listen is recorded for that library track |
| A news bulletin plays | No listen |
| Scrobbling is switched off in the settings | Nothing is recorded or queued |

## Acceptance Criteria

1. A play of 5 seconds or more is recorded once, whether it ends by a skip, an automatic advance,
   the end of the queue, a cleared queue or the app being stopped.
2. A play shorter than 5 seconds is never recorded.
3. A listen made without network appears in the history once the phone is back online, without
   opening any screen.
4. A listen whose app process was killed mid-play appears in the history after the app next runs.
5. Repeating a send never creates a second listen.
6. The listen's time in MuMa equals LMS's listen time for the same play.
7. Radio plays are recorded as their library track; news bulletins are not recorded.

## Open Questions / Not Yet Decided

- **Listens LMS recorded but failed to relay to MuMa.** Bug report 071 shows the three missing
  listens of 2026-09-25 reached LMS; LMS's relay to MuMa gave up on them. This design makes the
  app's side durable and makes relay retries harmless (the start time is fixed). LMS's relay is
  now durable as well. MuMa pulls recent LMS-only listens on a schedule (bug report 075), and
  since issue #67 LMS also
  keeps an outbox of listens it has not yet delivered; see
  [docs/designs/lms-listen-outbox/](../lms-listen-outbox/functional.md). Settled.
