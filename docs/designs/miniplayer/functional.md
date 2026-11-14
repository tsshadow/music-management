# Miniplayer — Functional Design

> Agreed 2026-11-12. Covers issues #177 (desktop miniplayer), #178 (Android
> picture-in-picture) and #179 (Android split screen next to Google Maps). The implementation
> contract is in [`technical.md`](technical.md). See [docs/designs/README.md](../README.md) for the
> process.

## Overview

A listener wants the music controls on screen while another app has the screen. On a bike that
other app is Google Maps. On the PC it is whatever the listener works in.

This design gives MuMa one small player, the **compact player**, and shows it in three places:

| Place | What the listener does | Issue |
|---|---|---|
| PC browser, Chrome or Edge | Clicks "Miniplayer" in the player bar. A small window opens that stays on top of every other window. | #177 |
| Phone, MuMa leaves the screen | Goes to Google Maps while music plays. MuMa shrinks to a small floating window in a corner. | #178 |
| Phone, split screen | Puts MuMa and Google Maps side by side, or taps "Navigeren naast MuMa". MuMa fills its half with the compact player. | #179 |

The three issues asked for three design folders. This is one folder, because the three places
show the same component and share most of the open choices below. Each place still ships on its
own.

Google navigation cannot go inside MuMa, and MuMa cannot go inside Google Maps: Maps shows media
controls only for its partner apps. So the two apps share the screen. That is the whole idea.

### What the phone app is today

The phone app's screens are the web player in a WebView (Capacitor, MR !783). The Kotlin app
underneath plays the music and runs Android Auto, downloads and the notification. So the compact
player is built once, in Svelte, and the phone and the PC show the same thing. The floating window
and the split screen are Android window modes: the Kotlin shell switches the window, and the web
player draws the compact layout inside it.

## User Stories

- As a cyclist, I want the track and a play/pause button next to my navigation, so that I can
  skip a track without leaving the route on screen.
- As a cyclist, I want MuMa to shrink to a corner when I open Maps, so that I still see what
  plays without opening MuMa again.
- As a cyclist, I want one tap that opens Maps next to MuMa, so that I do not have to build the
  split screen by hand at every start.
- As a cyclist, I want the screen to stay on while I ride with MuMa in half the screen, so that it
  does not go dark mid-ride.
- As a listener at the PC, I want a small player window above my other windows, so that I can
  pause or skip without looking for the browser tab.

## What the Compact Player Shows

