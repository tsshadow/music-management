# Offline mode follow-ups: Android Auto and queued ratings — Functional Design

## Overview

Two gaps the app start reachability check ([`app-start-reachability/`](../app-start-reachability/))
left open on purpose, both in the Android app. Issue #149; Teun agreed the approach in the issue.

1. Android Auto used the downloaded library only when the listener had chosen "Offline verder". A car
   that connected while the home server was down for another reason got a network timeout on every
   list: a cold start in the car, or a phone that waits on "Wachten op server".
2. A rating given while the server was out of reach failed and was lost. Listens already wait on the
   phone and go out later (bug report 071). Ratings now do the same.

## User Stories

- As a listener who starts the car while the home server is off, I want the car to show my downloaded
  music at once, so that I do not get an error or endless loading on each list.
- As a listener in the car whose server comes back during the drive, I want the car to use the server
  again by itself.
- As a listener in offline mode, I want a rating I give to be kept and sent later, so that I do not
  have to rate the track again.
- As a listener who changes their mind, I want the last rating I gave to be the one the server gets.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| Car connects, server answers | Unchanged: the car shows the server's library. Connecting costs one ping round trip. |
| Car connects, server down or no network (offline mode not chosen) | The car waits at most 3 s, then shows the downloaded library. |
| Phone waits on "Wachten op server", car connects | The car shows the downloaded library, because the phone's last attempt found no server. |
| Car shows the downloaded library, server comes back | The car checks again in the background, every 20 s while it browses. The next list after a good answer comes from the server. |
| An "unreachable" answer older than 2 minutes | No longer trusted: the car asks the server again. |
| Offline mode chosen | Unchanged: the car shows the downloaded library until offline mode ends. |
| Rating given in offline mode (phone screen, car, notification) | The stars change at once. The phone shows "Beoordeling bewaard, gaat naar de server zodra die weer bereikbaar is". |
| Rating given while the connection drops (no answer, or a proxy answers 502/503/504) | The same: the stars stay and the rating waits on the phone. |
| The server refuses a rating | Unchanged: the stars go back and the phone says the rating was not saved. |
| The same track rated 3, then 5, while offline | The server gets only the 5. |
| Server answers again | Waiting ratings go out at once, oldest first. Also after the app was closed: the next start sends them. |
| A rating that cannot go out for 30 days | It is dropped, the same limit as for listens. |
| A browser tab | Unchanged: a browser has no queue, so a rating that fails goes back. |

Rating 0 clears a rating, 5 is a favorite, and 1 is only a rating: a low rating never removes
anything.

## Acceptance Criteria

1. With the server stopped and the app closed, connecting Android Auto shows the downloaded library
   within a few seconds, without error messages on the lists.
2. With the phone on "Wachten op server", connecting Android Auto shows the downloaded library.
3. With the car on the downloaded library, starting the server makes the car show the server's
   library again within about half a minute of browsing.
4. With the server reachable, the car behaves as before.
5. In offline mode, rating a track on the phone keeps the new stars and shows the "bewaard" message;
   once the server is back, the server has that rating.
6. Rating the same track twice while offline leaves only the last rating on the server.
7. A rating given in offline mode, followed by closing the app, still reaches the server after the
   next start with the server reachable.

## Open Questions / Not Yet Decided

- When the car changes from the downloaded library back to the server, the lists already on the car
  screen are not refreshed. The next list the listener opens comes from the server.
- A rating waits for the server it was given on. A rating given while the hand-picked offline library
  was active goes to the next server that is active.
