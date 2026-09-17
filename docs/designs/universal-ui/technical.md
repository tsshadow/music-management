# Universal UI — Technical Design

> Implements [`functional.md`](functional.md). Proposal, not yet agreed; no code exists for it.
> Two paths are worked out: **Path A**, the Svelte UI in a Capacitor shell (the design the
> functional document describes), and **Path B**, restyling the existing Kotlin app to match the
> web player. They are alternatives; the comparison at the end is what the decision should rest
> on.

## The shape of the problem

Measured on 2026-09-12 in this checkout:

| | Web (`services/frontend`) | Phone (`services/muma-mobile/app/src/main`) |
|---|---|---|
| UI code | 72 `.svelte`, 17.1k lines | 76 files in `activity/`, `fragment/`, `adapters/`, `view/`, 15.6k lines; 95 XML layouts; **no** Compose |
| Non-UI | `store.js`, `collections.js`, `feeds.js`, `memories.js`, `radioController.js`, i18n | `service/`, `data/`, `di/`: 54 files, 13.7k lines; `core/voice`, `core/domain`, `core/subsonic-api` |
| Playback | `<audio>` in `Player.svelte`, Web Audio equalizer, browser MediaSession | `PlaybackService` (ExoPlayer + `MediaLibrarySession`), `DownloadService`, `OfflineMusicService` (Room + files on disk) |
| Talks to | LMS `/rest/*` relative to origin, muma `/api/*` via `mumaApiUrl` | LMS `/rest/*` on a configured server, muma `/api/*` |
| Phone layout | already responsive: `isMobile`, `MobileNav`, drawer, simplified rows | native |
| Style source | `app.css` `@theme` tokens; `mode-sets` class flips `--brand-color` | `res/values/themes.xml` attributes; two styles |

Two things make Path A smaller than it looks: the web player already has a phone layout, and
the phone's native layer is already split into services the UI does not own. One thing makes it
larger than it looks: `MediaPlayerModule.kt:25` scopes the player controller to
`NavigationActivity`, so the native layer is not yet UI-free.

---

## Path A — Svelte UI in a Capacitor shell

### Architecture

```
┌────────────────────────── services/frontend (Svelte) ──────────────────────────┐
│  screens (unchanged) · store · router · i18n · collections · feeds · memories   │
│                                                                                │
│  platform/                         one interface, three implementations        │
│    player     play/pause/seek/queue/state/resume                               │
│    storage    download/list/remove/progress/size/isLocal                       │
│    speech     start/stop/partial/final                                         │
│    diagnostics log(action)/report()                                            │
│    system     serverUrl/credentials/deepLink/back/carConnected                 │
└──────┬────────────────────────────┬──────────────────────────────┬─────────────┘
       │ browser                    │ Capacitor Android            │ PC shell (later)
       ▼                            ▼                              ▼
  <audio>, Cache Storage,     Kotlin plugins over the        Tauri 2 (proposal):
  Web Speech (disabled),      existing services:             Rust fs, tray, hotkeys,
  console                     PlaybackService,               media keys, own cache
                              DownloadService,
                              OfflineMusicService,
                              SpeechCapture,
                              CrashReportManager,
                              Android Auto (untouched)
```

The UI imports `platform` and nothing else platform-specific. The browser implementation is what
`Player.svelte` does today, moved behind the interface. Choosing the implementation happens once
at boot from `Capacitor.isNativePlatform()` (or the Tauri global later).

### Playback ownership

On Android the native `PlaybackService` owns queue, position and state; the WebView renders them
and sends commands. Two engines must never run at once: the browser `<audio>` path is not even
loaded inside the shell. This is the rule that keeps Android Auto, the notification, Bluetooth and
background playback exactly as they are, and it is why `Player.svelte` must be split into a
presentational component and a `player` engine before anything else.

