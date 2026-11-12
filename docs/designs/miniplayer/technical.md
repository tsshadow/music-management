# Miniplayer — Technical Design

> Agreed 2026-11-12. Implements [functional.md](functional.md) (issues #177, #178, #179). The
> numbers in brackets point at the decisions there.

## What the Code Has Today

Read before this design was written. Paths are under `services/`.

**Web player.**

- `frontend/src/lib/Player.svelte` owns the player state and every transport action:
  `togglePlay`, `playNext`, `playPrev`, `seek`, `seekTo`, `updateRating`. In a browser tab it
  also owns the one `<audio>` element. The derived state the views show (`track`, `playing`,
  `progress`, `duration`, `currentRating`, `transportLocked`, `playLocked`, `coverUrl`,
  `artistUrl`, `tint`) is computed once there.
- `frontend/src/lib/NowPlaying.svelte` gets that state and those functions as props and reads no
  player store itself. The compact player follows the same pattern.
- In a browser, `platform.player.next()` and `previous()` do nothing
  (`frontend/src/lib/platform/browser/player.js`). Only `Player.svelte`'s `playNext`/`playPrev`
  move a browser queue. A component outside `Player.svelte` therefore cannot skip a track in the
  browser by itself. `CarModeView.svelte` can, because it is native-only and calls the service.
- `isMobile` is set in `frontend/src/App.svelte` (width below 1024px or a coarse pointer).
  `isWideLayout` in `frontend/src/lib/store.js` is the `md` breakpoint. Neither knows about
  window height or window mode.
- `NowPlaying.svelte` already lays out its cover with a size container (`container-type: size`,
  `min(100cqw, 100cqh)`), and Tailwind is v4 (`@import "tailwindcss"` in `frontend/src/app.css`).
- Songs and sets mode is a class on `<html>` (`mode-sets`, set in `App.svelte`), which switches
  `--brand-color` in `app.css`.
- Nothing in the frontend uses `documentPictureInPicture` yet.

**Android shell.**

- The only UI is `muma-mobile/app/src/main/kotlin/nl/teunschriks/mumamobile/activity/CapacitorActivity.kt`,
  a Capacitor `BridgeActivity` with the web bundle. The Kotlin screens were deleted in MR !783.
- `muma-mobile/app/src/main/AndroidManifest.xml`: `CapacitorActivity` has
  `configChanges="orientation|keyboardHidden|screenSize|smallestScreenSize|screenLayout|uiMode"`
  and `launchMode="singleTask"`. It has **no** `supportsPictureInPicture` and **no**
  `resizeableActivity`. No activity sets `resizeableActivity="false"`.
- `muma-mobile/gradle/libs.versions.toml`: `appMinSdk = 33`, `appTargetSdk = 35`. With a
  targetSdk of 24 or higher, `resizeableActivity` defaults to true, so split screen is already
  allowed. And with minSdk 33, every phone has `setAutoEnterEnabled` (API 31) and
  `PictureInPictureParams.Builder.setTitle`/`setSubtitle` (API 33). The `onUserLeaveHint`
  fallback from issue #178 is not needed.
- The `configChanges` above mean a split-screen or picture-in-picture resize does not recreate
  the activity: the WebView only gets a new size. This is what keeps the music and the web state
  through a mode change.
- `MumaSystemPlugin.setKeepScreenOn` (`capacitor/MumaSystemPlugin.kt`) sets `setShowWhenLocked`
  and `setTurnScreenOn`. It does **not** set `FLAG_KEEP_SCREEN_ON`, so the screen still times out.
  `MediaPlayerManager.keepScreenOn` is a field nothing reads.
- `MediaPlayerManager` has `isPlaying`, `togglePlayPause()`, `seekToNext()`, `seekToPrevious()`
  and `addListener(Player.Listener)`.
- The home-screen widget (`provider/UltrasonicAppWidgetProvider.kt`) builds its play/pause,
  next and previous buttons as broadcast `PendingIntent`s to the non-exported
  `UltrasonicIntentReceiver` with `CMD_PROCESS_KEYCODE` and a media `KeyEvent`. The PiP actions
  reuse that path.
- The manifest's `<queries>` lists only the speech recogniser, so on API 30+ the app cannot see
  whether Google Maps is installed.

## A. The Compact Player Component

`frontend/src/lib/CompactPlayer.svelte`, new. Props only, no player store reads, like
`NowPlaying.svelte`:

| Prop | Type | From `Player.svelte` |
|---|---|---|
| `track`, `playing`, `buffering`, `progress`, `duration`, `rating` | as `NowPlaying` | same derived values |
| `coverUrl`, `artistUrl`, `tint` | strings or null | same as the mini player |
| `transportLocked`, `playLocked`, `isLiveStation` | boolean | same |
| `restoringQueue` | boolean | `$queueRestore.status === 'restoring'` |
| `variant` | `'window' \| 'pip' \| 'split'` | the caller |
| `showRating` | boolean | `true` for `window`, `false` for `split` (decision 7) |
| `ontogglePlay`, `onnext`, `onprev`, `onrate` | functions | `togglePlay`, `playNext`, `playPrev`, `updateRating` |
| `onnavigate` | function or null | `split` only, "Navigeren naast MuMa" (section E) |
| `onexpand` | function or null | `split` only, "Volledige app" (section F) |

Layout, by the component's own size (`container-type: size` on its root), so it does not depend on
the window it is in:

- **Strip**, height below 200px: cover as a square of the full height on the left, title and
  artist, then the buttons on the right, progress as a 2px bar along the bottom (the mini player's
  bar).
- **Stacked**, height 200px or more: cover as the largest square that fits on top (the
  `min(100cqw, 100cqh)` rule of `NowPlaying.svelte`), title and artist, a row of buttons, the
  progress bar.
- `variant: 'pip'`: no buttons, no progress, no stars. Android does not pass taps into a
  picture-in-picture window, so a button there would only mislead.
- `variant: 'split'`: buttons at least 64px, play/pause 80px, the "Navigeren naast MuMa" and
  "Volledige app" buttons as secondary pills (`bg-muma-spotify-light`) under the transport.

Rules for the component:

- No Svelte transitions and no `requestAnimationFrame`. In the PC window (section B) the
  component runs in the main tab's JavaScript, and Chrome pauses `requestAnimationFrame` in a
  hidden tab. A transition would stop halfway while the listener looks at the window.
- `Artwork.svelte` for the cover, so the fallback chain (cover, artist image, tinted panel) is the
  same as in the mini player.
- Text through `$t`, new keys under `miniplayer.*` in both locale files.

## B. PC: Document Picture-in-Picture (#177)

### The browser API

`window.documentPictureInPicture.requestWindow({width, height})` returns a new same-origin
`Window` with an empty document that the browser keeps above other windows.

- Chrome and Edge 116+ on Windows, macOS, Linux and ChromeOS. Not on Chrome for Android, not in
  Firefox, not in Safari, not in the Android WebView.
- Secure context only (https or localhost). On a plain-http origin the property is absent, so the
  feature test below hides the button there too.
- The call must come from a click (user activation). One window per tab; a second call replaces
  the first window.
- The window closes when the tab closes or navigates away. It has a "back to tab" button of its
  own.
- On Linux the window manager decides "always on top". Under X11 it works. Under Wayland some
  compositors ignore it. Check on Teun's desktop (technical acceptance criterion 4).

### `frontend/src/lib/miniplayerWindow.js`, new

- `isSupported()`: `'documentPictureInPicture' in window && !platform.system.isNative`.
- `open(props)`:
  1. If a window is open, focus it and return.
  2. `requestWindow({ width, height })` at 360 x 120 (decision 2).
  3. Copy the styles: for each `document.styleSheets`, write its `cssRules` into a `<style>` in
     the new document; when reading `cssRules` throws (a cross-origin sheet), clone the `<link>`
     instead. Vite's production build emits the Tailwind CSS as linked files, and a lazy chunk
     adds its CSS later, so the copy also runs again when a new sheet appears (one
     `MutationObserver` on `document.head`).
  4. Copy `document.documentElement.className` (for `mode-sets`) and keep it in step with a
     `MutationObserver` on the class attribute.
  5. `mount(CompactPlayer, { target: pipWindow.document.body, props })`, with `props` a
     `$state` object owned by `Player.svelte`. Svelte 5 updates a mounted component when that
     object changes. The functions in `props` are `Player.svelte`'s own, so the window runs the
     same code as the player bar and there is still one `<audio>` element, in the tab.
  6. `pagehide` on the window: `unmount`, drop the observers, clear the handle.
- `close()`: closes the window if one is open. Called on logout.

The component is mounted into the new document, not moved there. Svelte 5 attaches its delegated
event listeners to the mount target, so a click in the window reaches the handler. A test mounts
into a second `document` to prove it (criterion 2).

### Player bar

`Player.svelte`, desktop branch, right-hand cluster: one icon button "Miniplayer" before the queue
button, only when `isSupported()`. Its click calls `open(miniplayerProps)`. `miniplayerProps` is
a `$state` object that one `$effect` fills from the derived values listed in section A.

Where the API is missing, the button is absent (decision 1). There is no popup fallback.

## C. Android: the Window-Mode Signal

The web player needs to know whether its window is full screen, half of a split, or a floating
window. A size alone cannot tell a split half from a phone in landscape.

- `CapacitorActivity` overrides `onMultiWindowModeChanged` and `onPictureInPictureModeChanged`
  and calls `MumaSystemPlugin.emit("windowModeChanged") { it.emitWindowMode(mode) }`, with
  `mode` one of `full`, `split` and `pip` (`isInPictureInPictureMode` first, then
  `isInMultiWindowMode`).
- `MumaSystemPlugin.windowMode()` returns the current mode, for a WebView that subscribes after
  the first event. Same reason as `carState()`.
- `frontend/src/lib/platform/index.js`: `onWindowModeChanged(fn)` and `windowMode()` on
  `PlatformSystem`. The browser platform answers `full` and never fires.
- `frontend/src/lib/store.js`: `windowMode` (readable, from the platform) and `compactLayout`
  (derived): `pip` when the mode is `pip`; `split` when the mode is `split` and
  `window.innerHeight < 480` (decision 6); otherwise `null`.

## D. Android: Picture-in-Picture (#178)

### Manifest

`CapacitorActivity` gets `android:supportsPictureInPicture="true"`. The existing `configChanges`
stay as they are.

### `activity/PictureInPicture.kt`, new, used by `CapacitorActivity`

- Builds `PictureInPictureParams`:
  - `setAspectRatio(Rational(16, 9))` (decision 9).
  - `setAutoEnterEnabled(autoEnter)`, with `autoEnter = mediaPlayerManager.isPlaying &&
    setting` (decision 3).
  - `setSeamlessResizeEnabled(false)`: the content is not video, and the cross-fade looks better
    for a layout switch.
  - `setSourceRectHint`: a 16:9 band across the middle of the window, so the shrink starts from
    the floating window's shape. Android Lint requires it with auto-enter.
  - `setTitle` / `setSubtitle`: the track's title and artist, for the system's accessibility and
    the menu.
  - `setActions`: three `RemoteAction`s, previous, play/pause, next, each a broadcast
    `PendingIntent` to `UltrasonicIntentReceiver` with `CMD_PROCESS_KEYCODE` and the media
    `KeyEvent`, built like the widget's (request codes of its own, `FLAG_IMMUTABLE`). The
    play/pause action's icon and label follow `isPlaying`.
- `CapacitorActivity` calls `setPictureInPictureParams(...)` on start and again from a
  `Player.Listener` on `MediaPlayerManager` (`onIsPlayingChanged`, `onMediaMetadataChanged`), so
  the auto-enter flag and the play/pause icon are never stale.
- `MumaSystemPlugin.enterPictureInPicture()`: calls `enterPictureInPictureMode(params)` on the
  running activity, for the "Zwevende speler" button (decision 4). The plugin reaches the activity
  through the `FloatingWindowHost` interface, which `CapacitorActivity` implements. The button is
  a row in the track details sheet that the Now Playing header menu opens, shown in the app only.
  Writing `pipOnLeave` through `setSetting` sets the parameters again at once.
- The device setting `pipOnLeave` (boolean, default false) goes through `getSettings` /
  `setSetting` and `DEVICE_SETTING_WHITELIST`, shown in Instellingen > Apparaat.

### The web side in PiP

`App.svelte` renders `CompactPlayer` with `variant="pip"` over the whole viewport while
`$compactLayout === 'pip'` (z-index under car mode's `z-50`). The normal screens stay mounted
underneath, so an expand shows them as they were.

### Risks to check on a device first

- **WebView paused in PiP.** The activity is paused (not stopped) while it floats. If Capacitor's
  `onPause` pauses the WebView's timers or drawing, the window keeps showing the old track after
  a track change. Check it in the first build. If it happens, `CapacitorActivity` resumes the
  WebView when `isInPictureInPictureMode` is true.
- **Duplicate buttons from the media session.** Android can add media buttons to a PiP window
  from the app's active `MediaSession`. If the test phone shows them, the `RemoteAction`s are
  dropped and the session's buttons are used.
- **Two notifications' worth of controls.** The media notification stays. That is wanted.

## E. Android: Split Screen and "Navigeren naast MuMa" (#179)

### Resizability

Nothing to add: see "What the code has today". A test checks that the merged manifest of
`CapacitorActivity` never has `resizeableActivity="false"` (criterion 7), so a later edit cannot
switch split screen off by accident.

### Opening Maps next to MuMa

- `MumaSystemPlugin.canNavigate()`: true when `packageManager` resolves the Maps intent below.
  Needs a `<queries>` entry in the manifest: `<package android:name="com.google.android.apps.maps" />`.
- `MumaSystemPlugin.navigateAdjacent()`: `Intent(ACTION_VIEW, Uri.parse("geo:0,0?q="))` with
  `setPackage("com.google.android.apps.maps")` and
  `FLAG_ACTIVITY_LAUNCH_ADJACENT | FLAG_ACTIVITY_NEW_TASK`. No destination (decision 8).
- `FLAG_ACTIVITY_LAUNCH_ADJACENT` puts Maps in the other half when MuMa is already in split
  screen. From full screen, whether the phone enters split screen for it depends on the Android
  version and the maker. Check on the bike phone (criterion 9). If it does not, the button is
  shown only while `windowMode` is `split`.

### Keeping the screen on

`setKeepScreenOn` gets a third flag, `keepOn`, which adds or clears
`WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON` on the activity's window. The shell applies
each ask only when the call has it: a call with only `keepOn` leaves the lock-screen flags as
they are, and car mode's calls (without `keepOn`) leave the keep-on flag as it is. So car mode
and the split screen cannot undo each other. `App.svelte` sends `{keepOn: true}` while the split
player shows and music plays, and `{keepOn: false}` when either stops, only on a change. (Google Maps
also keeps the screen on while it navigates, so this matters mainly before the route starts and
after it ends.)

## F. The App Layout in Compact Mode

`App.svelte`:

- `$compactLayout` set and not dismissed: render `CompactPlayer` over the whole viewport, with the
  props from `Player.svelte` (the same `miniplayerProps` object of section B, exported through a
  small store, `compactPlayerProps`, so `App.svelte` does not compute player state).
- "Volledige app" sets `compactDismissed = true`. Any change of `$windowMode` sets it back to
  false.
- Car mode open: car mode wins, the compact player is not rendered.
- The Android back gesture while the compact player shows: the same as at the root of the app.

## Data Model

None. No table, column or endpoint changes. One new device setting on the phone (`pipOnLeave`),
stored with the other Apparaat settings. The PC window stores nothing (the browser keeps its own
window size).

## API Contract

No HTTP endpoint changes. The contract that changes is the one between the web bundle and the
shell (`frontend/src/lib/platform/index.js`, `PlatformSystem`):

| Member | Request | Response | Error cases |
|---|---|---|---|
| `windowMode()` | none | `{mode: 'full' \| 'split' \| 'pip'}` | browser: `{mode: 'full'}` |
| `onWindowModeChanged(fn)` | handler | unsubscribe function | browser: never fires |
| `enterPictureInPicture()` | none | resolves when asked | rejects `no activity`; browser resolves without doing anything |
| `canNavigate()` | none | `{value: boolean}` | browser: `{value: false}` |
| `navigateAdjacent()` | none | resolves when started | rejects when nothing handles the intent |
| `setKeepScreenOn({showWhenLocked, turnScreenOn, keepOn})` | `keepOn` new, applied only when present | unchanged | unchanged |

An old APK with a new web bundle cannot happen: the bundle is baked into the APK.

## Cross-App Impact

- `services/frontend` and `services/muma-mobile` change together for sections C to F, in one MR
  per issue (rule 7).
- The PC window (section B) is frontend only.
- The phone parts reach phones only with an app release: bump `versionCode` in
  `services/muma-mobile/app/build.gradle`.
- No music-manager, LMS or Subsonic change.
- Style guide: one entry "Compact player" under Components (strip, stacked, pip and split
  layouts, button sizes) and one for the "Miniplayer" icon button, added before the code (rule
  15).

## Technical Acceptance Criteria

1. `CompactPlayer.svelte` renders the strip layout below 200px height and the stacked layout from
   200px, shows no buttons with `variant="pip"`, and calls `ontogglePlay`, `onnext`, `onprev`,
   `onrate` from its buttons (vitest, `tests/unit/compactPlayer.test.js`).
2. `miniplayerWindow.open` with a stubbed `requestWindow` that returns a second document mounts the
   component there, copies every style sheet and the `mode-sets` class, and a click on its
   play button calls `Player.svelte`'s `togglePlay`. A second `open` mounts nothing new. A
   `pagehide` unmounts it.
3. `isSupported()` is false without `documentPictureInPicture` and on the native shell; the player
   bar then has no "Miniplayer" button.
4. By hand, Chrome on Teun's PC: the window stays above other windows, follows a track change
   within a second, and closing it keeps the music playing.
5. `compactLayout` is `pip` for mode `pip`, `split` for mode `split` with a height below 480,
   and `null` otherwise, including landscape full screen (vitest).
6. Robolectric: `CapacitorActivity` builds `PictureInPictureParams` with auto-enter only while
   playing and the setting on, and the play/pause `RemoteAction` follows `isPlaying`.
7. A unit test on the merged manifest: `CapacitorActivity` has `supportsPictureInPicture="true"`
   and no `resizeableActivity="false"`; the `<queries>` lists the Maps package.
8. `setKeepScreenOn({keepOn: true})` sets `FLAG_KEEP_SCREEN_ON` and `{keepOn: false}` clears it
   (Robolectric).
9. By hand, on the bike phone: split screen with Maps does not restart MuMa or stop the music;
   "Navigeren naast MuMa" opens Maps in the other half; the floating window shows the new track
   after a skip from its own system button; the screen stays on in the split while music plays.

## Related Docs

- [universal-ui](../universal-ui/functional.md): why the phone app's screens are the web player.
- [phone-ui-polish](../phone-ui-polish/functional.md): `Artwork.svelte` and the mini player's
  cover rules, reused here.
- [deferred-queue-restore](../deferred-queue-restore/functional.md): the "restoring the queue"
  state the compact player shows too.
- Issues #177, #178, #179.
