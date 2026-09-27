# Android Auto Still Hides The Custom Buttons, And The Car's Button List Goes Stale

# status: fixed — the stale list and the diagnostics; whether the car draws the buttons is open (issue #131)

# reported problem
"In Android Auto zie ik nog steeds alleen vorige, volgende en play/pause" (Teun, 2026-09-27, app
7.11.0, Pixel 10 Pro, Android Auto 17.6.663454). No rating, shuffle, repeat or news button, and no
overflow menu. This follows bug report 057 (7.4.4), which moved the buttons to media button
preferences with `SLOT_OVERFLOW` and added the `car sees` diagnostics line.

Diagnostics report 40 is the first report from a drive since that line was added:

```
20:10:51.266 [CarConnection] Setting repeat mode to ALL
20:10:52.993 car sees (Android Auto 17.6.663454-release): custom actions: CYCLE_RATING(icon=59448), REPEAT_MODE(icon=1040448), PLAY_NEWS(icon=57573) | reserve prev=true next=true
20:10:53.267 MediaLibraryCommandHandler: custom layout: CYCLE_RATING(icon=59448), SHUFFLE(icon=57411), REPEAT_MODE(icon=57408), PLAY_NEWS(icon=57573)
```

# Possible reason
What the report proves:
- **The app publishes the buttons, and the car's platform session carries them.** Android Auto
  connects as a legacy controller (`onConnect: com.google.android.projection.gearhead (controller
  v0)`) and reads the custom actions from the platform `PlaybackState`. That state carries three,
  each with a media3 `CommandButton.ICON_*` constant in `EXTRAS_KEY_COMMAND_BUTTON_ICON_COMPAT`,
  and both previous/next reservations. That is the shape the Android for Cars docs describe.
- **1040448 is a valid media3 icon.** It is `0xfe040`, `CommandButton.ICON_REPEAT_OFF`. Media3 puts
  its "filled" and "disabled" variants in the `0xf….` range (`ICON_STAR_FILLED = 0xfe838`,
  `ICON_HEART_FILLED = 0xfe87d`). 57408 is `ICON_REPEAT_ALL`. The two lines show two repeat states,
  not two icon schemes.
- **The car's list was stale.** The car switched repeat to "all" at 51.266, and the restored queue
  made shuffle available. Neither goes through a button, and neither `onRepeatModeChanged` nor a
  queue change republished the buttons, so the car kept "repeat off, no shuffle" until the next
  track change (53.267 here, but a long track keeps it much longer). The same applied to a repeat
  change on the phone and to playback resumption restoring a saved mode. The start-up list
  (`defaultCustomCommands`: shuffle, repeat off, news, no rating) also differed from every later
  one.
- **The commands are granted.** Every controller, the car's included, gets media3's defaults plus
  every button's command (`sessionCommandsWithCustomButtons`). Media3 1.11's legacy stub leaves out
  any custom action whose command is unavailable, so the three actions that reached the platform
  state are proof in themselves. The log did not say so, though.
- **Slots do not reach Android Auto.** `CommandButton.getCustomLayoutFromMediaButtonPreferences`
  (media3 1.11) maps only `SLOT_BACK`, `SLOT_FORWARD` and `SLOT_OVERFLOW` onto the platform
  session. `SLOT_BACK_SECONDARY` / `SLOT_FORWARD_SECONDARY` are dropped for a legacy controller,
  and a button with only those slots is left out entirely. So moving the buttons to secondary slots
  cannot change what Android Auto receives. Taking previous/next's slots (`SLOT_BACK`/`SLOT_FORWARD`)
  would replace the transport controls.
- **The count is within limits.** At most four custom actions; the car design guidelines allow six
  while previous/next stay.

What the report does not settle is why Android Auto 17.6 draws none of the actions it receives. The
platform state matches the documented requirements (a `CommandButton.ICON_*` constant per action,
at most six, reservations set). Android Auto logs nothing on the phone about what it drops. Three
candidates remain, and the next report tells them apart:
1. Android Auto cannot load the actions' drawables from this package (every car drawable is a
   vector with `android:tint="?attr/colorControlNormal"`, a theme attribute another process has no
   theme for).
2. Android Auto 17.6's redesigned player draws custom actions only in a place this car does not
   show, or not at all for any app.
3. Something session-wide in the playback state (state, action bitmask) that the log did not show.

# solution
- **The car's list follows the player.** `PlaybackService` republishes the buttons on
  `onRepeatModeChanged` and on every playlist change (`TIMELINE_CHANGE_REASON_PLAYLIST_CHANGED`,
  which is when shuffle becomes available or not). The start-up list comes from the same builder as
  every later one, with the rating first. All publications go through
  `MediaLibraryCommandHandler.publish`, which skips a list the session already carries
  (`CommandButton.equals`), so frequent timeline changes do not resend it.
- **The grant is explicit and recorded.** The session-command set moved to
  `sessionCommandsFor(buttons)` (`PlayerCommandGrants.kt`). `onConnect` and
  `updateAvailableCommands` remember what they granted a controller for which
  `session.isAutoCompanionController` is true.
- **The `car sees` line proves more.** It is written twice after Android Auto connects: at 2 s, and
  at 15 s once the queue is restored and "repeat all" has landed. The line now reads:

  ```
  car sees (Android Auto <ver>): custom actions: CYCLE_RATING(icon=59448, res=ic_car_rating_0 ok), … | reserve prev=true next=true | state=3 actions=0x… | published: CYCLE_RATING(icon=59448, slot=overflow), … | granted to car: CYCLE_RATING, SHUFFLE, REPEAT_MODE, PLAY_NEWS (missing: none)
  ```

  `res=… ok/unloadable` inflates each action's drawable from this package's resources as obtained
  through the package manager with no theme, which is how another process gets them. `published`
  carries each button's slot. `granted to car` names any custom command the car's controller lacks.
  The media3 log line `custom layout:` carries the slot as well.
- **Icons and slots are unchanged, on purpose.** Every constant is a valid media3 `ICON_*`. Rating
  unfilled/filled/heart, `ICON_SHUFFLE_ON`, `ICON_REPEAT_OFF/ONE/ALL`, `ICON_FEED`. Each button keeps
  `SLOT_OVERFLOW`, the only non-transport slot that reaches the platform session.
- Tests: `AndroidAutoCarButtonsTest` covers the list the car gets in the state it drives in:
  - four buttons, in order, within Android Auto's limit
  - every icon a media3 constant, every button `slot=overflow` and enabled
  - every command granted via `sessionCommandsFor`
  - a repeat/queue change publishing the new state, and an unchanged list not being resent
  - the notification's own drawables unchanged
  - the drawable check

  `MediaLibraryCommandHandlerCarIconTest` follows the new log format.
- Open: issue #131. Teun checks the car on the new build, compares with another media app on
  Android Auto 17.6, and sends a diagnostics report. The two `car sees` lines decide between
  candidates 1–3 above.