Equalizer: the web equalizer is Web Audio and cannot reach ExoPlayer. On Android the equalizer
maps onto the existing native equalizer (`EqualizerFragment`'s backend) through
`platform.player.setEqualizer(bands)`; the UI is the web one.

### Offline

Room and the files on disk stay where they are (same `applicationId`, same database name, same
directory). `OfflineMusicService` already answers Subsonic-shaped queries (`minDuration` included)
from the local store; the plugin exposes it as `platform.storage.query(request)` returning the same
JSON shape LMS returns, so list components do not learn a second data source. The download state
glyph in a row comes from `platform.storage.stateOf(ids)` batched per list.

Local playback never streams a file through the WebView: the UI hands the native player a track
id and the native `DownloadService`/`OfflineMusicService` resolve the local file, as today.

### Server, sign-in, upgrade

- `mumaApiUrl` and the Subsonic base become one `serverUrl` from `platform.system`; the web keeps
  deriving it from `window.location`, the shell reads it from the plugin.
- Migration on first start reads the old app's server list, active server, credentials and the
  settings that have an equivalent, writes them into the settings blob, and marks the migration
  done. No wizard.
- Google sign-in uses the Capacitor Google Auth plugin; the resulting id token enters the same
  `handleGoogleResponse` the web has.
- Settings that are phone-only (downloads, car, voice) live under new keys in the existing
  `/api/users/{id}/settings/frontend` blob.

### Android Auto, voice, car mode, diagnostics

- **Android Auto**: `MediaLibraryService`, `MediaLibraryPlaybackController` and the browse tree
  are untouched. A "Sets" root is added next to the existing roots (both always present); the
  feed entries stay.
- **Voice**: `SpeechCapture` becomes the `speech` plugin; the parser and resolver in `core/voice`
  stay Kotlin and run natively. The voice screen is Svelte. Later, if the PC wants voice, the
  parser is ported to JS; not in scope.
- **Car mode**: the screen is Svelte; `platform.system.carConnected` is a plugin event from the
  existing detection.
- **Diagnostics**: `CrashReportManager` stays; the plugin adds `log(action)` so the UI's action log
  joins the report, and the WebView's uncaught errors are forwarded to it. Reports go to the same
  crash-report endpoint.
- **Device settings**: a native-only "Apparaat" tab in the Svelte settings screen (`platform.system.isNative`
  is the gate, the same check `platform.storage.supported` serves as elsewhere) covers the phone-only
  preferences Spotify-style: downloads, streaming quality, playback, car mode, diagnostics. `MumaSystem`
  has `getSettings()` (a snapshot of every field the tab shows) and `setSetting({key, value})`, which
  checks `key` against a fixed whitelist (`DEVICE_SETTING_WHITELIST` in `capacitor/DeviceSettings.kt`,
  now `BOOLEAN`/`INT`/`STRING_SET`) and `value`'s type before writing through `Settings` — an
  unrecognised key or a wrong-typed value rejects the call rather than silently doing nothing. Every
  legacy setting that had no equivalent here now does: `listBondedDevices()` backs a real Bluetooth
  picker for `car_mode_devices` (pre-ticking whatever is already stored, or a car-class guess if
  nothing is); `requestCarModeFullScreenPermission()` fires the same system settings screen the
  legacy row's click listener did; `pickCacheLocation()`/`clearCustomCacheLocation()` drive the SAF
  directory picker through `Plugin.startActivityForResult`/`@ActivityCallback`, the same flow
  `SelectCacheActivityContract` gives the legacy screen. `muma_user_id`/`muma_api_key` are answered
  read-only (`mumaUserId`, `mumaApiKeySet`) — login fills them, nothing here edits them. The "Alle
  app-instellingen…" row and its `openLegacySettings()` call are gone from the tab now that nothing
  in it needs the legacy screen any more; the plugin method itself is unchanged, kept for the
  eventual deletion MR. `MumaStorage` has `clearCache()`, which cancels queued/active downloads and
  deletes every cached file that is not pinned.

  What used to be phone-only and is now an account-level web setting too (`accountSetting()` in
  `store.js`, synced through the same `frontend` app-settings blob `favoriteGenres`/`language`
  already use): the home-section keys and the "Weergave" (display) keys, surfaced in
  `GeneralSettings.svelte`. `canonical_only` and `show_confirmation_dialog` map onto or extend an
  existing web control (`deduplicateEnabled`, the set-size download confirmation) rather than adding
  a parallel one. `override_language`'s existing `LanguageSetting.svelte` now also calls a new
  `setAppLocale()` plugin method, so `CapacitorActivity.attachBaseContext`'s `LocaleHelper.wrap`
  picks it up for the shell's own chrome, not only the WebView's JS-rendered text — this recreates
  the host activity, so it is a deliberate, infrequent action, not something called on every boot.

  Everything else the legacy screen offered is retired outright rather than ported: see
  functional.md's "Open Questions / Not Yet Decided" entry ("Device settings") for the full list
  and the reasons. `style`/`app_icon`/`ui_scale`/`server_scaling` keep their `Settings.kt` property
  real and writable — deliberately not hardcoded — because the theming engine and its tests still
  branch on more than the default; everything else that is retired and still read by other Kotlin
  code is hardcoded there instead of deleted.
- **Audio output** (phone-ui-polish increment H): `platform.system` also carries
  `outputRoute()` (`{name, type}` of the output media plays through, `null` in a browser),
  `onOutputRouteChanged(fn)` (an `AudioDeviceCallback` on the Kotlin side, never fires in a
  browser) and `openOutputPicker()` (Android's output switcher, Bluetooth settings as fallback).
  Details in [`phone-ui-polish/technical.md`](../phone-ui-polish/technical.md), section H.

### What is deleted from the Kotlin module

Done (MR after 0.61.0 / muma-mobile 6.36.0, the last release that still carried both interfaces).
The list below is what went; it is kept so the "what stays" half can be checked against.

- Every fragment under `fragment/`, including `LyricsFragment`, `SetupWizardFragment`,
  `ManualFragment`, `LogViewerFragment`, Chat, Shares, the standalone Podcast screens, Bookmarks
  (replaced by set resume) and Jukebox (not carried over).
- `wizard/`, `manual/`, `management/`, `model/`, `adapters/`, `view/` in full;
  `activity/NavigationActivity.kt`; the home screen's own model (`HomeViewModel`,
  `HomeSectionProvider`, `HomeCardAdapter`, `HomeCardNavigator`, `MemoriesProvider`, and the rest
  of `home/` that only the Kotlin home read).
- All of `res/layout` and `res/layout-land` except the three widget layouts, `res/menu`,
  `res/navigation`, `res/xml/settings.xml`, `res/xml/searchable.xml`, the `UltrasonicTheme.Muma`
  style, and every string, plural, array, colour, style, drawable and animation that only those
  referenced -- ~7.000 lines across the locale folders, pruned by running Android Lint's
  `UnusedResources` to a fixed point.
- The theming engine's second style, `UiScaleHelper`, `Settings.style`/`uiScalePercent`/
  `serverScaling`/`webUiEnabled`, `UiVariant`'s enum (now an object naming `CapacitorActivity`),
  `MumaSystemPlugin.switchToLegacyUi`/`openLegacySettings`, and the Gradle dependencies only the
  screens pulled in (Navigation + SafeArgs, ViewPager2, SwipeRefresh, ConstraintLayout,
  RecyclerView fast-scroll, Markwon, MultiType, GridLayout, ColorPickerView, Transition,
  fragment-ktx).

What stays: `CapacitorActivity`/`LauncherActivity` (the launcher aliases and the icon-colour
switch are untouched; the trampoline now also carries the `SEARCH`/`MEDIA_PLAY_FROM_SEARCH`
filters `NavigationActivity` had), the services, Room, the Koin root `single`s,
`service/androidauto/`, `core/*`, `capacitor/*`, `CrashReportManager`, `car/*`,
`voice/VoiceTileService`, the widget, the launcher shortcuts, and the parts of `home/` the
services read: `RecentActivityStore`, `PlayHistoryRecorder`, `PlaybackSourceHolder`,
`FavoriteGenres`, `HomeSorts`, `HomeCard` (the persisted shape of a shortcut), `HomeSectionId`
(named in that shape) and `TileInfo`/`TileStorage`, moved from `fragment/muma` because Android
Auto's "Afspeellijsten" root still lists the favourite tiles. Nothing writes tiles any more; that
root keeps showing what the phone had and is the one Auto surface whose content the web cannot
change -- see `functional.md`'s open questions.

`StaticServers` in `data/` is the companion object of the deleted `ServerSettingsModel`, kept
because `ActiveServerProvider` resolves the active and sign-in server against it.

### What is added to the web module

- `platform/` with the interface and the browser implementation.
- Four screens: full-screen player (styleguide already specifies it), Downloads, Car mode, Voice.
- Configurable home sections, ported from the phone's `HomeSectionId` model into the dashboard.
- Set resume: position stored per work id in the account settings blob, throttled writes, read on
  play; the phone's bookmark table migrates into it once.
- Filter chip row at phone width over the existing `FilterBar`.
- Duration column, ±30 s buttons and h:mm:ss scrub in sets mode.
- Capacitor config, `android/` project, and a `frontend:capacitor` CI job that builds the APK the
  way `muma-mobile:build` does today (same signing, same APK hoster, same `APK_ALIASES`).

### Phases

Each phase ends in a build that can be installed and judged. Sizes are relative to the home
sections change (one design, one MR, ~two days including tests) = **S**.

| Phase | Delivers | Size | Proof |
|---|---|---|---|
| 0 | `platform` interface; `Player.svelte` split into view + browser engine; no behaviour change on the web | M | web unit + Playwright green, nothing visible changed |
| 1 | Capacitor shell; login with server; browse and play through the native `PlaybackService`; notification, lock screen, Bluetooth; Android Auto still works | L | **the risk proof**: play, kill WebView, reopen, position correct; Auto browses and plays |
| 2 | Offline: Downloads tab, states in rows, `query` through `OfflineMusicService`, local playback, set size confirmation | M | airplane-mode playback of a downloaded set |
| 3 | Sets first-class: ±30 s, h:mm:ss, duration column, resume across devices, Sets root in Auto, three voice phrasings | M | criteria 6–8 |
| 4 | Voice screen, car mode, diagnostics with action log, settings migration, in-place upgrade from 6.x | M | upgrade test from the last 6.x APK on a real phone |
| 5 | Home sections on the web, full-screen player polish, management at phone width verified page by page, delete the Kotlin UI, release as 7.0.0 | M | criteria 1, 2, 11 |
| 6 | PC as PWA: service worker, Cache Storage `storage` implementation, install prompt | S | criterion 6 on a PC in Chrome/Edge |
| 6b | Only if the PWA falls short: Tauri 2 shell with fs downloads, tray, media keys | L | same, with a visible music folder |

Total roughly 6× the home-sections change before the PC, on the order of two to three months of
part-time work, most of it in the fast web loop. Phase 1 is the one that can fail; it is
deliberately early and deliberately small.

### Cross-App Impact

| App | Impact |
|---|---|
| `services/frontend` | grows by `platform/`, four screens, home sections, set resume; `Player.svelte` restructured; Tailwind tokens unchanged |
| `services/muma-mobile` | lost its UI (done); shell + plugins + services; version series continues (7.0.0) under the same package |
| `services/music_manager` | new keys in the frontend settings blob (downloads, car, voice, home sections, set positions); no new endpoint |
| LMS | none |
| CI | `frontend:capacitor` build job; `muma-mobile:unit` shrinks to services and plugins; Playwright gains the four screens; the `e2e:scan-to-listen` chain is unaffected |
| Docs | `services/muma-mobile/STYLEGUIDE.md` retired in favour of `services/frontend/STYLEGUIDE.md`; `docs/styleguide.md` reconciled (44 vs 48 px touch target) |

### Technical Acceptance Criteria

1. `grep -r "Capacitor" services/frontend/src --include=*.svelte` returns nothing: only
   `platform/` knows the shell.
2. Inside the shell, `document.querySelector('audio')` is null at all times.
3. Killing the app process during playback and reopening restores queue and position from the
   native service within one second of the WebView's first paint.
4. `platform.storage.query` returns byte-identical JSON to LMS for the same request against a fully
   downloaded playlist.
5. Upgrading from the last 6.x APK on a device with downloads and a Google session: zero network
   calls before the first screen shows the migrated session, and every download is listed.
6. Android Auto's browse tree, diffed against 6.35.0 with the same library, differs only by the
   added Sets root.
7. The `frontend:capacitor` job produces an APK signed with the existing key and the APK hoster
   serves it under the existing aliases.
8. The web Playwright suite runs unchanged against the shell's bundle served by Vite, proving the
   bundle is the same code.

---

## Path B — Restyle the existing Kotlin app to match the web

### What it is

Keep muma-mobile as it is architecturally and give it a new style package that reproduces the
web player's look: the same tokens, the same components, the same spacing, on the existing
fragments. No Capacitor, no change to playback, offline, Auto, voice.

### What has to change

1. **One token source.** A generated `tokens.xml` from the web's `app.css` `@theme` block (colours,
   radii, type scale, spacing), produced by a script in `services/frontend` and committed to
   `res/values/`. `themes.xml` reads only those. The MuMa style is deleted; the appearance setting
   goes.
