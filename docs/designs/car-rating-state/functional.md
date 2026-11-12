# Car Rating State: Functional Design

## Overview

The rating button in Android Auto always starts from the real rating of the track. Each tap moves
one step: 0, 1, 2, 3, 4, 5, then back to 0. Before this change, a queue that the phone's web player
built had no ratings, so the car showed 0. The first tap wrote 1 over the real rating (issue #256).
On 2026-11-12 a track with rating 4 got the values 1 to 5 from the car within one second.

Now the car knows the rating, or it gets the rating before the first tap is used.

## User Stories

- As a listener in the car, I want the rating button to show the rating the track has, so that a
  tap moves it one step up from that rating.
- As a listener, I want a rating I make in the web player or on another device to show in the car,
  so that the next tap in the car starts from it.
- As a listener without a connection, I want the downloaded tracks in the car to show their last
  rating, not the rating from the day of the download.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| The web player queues a track with rating 4. | The car button shows the rated icon. One tap gives 5. |
| The web player queues a track without a known rating. | The car button shows no stars. When the track starts, the app asks the server and the button changes to the real rating. |
| You tap the button before the app knows the rating. | The app gets the rating first (server, then the app's copy of the server data, then the downloaded library) and steps from it. Three quick taps give three steps. |
| No source knows the rating (no connection, track not downloaded). | The tap does nothing. The app never guesses 0. |
| You rate the playing track in the web player. | The car button changes at once. The server gets one write, not two. |
| Another device changes the rating of a queued track. | The car shows the new rating when that track starts. |
| You rate a track in the car, then browse the downloaded library offline. | The list shows the new rating. |

## Acceptance Criteria

1. The web player queues a track rated 4 and you play it in the car. The button shows the rated
   icon, and one tap sets 5.
2. A tap never writes 1 over a rating that the car did not know.
3. A rating changed in the web player shows on the car button without a track change.
4. A rating changed on another device shows in the car when the track starts.
5. A rating in the web player causes exactly one server write.
6. Offline car lists show the last rating that the phone knows.

## Open Questions / Not Yet Decided

- None. The owner chose the full fix on 2026-11-12.