| Element | PC window | Phone, floating window | Phone, split screen |
|---|---|---|---|
| Cover (or the artist image, or the tinted title panel, as everywhere) | yes | yes, fills the window | yes, small |
| Title and artist, one line each | yes | yes | yes |
| Play/pause | button | system button over the window | large button |
| Previous and next | buttons | system buttons over the window | large buttons |
| Progress | thin bar | no | thin bar |
| Rating (five stars) | yes | no | no |
| "Navigeren naast MuMa" | no | no | yes |
| "Volledige app" (back to the normal screens) | "back to tab" (browser's own button) | tap on the window | button |

In the floating phone window Android does not pass taps to the app. A tap shows the system's own
buttons over the window: play/pause, previous, next, expand and close. So the window itself shows
only the cover, the title and the artist.

A live radio station shows its logo and name, with play/pause only, as the mini player does today.
Nothing playing shows the "Niets aan het afspelen" line of the mini player.

## Functional Flows

### PC: the miniplayer window (#177)

| Situation | Observable outcome |
|---|---|
| Chrome or Edge 116 or newer, on a desktop | The player bar has a "Miniplayer" button next to the queue button. |
| Firefox, Safari, Chrome on a phone, the Android app | No "Miniplayer" button. |
| Listener clicks "Miniplayer" | A small window opens with the compact player. It stays above other windows. The music does not stop or restart. |
| Listener clicks play, next or a star in the window | Same result as the same button in the player bar. The player bar in the tab follows. |
| The track changes, from the tab, a media key or the window | The window shows the new track within a second. |
| Listener switches songs and sets mode in the tab | The window takes the new brand colour. |
| Listener clicks "Miniplayer" again while the window is open | Nothing new opens. There is one window. |
| Listener closes the window, or uses its "back to tab" button | The window goes. Music plays on. |
| Listener closes or reloads the tab | The window closes with it. The browser does this. |
| Listener logs out | The window closes. |

### Phone: the floating window (#178)

| Situation | Observable outcome |
|---|---|
| Music plays and the listener leaves MuMa (home gesture, or opens Maps from the recents) | With the setting "Zwevende speler bij verlaten" on, MuMa shrinks to a floating window with the cover, title and artist. |
| Music is paused and the listener leaves MuMa | MuMa goes to the background as today. No window. |
| Listener taps the window | The system shows play/pause, previous, next, expand and close over it. |
| Listener taps play/pause, previous or next | Same result as the notification's buttons. The play/pause icon follows the state. |
| The track changes | The window shows the new cover, title and artist. |
| Listener taps expand | MuMa opens full screen where it was. |
| Listener drags the window to close it | The window goes. The music plays on, and the notification stays. |
| Listener taps the "Zwevende speler" button (Now Playing menu) | MuMa shrinks to the floating window at once. |
| Android Auto is connected | No change: the car shows its own screen. The floating window follows the same rule as on a bike. |

### Phone: split screen next to Maps (#179)

| Situation | Observable outcome |
|---|---|
| Listener puts MuMa in split screen by hand (recents, app icon, "Split screen") | MuMa resizes. It does not restart and the music does not stop. |
| MuMa's half is short (portrait phone, MuMa at the top or bottom) | MuMa shows the compact player in its half (split screen and a half lower than 480px). |
| MuMa's half is tall enough (a tablet, a landscape split) | MuMa shows its normal screens. |
| Listener taps "Volledige app" in the compact player | The normal screens come back in the half, until the split changes or ends. |
| Listener taps "Navigeren naast MuMa" | Google Maps opens in the other half, with no destination set. |
| Google Maps is not installed | The button is not shown. |
| The compact player shows and music plays | The screen stays on. It goes off as normal when the music is paused or the split ends. |
| Listener ends split screen | MuMa goes back to its normal screens. |
| Car mode is open | Car mode stays on top. It is the screen for the car and wins over the compact player. |

## Acceptance Criteria

1. In Chrome or Edge on a desktop, the "Miniplayer" button opens one always-on-top window with the
   cover, title, artist, play/pause, previous, next, progress and rating of the current track.
2. Every button in the PC window gives the same result as the same button in the player bar, and
   the music never plays twice (one audio element, in the tab).
3. The PC window follows a track change within one second, in both songs and sets mode.
4. Closing the PC window never stops the music. Closing the tab or logging out closes the window.
5. In a browser without the API, the PC shows no "Miniplayer" button.
6. On the phone, leaving MuMa while music plays puts it in a floating window (when the setting is on). Leaving it while paused does not.
7. The floating window shows the current cover, title and artist, and its system buttons
   play/pause, previous and next work, with the play/pause icon matching the real state.
8. Expanding the floating window shows MuMa where it was. No reload, no boot screen.
9. MuMa in split screen does not restart and keeps playing when the split starts, ends or moves.
10. In a short portrait split, MuMa shows the compact player. Its play/pause, previous and next
    buttons are at least 64px.
11. "Navigeren naast MuMa" opens Google Maps in the other half on the test phone. The button is
    absent without Google Maps.
12. While the compact player shows in a split and music plays, the screen does not turn off.
13. The compact player's look is in the style guide before the code (rule 15).

## Decisions

Teun took these on 2026-11-12. Each one names the option picked; the others were weighed and
dropped.

1. **PC, browser without Document Picture-in-Picture:** no button. Only Chrome and Edge 116+ on a
   desktop show "Miniplayer". (A popup fallback and a video picture-in-picture hack were dropped.)
2. **PC window size and layout:** it opens as a strip of about 360 x 120 (cover left, text and
   buttons right). Dragged larger, it switches to the stacked layout (large cover, text and
   buttons below).
3. **Phone, shrink by itself:** only when the setting "Zwevende speler bij verlaten"
   (Instellingen > Apparaat) is on. It is off by default.
4. **Phone, shrink on purpose:** a "Zwevende speler" entry in the Now Playing header menu.
5. **Phone, closing the floating window:** the music plays on.
6. **Phone, split screen:** the half shows the compact player when MuMa is in split screen and its
   half is lower than 480 CSS pixels. A phone in landscape, full screen, keeps its normal screens.
7. **Phone, split screen, stars:** none. Only play/pause, previous and next, as large as possible.
   The PC window keeps its stars.
8. **"Navigeren naast MuMa":** opens Google Maps next to MuMa with no destination. The listener
   picks it in Maps. MuMa stores no addresses.
9. **Floating window shape:** wide, 16:9.
10. **Delivery order:** PC window (#177), then split screen (#179), then the floating window
    (#178), one merge request each.

### Check before building, no code

Issue #179 asks for this first: put the current app in split screen next to Maps by hand (recents,
MuMa icon, "Split screen"), on the phone used on the bike. Two answers decide how much work
#179 is: does MuMa restart when the split starts (it should not, see technical.md), and how much of
the normal player fits in the half.

## Not in Scope

- A map inside MuMa (MapLibre and OpenStreetMap). Parked in #179.
- MuMa's controls inside Google Maps. Maps does not offer it to apps outside its partner list.
- A floating bubble over other apps (`SYSTEM_ALERT_WINDOW`). The floating window of #178 needs no
  extra permission.
- The miniplayer window in the Android app. The app has the floating window instead.