2. **Component-by-component parity.** Each web component that the phone shows gets a spec (size,
   type, icon, states, spacing) and its Android twin is rebuilt to it. The list, in the order that
   shows on screen most:
   track row · mini player · bottom bar · top bar · home shortcut card · section heading + "Meer" ·
   filter chips · options sheet · full-screen player · library tab strip · search field · login ·
   settings rows · empty states · toasts.
   Fifteen components; the 95 layouts are mostly compositions of them.
3. **Icons.** The web uses Lucide; the phone uses Material and its own drawables. Swap to Lucide's
   Android set for the fifteen components so glyphs match.
4. **Sets colour.** The phone already flips the brand for sets mode; make sure every accent goes
   through the theme attribute (the styleguide says it does).
5. **Screenshot parity tests.** A Playwright screenshot of the web at 412×915 and a Robolectric or
   emulator screenshot of the same screen, compared per component — Robolectric draws nothing, so
   this needs the emulator job, with its known traps.

### What it does not do

- It closes no feature gap. The web's role filter, "include unrated", memories year tiles,
  listening stats, song versions, artist display name, nine management pages, and everything
  added to the web from now on still have to be built twice. The drift that motivated this
  design continues.
- It cannot reach pixel identity: two renderers, two text engines, different scroll physics. It
  can reach "obviously the same design".
