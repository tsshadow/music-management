# Android Auto Draws No Custom Buttons: Rating, Shuffle, Repeat And News Are Missing

# status: fixed — not confirmed in the car; the first report from a drive (40, 7.11.0) showed the platform session carrying the buttons and the car still drawing none, continued in bug report 127

# reported problem
"Geen icons zoals radio en rating. Laatste versie." (2026-09-24, app 7.4.3). The car's now-playing
screen shows play/pause, previous and next, and nothing else: no rating star, no shuffle, no
repeat, no news button, and no overflow menu. The phone's media notification still shows them.
The buttons first went missing around 2026-09-12, when Android Auto updated itself to 17.6 and
its redesigned media player rolled out. 7.4.1 gave every button a media3 `CommandButton.ICON_*`
constant (MR !876), which did not bring them back.

# Possible reason
Not proven — nothing on the phone logs what Android Auto decides to draw, and no diagnostics report
from a drive on 7.4.2 or later exists yet (the newest, 37, is 7.4.1 and was flooded, bug report 036).

What the code shows, read against the media3 1.11.1 sources:
- The app published its buttons with `MediaSession.setCustomLayout`, deprecated since media3 1.6.
  On that path the legacy stub copies the buttons into the platform `PlaybackState` as custom
  actions (with the icon constant in their extras since !876), but writes no slot reservations
  into the session extras: `updateCustomLayoutAndLegacyExtrasForMediaButtonPreferences` only runs
  when media button preferences are set.
- Android Auto's documentation describes custom actions together with those reservations, and a
  media3 1.10 app on the new Auto player (androidx/media#3342) draws its custom buttons there.
- A bugreport on 2026-09-19 showed the platform session carrying the custom actions, so the app did
  publish them; the car did not draw them.

So the remaining difference between this app and one the new player serves is the API it
publishes through, and the extras that come with it.

# solution
- Every car button names `CommandButton.SLOT_OVERFLOW`, and the session publishes the list with
  `setMediaButtonPreferences` instead of `setCustomLayout` — at start-up, on every track change,
  rating, repeat change, and in `onPostConnect`. Media3 now writes the previous/next reservations
  (`EXTRAS_KEY_SLOT_RESERVATION_SEEK_TO_PREV`/`_NEXT`) into the platform session's extras.
- The placeholder button is gone. It kept the rating out of the slot beside play/pause on the last
  track of a queue that does not repeat; the "next" reservation does that now.
- `onPostConnect` publishes the buttons for every controller, legacy ones (version 0, which Android
  Auto is) included, instead of only for media3 controllers.
- When Android Auto connects, the app logs what the platform session actually carries, e.g.
  `car sees (Android Auto 17.6.…): custom actions: CYCLE_RATING(icon=…), SHUFFLE(icon=…), … |
  reserve prev=true next=true`. If the car still draws nothing, one diagnostics report after a drive
  tells whether the actions were there — and if they were, the problem is Android Auto's.
- Tests: `MediaLibraryCommandHandlerCarIconTest` pins the overflow slot, the preferences path, the
  missing placeholder and the logged line.
