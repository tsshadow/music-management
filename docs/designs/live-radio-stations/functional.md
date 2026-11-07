# Live Radio Stations - Functional Design

> Status: agreed on 2026-11-06 in issue #213.

## Overview

You can listen to live stations from outside MuMa, in the app, in Android Auto and in the web player.
A curator keeps the list in Beheer. A new installation has no stations until a curator adds them. You can mark a station
as a favorite, and the page shows the stations that you played last.

The name in the interface is "Radio". The channel that MuMa makes from your own library is now "MuMa
Radio". MuMa does not record, change or forward the audio. Your device connects to the broadcaster.

## User Stories

- As a driver, I want to choose SLAM, Q-dance or 538 in Android Auto, so that I can listen to live radio
  without a second app.
- As a listener, I want the same stations on my phone and in the browser, so that I do not have to look
  for them again.
- As a listener, I want my favorite stations at the top, so that I do not search a long list.
- As a driver, I want my favorites first in the car, so that I do not scroll while I drive.
- As a curator, I want to add a station or change its address in Beheer, so that a moved stream does not
  need an app release.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| You open Start in Android Auto | The Live group shows Radio, MuMa Radio and Nieuws. There are still four tabs. |
| You open Radio in the car | You see your favorites first, then the other stations, each with a logo. |
| You tap a station | The station starts at the live point. The queue stops, the same as when you start a MuMa Radio channel. |
| You open Radio under Browse in the app, or in the sidebar of the web player | The page shows Favorites, Recent and All stations as grids of logos, then the channels under MuMa Radio. A section with no stations is not shown. |
| You tap the star on a logo | The station goes into or out of Favorites, and it does not start. The list follows your account to your other devices. |
| You type in the search box | The page shows only the stations with a matching name. |
| A station that a curator added has no logo file | The tile shows the name of the station. |
| You tap the logo of the station that plays | The station stops. |
| A station plays in the player | The player shows the logo, the name and pause. It does not show a track position, stars, next, previous, shuffle, repeat, the queue or a seek bar. |
| You push pause during a station | The station pauses. |
| You push the play button during a MuMa Radio channel | The channel stops, because a channel follows a shared clock and has no pause. |
| You tap a track during a station or a MuMa Radio channel | The radio stops and the track plays. |
| A station plays in the car | The next, previous and seek buttons are not available. |
| The stream sends the title of the song (app and car) | The screen shows that title, with the station name under it. |
| The stream sends no title, or you listen in the browser | The screen shows the station name. |
| You pause and then play | You hear the live point, not the audio from the moment that you paused. |
| A station starts, or the connection stops, for example in a tunnel (app and car) | The app shows no message while it connects. It tries again for 5 minutes, then it stops and shows that the station is not available. |
| The connection stops in the browser | The player shows an error. Play connects again. |
| A news bulletin starts during a station | The station stops for the bulletin and starts again after it. |
| A station plays for a long time | No listens are recorded. It does not change your statistics or your mixes. |
| A curator adds, changes or removes a station | The new list shows the next time that a device loads it. No release is necessary. |

## Acceptance Criteria

1. In Android Auto, you can start every station from Start > Live > Radio.
2. In the app and in the web player, you can start every station from the Radio page.
3. The next, previous and seek buttons do nothing during a station, and the car shows them as not
   available.
4. An hour of listening to a station adds no listens to your history.
5. In the app and the car, after a connection loss of less than 5 minutes, the station starts again without an action from you.
6. After you pause, play continues at the live point.
7. A curator can add, change, disable and remove a station. A removed station does not come back after a
   restart.
8. A listener without the `radio.manage` permission cannot change the list.
9. A favorite stays after a restart, and shows first in the car.
10. On the phone, no error message shows when a station starts normally.

## Open Questions / Not Yet Decided

No open questions. These items are deferred, and each one can come later without a change to this design:

- Start of the last station when the car connects.
- A search through all stations of radio-browser.info.
- A spoken request to Assistant for a station.

Stations can have advertisements. MuMa does not remove them.