- It does nothing for a PC app; that is a third implementation or the PWA/Tauri route anyway.
- The four missing web screens (full-screen player already exists natively; Downloads, car mode,
  voice exist natively) do not need to be written — this is the one place Path B is ahead.

### Size

Token generation and the theme: **S**. Fifteen components with parity checks: **M–L**, dominated
by the emulator screenshot loop. Total roughly 2–3× the home-sections change, then a permanent
tax of every future UI feature twice.

---

## Comparison

| | Path A — Capacitor | Path B — restyle |
|---|---|---|
| Look | identical (same code) | close, never identical |
| Feature parity | automatic, now and later | manual, now and later |
| Native features | kept, behind plugins; phase 1 proves it | kept, untouched |
| Risk | phase 1 (WebView + native player lifecycle, Auto) | low |
| Up-front size | ~6 S | ~2–3 S |
| Ongoing cost | one UI, fast web loop | two UIs, one in the slow Android loop |
| PC app | same UI, one more shell | separate work |
| Reversible | yes until phase 5 deletes the Kotlin UI | yes |

Path B is the right choice if the Capacitor proof in phase 1 fails or if the UI is expected to
stop changing. Given that every recent feature landed on the web first and the phone second or
never, Path A is the recommendation; Path B's token generation (step 1) is worth doing regardless,
because Path A's phase 0 needs the same reconciled token set.

## Related Docs

- [`functional.md`](functional.md)
- [`../home-sections/`](../home-sections/) — the home model Path A ports into the web dashboard
- [`../../styleguide.md`](../../styleguide.md), [`../../../services/frontend/STYLEGUIDE.md`](../../../services/frontend/STYLEGUIDE.md), [`../../../services/muma-mobile/STYLEGUIDE.md`](../../../services/muma-mobile/STYLEGUIDE.md) — the three style sources to reconcile into one
- [`../../superpowers/specs/2026-08-18-muma-mobile-style-themes-design.md`](../../superpowers/specs/2026-08-18-muma-mobile-style-themes-design.md) — the MuMa style this design retires
- [`../url-routing/`](../url-routing/) — the routes the shell's deep links and back button follow

## Phone feedback round 3 — approved request, 2026-09-15

Use shared settings density CSS and a shared quick-access tile. Dashboard maps account modes
onto existing feeds and getSpotifyTracks (recent/added order), with getStarred2 for favourites. Browse routing
replaces the library chip layout and owns playlist pages; search remains compatible. FavoritesView
owns the phone favourites page and its two-column layout, with a top create action and PresetGrid
rendering only preset tiles. Preset detail/create/edit routes belong to Favorites. PhoneHome no
longer renders presets; desktop Home keeps PresetGrid. TrackList owns the details sheet
and reuses its handlers, with trackListLines controlling the extra metadata line.

Bound TransportTracker's pending expectation to three repeated non-null states at the same
track/index. Settle quietly to preserve queue-replacement loop protection, but emit the changed
snapshot. Player reconciles durationchange by trackId without directional fallback; car mode
also adopts the snapshot on mount. No shared API contract changes.
