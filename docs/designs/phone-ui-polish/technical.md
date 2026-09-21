# Phone UI polish — Technical Design

Implements [`functional.md`](functional.md). All paths are under `services/frontend/src/lib/` unless
stated otherwise. The phone UI is the Svelte bundle that `prepareWebBundle` stages into the Android
app, so nearly all of this is frontend work; only increment H touches Kotlin.

## Data Model

No schema change anywhere. Two new client-side stores, both device-local:

- **Recent places** (E): `localStorage` key `muma.recentPlaces.<serverUrl>.<username>`, a JSON array
  of `{view, title, kind, at}` (newest first, max 12). `view` is the navigation string the app already
  uses for eight of the nine kinds (`artist:<id>`, `album:<id>`, `genre:<name>`, `label:<name>`,
  `festival:<name>`, `preset:<id>`, `year:<n>`, `memories:<year>`); `playlist:<id>` is the one
  exception -- a playlist is not itself a real `activeView` (it opens as `'playlist-detail'` with the
  id in the separate `currentPlaylist` store, see `router.js`), so `App.svelte`'s `handleNavigate`
  translates `playlist:<id>` to that mechanism and back, and it is only ever a recent-places
  identifier. `kind` is the prefix without its colon, `at` is epoch ms. Keyed per server and account
  so a second login never shows another library's places; a place whose title never resolved (an
  id-based place that only ever got the bare `recordPlace(view)` from `handleNavigate`) stays in
  storage but is skipped by `RecentPlacesRow.svelte`.
- **Queue source** (E): a Svelte store `queueSource` in `store.js`, `{view, name} | null`, set by
  `queue.js`'s `startQueue(tracks, {name, view})` -- the one function every code path that used to
  call `playlist.set(...)` from a view now calls instead, so `queueSource` can never lag behind the
  playlist it describes. `view` defaults to the current `activeView`; a restore rather than a new
  start (the jam sync in `Player.svelte`, session rehydration in `nativeSession.js`) passes
  `view: null` explicitly, which `startQueue` turns into `queueSource.set(null)` rather than
  attributing the restored queue to whatever view happens to be open. Not persisted, so a WebView
  restart falls back to the track's own album, as before this existed.

## API Contract

No new endpoints. Existing calls used, per increment:

| Increment | Call | Notes |
|---|---|---|
| A | `GET /rest/getCoverArt?id&size=512` | Full-screen artwork; the mini player keeps `size=100`. |
| A | `getArtistImageUrl(artist)` (`utils.js`) | 404 when MuMa has no image, so `<img onerror>` is a reliable "no artist image" signal. |
| A | `fetchGenreTints()` (`genreTints.js`) → `/api/library/genres` | Per-genre tint, server-owned. Never compute a colour client-side. |
| D | `getSpotifyTracks` `sort=recent|added`, `min/maxDuration=10` | Already fetched by `PhoneHome.svelte`; the shelf reuses those arrays. |
| D | `memoryGroups` prop | Already loaded by `Dashboard.svelte`. |
| F | `getSpotifyTracks?artistId=` | More from this artist, `count=6`. |
| F | `getSpotifyTracks?workId=` | Other versions (the same call `SongView.svelte` makes). Never play a MuMa song-version id; only LMS track ids from this call. |
| G | `/api/listening/top-artists`, `/api/listening/top-labels` | Returns MuMa artist ids; resolve to LMS artists by name via `search3` before linking, or link to `artist-name:<name>` if such a view exists. |
| H | `MumaSystem` Capacitor plugin: methods `outputRoute()`, `openOutputPicker()`; event `outputRouteChanged` | `platform.system`, not `platform.player`: the system plugin already owns Bluetooth (`listBondedDevices`). See section H and Cross-App Impact. |

## Design decisions

### A — artwork and tint

- New component `Artwork.svelte` (props: `coverUrl`, `artistUrl`, `tint`, `title`, `size` class)
  owning the fallback chain as explicit state `cover | artist | panel`, advanced by `onerror`.
  Reset to `cover` whenever `coverUrl` changes (a stale error from the previous track must not skip
  the new track's cover). Guard async: the state belongs to the URL it was computed for.
- Offline artwork goes through `coverArtSrc()` from `coverArt.js`, so the player and Home no longer
  build `/rest/getCoverArt` URLs by hand.
- Tint: `trackTint(track, tints)` in `genreTints.js` returns the tint of the first genre in
  `genreNames(track.genre)` that has one, else `null`. Background in `NowPlaying.svelte`:
  `linear-gradient(to bottom, color-mix(in srgb, <tint> 55%, #121212) 0%, #121212 60%)`; `null`
  renders the plain `#121212`. `Player.svelte` fetches tints once (`fetchGenreTints()`) and passes
  `tint` as a prop, same as it passes `coverUrl`.
- The panel fallback is a `div` in the tint (or `#282828` without one) with the title in
  `text-2xl font-bold` centred and `line-clamp-3`; text colour white with a `bg-black/25` wash, the
  same readability rule `QuickAccessTile.svelte` uses.
- `app.css`'s `img.w-full[src="/images/spotify-fallback.svg"]` rule stops applying to the player
  because the player no longer renders that file at full width; the rule stays for shelves.
- Mini player: the 44px slot becomes `<Artwork size="w-11 h-11">`; the 16px artist avatar and its
  `getArtistImageUrl` call are removed from the mini player.
- Since 2026-09-20 the rows and cards (`TrackRowCompact`, `TrackCard`) run the same chain as the
  player instead of skipping the portrait: `artistImageFallback(track, auth)` in `coverArt.js`
  builds the portrait URL from `primaryArtistOf(track)` (`utils.js`, the `artists` array first,
  the joined string second) and answers `null` for a URL in `missingArtistImages`, the Set
  `Artwork.svelte` fills from its artist `onerror`. MuMa's 404 is not cached by the browser, so
  without that Set every row of the same artist re-asked on every render.

### B — header, chips, targets

- Header: `nowPlaying.playingFrom` split into two i18n keys, `nowPlaying.playingFromLabel` (caption,
  `text-[11px] text-[#b3b3b3]`) and the name (`text-sm font-bold text-white truncate`). Until E
  lands the name is still `track.album || queue.title`.
- ⋮ opens the existing `TrackDetailsSheet` (it already has artist, album, play next, add to queue,
  lyrics); the lyrics header button is folded into it. The bottom-row `(i)` button is removed as a
  duplicate; the EQ, versions and queue buttons stay.
- Genre/label chips: extract the chip markup of `TrackDetailsSheet.svelte` into `MetaChips.svelte`
  and use it in both. Drop `max-h-8 overflow-hidden`; drop the date item from `metaItems`.
- `ArtistList.svelte` gains a `size="lg"` variant: `py-2`, chevron after the last name.
- Stars: `w-11 h-11` buttons with a 24px glyph in the full player. Rating still flows through the
  `onrate` prop into `Player.svelte`'s `updateRating()`.
- Icons: shuffle/repeat at 24px, bottom row 24px, all `fill="currentColor"`; the EQ icon becomes a
  filled glyph. No new icon library.

### C — Home and Browse layout

- `PhoneHome.svelte`: `subtitle()` gains a per-destination empty string (`dashboard.empty.<id>` i18n
  keys) and a `state` per shelf (`loading | ready | failed`) driven by the existing effects; a
  failed load shows `dashboard.loadFailed`. Tile grid: when the rendered tile count is odd the last
  tile gets `col-span-2`.
- `HomeShelf.svelte`: "show all" loses `uppercase tracking-[0.1em]`, becomes `text-[13px]`.
  New prop `layout="cards" | "rows"`; `rows` renders `TrackRow`-style compact rows (48px thumbnail,
  title, artist) and is what Home's recent shelves use.
- `MobileSearchView.svelte`: the advanced-search card moves out; `TopBar.svelte` on the Browse route
  gets a filter icon button beside the search field that navigates to `new-preset`.
- `BrowseGrid.svelte`: `h-24` → `h-[68px]`, icon 32px.

### D — Home rows

- `PhoneHome.svelte` renders, below the destination shelves: a Memories year row (a plain `<section>`,
  not a new `MemoryYearShelf` component) with one `MemoryYearCard.svelte` per `yearTiles(memoryGroups)`
  entry in a horizontally-scrolling strip (`w-[140px]` tiles, matching `HomeShelf`'s mobile card
  layout), shown when `memoriesOnHomeEnabled` and the year list is non-empty; `onopen` navigates to
  `memories:<year>`, `onplay` calls the new `playMemoryYear(year, groups, authParams)` helper in
  `memories.js`, shared with `MemoriesView.svelte`'s own play button so the fetch-the-whole-year-then-
  fall-back-to-the-summary rule lives in one place.
- Below that, one fallback `HomeShelf layout="rows"` for whichever of `recentlyAdded` (songs) /
  `recentlyReleased` (sets) matches `$viewMode` -- but only when *neither* of the two "recent"
  destinations is already in `OVERVIEW` mode, so the shelf a destination's own mode already draws is
  never repeated. Both rows reuse the arrays `PhoneHome` already fetches for its tiles; no extra
  requests.
- `MemoryYearCard.svelte`'s no-cover branch (`shown.length === 0`) now renders `Artwork.svelte` with
  `coverUrl={null}` and the year as `title`, instead of the generic `/images/spotify-fallback.svg`
  image, so a yearless cover reads as designed rather than as a missing image.

### E — recent places and queue source

- New `recentPlaces.js`: `PLACE_PREFIXES` (the nine tracked kinds, each written with its trailing
  colon so a prefix check is a plain `startsWith`), `recordPlace(view, title = null)`,
  `recentPlaces` writable store, `placeTitle(place)`, `clearRecentPlaces()`. A module-level
  `credentials.subscribe` recomputes the `localStorage` key and reloads the list whenever the
  server or account changes; an empty username clears the store and blocks every write, so a
  browser nobody has signed into never renders (or persists) a place. Every `localStorage` call is
  wrapped in try/catch -- a private-mode failure leaves `recentPlaces` working in memory only for
  the rest of the session. `placeTitle` returns the stored title, else the argument itself for
  `genre:`/`label:`/`festival:`/`year:`/`memories:` (a year reads as the year), else `null` for an
  id-based place (artist, album, playlist, preset) that has not resolved a name yet.
- Recording happens in two places, not one: `App.svelte`'s `handleNavigate(view)` -- the single
  function every navigation in the app passes through -- calls `recordPlace(view)` right after
  moving `activeView`, which is enough on its own for the five argument-based kinds (genre, label,
  festival, year, memories: `placeTitle` reads the name straight out of the view string). The four
  id-based kinds (artist, album, playlist, preset) are opened by id, so their own view --
  `ArtistView.svelte`, `AlbumView.svelte`, `PlaylistView.svelte`, `PresetView.svelte` -- calls
  `recordPlace(view, name)` again once its load resolves, backfilling the title on the same entry
  `recordPlace` already deduped by `view`. `handleNavigate` also special-cases `playlist:<id>`: it
  is not a real `activeView` (see Data Model), so this is the one spot that translates it into
  `currentPlaylist.set({id})` + `activeView.set('playlist-detail')` before recording it, so a tap on
  a recent playlist tile works the same as opening one from a card.
- `browseColors.js` holds `TILE_COLORS`, pulled out of `BrowseGrid.svelte` (which now imports it)
  so `RecentPlacesRow.svelte` can colour a recent place the same as its category tile from one
  table instead of two that could drift; a preset borrows the `starred` colour and the
  `nav.playlists` label, since neither table has an entry of its own for it.
- `RecentPlacesRow.svelte` renders nothing when no recorded place has a resolved `placeTitle`;
  otherwise a `mobile.recent` heading and a horizontally-scrolling strip of `QuickAccessTile`s (title
  = `placeTitle`, subtitle = the kind's `nav.*` label, colour = `browseColors.js`). Tapping a tile
  calls `onnavigate(place.view)`. `MobileSearchView.svelte` renders it between the heading and
  `BrowseGrid`.
- New `queue.js`: `startQueue(tracks, {name = null, view = get(activeView)} = {})` sets
  `queueSource` (`{view, name}`, or `null` when `view` is `null`) and then `playlist`, in that order,
  so a subscriber to `playlist` never briefly sees a queue with the previous source still attached.
  Every call site that used to do `playlist.set(...)` from a view -- `ArtistView`, `AlbumView`,
  `PlaylistView`, `PresetView`, `FeedView`, `DailyMixCard`, `MemoriesYearView`/`memories.js`,
  `StarredView`, `DownloadsView`, `VoiceView`, `CarModeView`, `TrackList`, plus `App.svelte`'s
  `clearQueue` (`startQueue([], {view: null})`) -- calls `startQueue` instead, passing a human name
  where one is already at hand and leaving it `null` (so the header falls back to `placeTitle`/
  `viewLabel`) where the caller only has a view. `Player.svelte`'s jam sync and
  `nativeSession.js`'s `rehydrateQueue` are restores, not starts, so both pass `view: null`
  explicitly rather than letting the current view be credited with someone else's queue. `queue.js`
  also exports `viewLabel(view)`, which names a whole view with no id/name argument of its own
  (`songs`, `sets`, `starred`, `home`, `downloads`, `daily-mixes`, `memories`, and `search:<q>` as
  the literal query) through the `nav.*`/`memories.title` key that already exists for it, resolved
  with `get(t)` since this is a plain module, not a component.
- `NowPlaying.svelte` reads `queueSource` for both the header text and its tap target:
  `playingFrom` is `$queueSource?.name ?? placeTitle({view: $queueSource?.view}) ??
  viewLabel($queueSource?.view) ?? track?.album ?? $t('queue.title')`; the header button navigates
  to `queueSource.view` when it is one of `PLACE_PREFIXES` (so "Playing from Hardstyle" opens that
  genre), else to the track's album as before `queueSource` existed.

### F — continuation sections

- `Player.svelte` derives `queueIndex`, the one number the whole increment is built on: native
  (`nativePlayback`) reads `nativeQueue.currentIndex()` (new getter on `createNativeQueue`,
  returning its private `pushedIndex`); browser is `$playlist.findIndex(t => String(t.id) ===
  String($currentTrack?.id))`, the same lookup `playNext`/`playPrev` already did. `pushedIndex` is
  kept current in three places: `adopt()` (unchanged), a successful `push()` (unchanged), and the
  guard branch that used to return early with nothing sent because the service already reached
  that position by itself (a `command`, or its own advance) -- that branch now sets `pushedIndex =
  index` before returning, or a self-inflicted move would leave it pointing at the position of the
  *previous* edit forever. Because `nativeQueue` is a plain variable and not a store, `queueIndex`'s
  `$derived.by` also reads a `nativeQueuePositionTick` `$state` counter that `Player.svelte` bumps
  in a `.then()` after every `adopt()`/`sync()` settles, purely to give the derived a reason to look
  at `currentIndex()` again.
- `queueIndex` is passed to `<NowPlaying queueIndex>` as a prop (default `-1`).
- `NowPlaying.svelte` renders three sections in a `flex flex-col gap-6 mt-8` block after the bottom
  icon row, each independently hidden with nothing to show:
  - **Next up** (`nowPlaying.nextUp`): `shuffleMode` true → empty list, and the section shows one
    line (`nowPlaying.shuffleOn`) instead of rows. Otherwise the three entries after `queueIndex` in
    `$playlist` *by position* (`list[queueIndex + step]`), not by id -- a duplicate id elsewhere in
    the queue must not make this land on the wrong copy. Wraps to the start of the queue only when
    `repeatMode === 'all'`; otherwise the preview simply runs out short. Hidden when the list is
    empty and shuffle is off.
  - **More from artist** (`nowPlaying.moreFrom`, `{name}` = the first artist's name, matching
    `artistId`): fetched only while `open` and `track.artistId` is set, via
    `subsonicJson('getSpotifyTracks', {artistId, count: 7})` → `listOf(data, 'tracks.track')`,
    current track id dropped, capped at 6. Cached per `artistId` (a plain `fetchedArtistId`
    closure variable, not `$state`) so reopening the player for the same artist does not refetch; a
    track with no `artistId`, or a different one, clears the cache instead of leaving it to leak
    under an unrelated track. A "show all" link navigates to `artist:<id>`.
  - **Other versions** (`track.versions`): only when `track.workId`, via the paging loop pulled out
    of `SongView.svelte` into new `versions.js`'s `loadVersions(workId, {max = 500})` -- `SongView`
    keeps its true count (`max` left at the default), this section asks for `{max: 6}` so the
    request itself stays small. Current track id dropped; hidden when the remainder is empty.
  - All three use `TrackRowCompact` with its new optional `onplay` prop (`(onplay ??
    playTrack)(track)` on tap): a "next up" row calls `playTrack(entry)` -- a jump within the
    playing queue, `$playlist` untouched -- while "more from artist" and "other versions" rows call
    `startQueue(list, {name, view})` (`queue.js`) first, so tapping either starts a fresh queue of
    that section's own list before playing the row picked.
- `addAfterCurrent()` (in `NowPlaying.svelte`, the details sheet's "play next") inserts at
  `queueIndex + 1` when `queueIndex >= 0`, else appends -- not `findIndex` by the track's id, which
  used to land the insert next to the *first* copy of a repeated id rather than the one actually
  playing.
- The scroll container (`px-6 pb-6 overflow-y-auto`, previously just tall enough for the artwork and
  transport) is now bound (`bind:this`); `handleTouchEnd`'s swipe-to-close only fires when
  `scrollContainerEl.scrollTop === 0`, since the continuation sections gave the screen something to
  scroll through that a downward drag must be allowed to reach.

### G — rankings

- New `homeRankings.js`: `loadTopArtists(fetcher)`/`loadTopLabels(fetcher)` GET
  `listeningUrl('top-artists'|'top-labels', { ...periodRange('30d'), limit: 8 })` with
  `getHeaders()` from `mumaApi.js` (the listening endpoints need the MuMa key, not the Subsonic
  credentials); each resolves to `[]` on any failure or non-OK response, same soft-fail contract as
  `loadListening`'s own `get()`. Rows are mapped down to `{name, listens}` (`artist`/`label` field
  from the router's response, never the row's own `artist_id`/`label_id`).
- `resolveArtistView(name)` calls `subsonicJson('search3', { query: name, artistCount: 3,
  albumCount: 0, songCount: 0 })`, reads `listOf(data, 'searchResult3.artist')`, and returns
  `artist:<id>` for the entry whose name matches case-insensitively, else the first entry, else
  `null`. Memoised in a module `Map<name, Promise<view|null>>` keyed by name -- storing the promise
  itself, not just its result, is what makes two concurrent lookups for the same name share one
  request instead of firing a second. Wrapped in try/catch, so any failure resolves to `null`. MuMa's
  own `artist_id` (carried by `/api/listening/top-artists`) is never used for navigation: it names a
  row in MuMa's own artist table, not an LMS entity.
- `PhoneHome.svelte`: two `QuickAccessTile` strips after the fallback recent shelf, one per ranking,
  each with its own `data-testid` and a "Alles tonen" (`dashboard.showAll`) to the `listening` view.
  Loaded once `onMount`, stale-guarded, only when `$mumaApiKey` is set -- no request at all otherwise.
  Colours reuse `browseColors.js`'s `TILE_COLORS.artists`/`.labels`, the same table
  `RecentPlacesRow.svelte` draws from. An artist tap awaits `resolveArtistView(name)` and navigates
  to the result, or to `search:<name>` when it resolves to `null`; a label tap navigates straight to
  `label:<name>` (label views already take the name, no id involved). Both rows hidden together
  without the key, and each hidden on its own when its ranking is empty.
- New i18n: `dashboard.topArtists`/`dashboard.topLabels` (en/nl only, following `dailyMixesSubtitle`'s
  precedent of not backfilling the two dialects for a brand-new dashboard row) and
  `common.listenCount` (en/nl, ICU one/other plural, mirroring `common.trackCount`).

### H — audio output (Kotlin)

- Contract (`platform/index.js`, `PlatformSystem` — on `system`, not `player`, since the system
  plugin already owns Bluetooth): `outputRoute(): Promise<OutputRoute|null>`,
  `onOutputRouteChanged(handler): unsubscribe`, `openOutputPicker(): Promise<void>`, with
  `OutputRoute = {name: string, type: 'bluetooth'|'wired'|'speaker'|'usb'|'other'}`. The browser
  (`platform/browser/system.js`) answers `null`, a no-op unsubscribe, and resolves; the Capacitor
  adapter (`platform/capacitor/system.js`) forwards to the plugin and reads an answer or event
  without a non-empty `name` and a known `type` as `null`/dropped — the plugin resolves `{}` while
  it has no bridge context to read its strings from, and that must read as "nothing to show",
  not as a route called `undefined`. `other` is in the union for a shell that can name something
  outside the four; the Android shell never sends it.
- `MumaSystemPlugin.kt` (`services/muma-mobile/.../capacitor/`), with the pure parts in the new
  `AudioOutput.kt`: `outputRoute()` → `{name, type}` from `AudioManager.getDevices(GET_DEVICES_OUTPUTS)`
  through `outputRouteOf(devices, wiredName, speakerName)`: the first Bluetooth device
  (`TYPE_BLUETOOTH_A2DP`/`BLE_HEADSET`/`BLE_SPEAKER`/`BLE_BROADCAST`/`BLUETOOTH_SCO`/`HEARING_AID`)
  wins with its `productName` ("Bluetooth" when blank), then wired
  (`WIRED_HEADPHONES`/`WIRED_HEADSET`/`LINE_ANALOG`, named by `R.string.audio_output_wired`), then
  USB (`USB_HEADSET`/`USB_DEVICE`, `productName` or "USB"), else the speaker
  (`R.string.audio_output_speaker`) — also for an empty list, so the method never rejects.
  `getDevices` lists the *available* outputs, not the active one; Android has no public current
  media output short of `MediaRouter2`, and the order above is the order its own policy routes
  in, so the two agree for every case a phone user meets. Documented in the KDoc as a known
  limit. Strings are the app's own resources (`values/`, `values-nl/`), so the label follows the
  app language the same way the rest of the shell chrome does.
- `OutputRouteMonitor` (in `AudioOutput.kt`) registers an `AudioDeviceCallback` in the plugin's
  `load()` and unregisters it in `handleOnDestroy()`; every add/remove recomputes the whole route
  and emits `outputRouteChanged` with the same `{name, type}`. Started in `load()` rather than on
  first subscription because Capacitor has no "listener added" hook to pair a teardown with.
- `openOutputPicker()` tries `outputPickerIntents(packageName)` in order —
  `com.android.settings.panel.action.MEDIA_OUTPUT` with
  `com.android.settings.panel.extra.PACKAGE_NAME` (Android 11+'s output switcher; neither string is
  a public constant), then `Settings.ACTION_BLUETOOTH_SETTINGS` — through `startFirstResolvable`,
  which moves to the next only on `ActivityNotFoundException`. Resolves once one started, rejects
  when neither does. Started from the plugin thread, not `runOnUiThread`, so the exception is
  catchable where the fallback lives. Both are plain Activity intents, not `MediaController`
  commands, so the empty command-grant set does not apply.
- `MumaSystemPlugin` sits under detekt's `TooManyFunctions` ceiling (30) by keeping the watcher in
  its own class and the two pure `setSetting` helpers at file level; `safeContext`/`runningActivity`
  are properties, which the rule does not count.
- UI: `NowPlaying.svelte` props `outputRoute` and `onopenOutputPicker`; with a route it renders a
  `text-brand` button (`data-testid="now-playing-output"`, `aria-label` `nowPlaying.outputPicker`)
  with a glyph per `type` (wired/usb share the headset glyph, other/unknown fall back to the
  speaker's) on its own line above the bottom icon row, taking that row's `mt-auto`.
  `Player.svelte` reads `platform.system.outputRoute()` once on mount when `isNative`, subscribes
  with `onOutputRouteChanged` and unsubscribes on destroy; a picker rejection is logged, never an
  unhandled rejection from a click.

## Cross-App Impact

- **Web (desktop)**: `Artwork.svelte`, `HomeShelf` and chip changes are shared components; desktop
  keeps its layouts. Visual snapshots in `tests/browser/__screenshots__/` will change for the phone
  project and must be refreshed (`MUMA_UPDATE_SNAPSHOTS=1`, see `docs/frontend-screenshots.md`).
- **Android**: only H adds native code; A–G ship through the web bundle. The `MumaSystem` plugin
  methods are additive; an older bundle simply never calls them, and a newer bundle on an older
  APK gets a rejected call, which `Player.svelte` swallows into a `null` route.
- **Backend**: none.

## Technical Acceptance Criteria

1. `Artwork.svelte` unit tests: cover error → artist shown; artist error → panel with title; new
   `coverUrl` resets to cover; panel uses the given tint and `#282828` without one.
2. `trackTint()` picks the first genre with a tint; returns `null` for no genres and for genres the
   server did not list.
3. `NowPlaying` renders `background-image` with the tint and none without; header has no
   `uppercase` class and a button labelled by `nowPlaying.more`.
4. `metaItems` contains no date; every genre and the label render as chips.
5. `PhoneHome` shows the destination copy for an empty feed and `col-span-2` on the last of an odd
   tile count; `HomeShelf layout="rows"` renders rows, not cards.
6. `recentPlaces.js`: records newest first, dedupes by `view`, caps at 12, isolates by key, and
   survives a throwing `localStorage`.
7. `queueSource` is set when play-all runs from a genre view and the header shows that name.
8. `NowPlaying`'s "next up" preview lists the three entries after `queueIndex` by *position*, correct
   even with a duplicate id elsewhere in the queue.
9. `platform.test.js`: browser `system.outputRoute()` is `null`, `onOutputRouteChanged` never
   fires, `openOutputPicker` resolves; `platformCapacitor.test.js`: the adapter forwards all
   three and reads an empty/nameless/unknown-typed answer as `null`. Kotlin
   `MumaSystemPluginOutputTest`: Bluetooth beats speaker and wired, wired beats USB, blank
   `productName` becomes "Bluetooth", empty list is the speaker, the monitor emits on a device
   the shadow adds and not after `stop()`, the picker falls back to Bluetooth settings on
   `ActivityNotFoundException` and rejects when neither resolves.
10. Coverage floors in `vite.config.js` hold (82/65/79/81) after every increment.

## Related Docs

- [`universal-ui/`](../universal-ui/technical.md) — the shell these screens run in.
- [`mobile-cover-art/`](../mobile-cover-art/technical.md) — the genre-tint contract reused here.
- [`home-sections/`](../home-sections/) — the section modes `PhoneHome.svelte` renders.
- [`docs/styleguide.md`](../../styleguide.md) — the design backlog entry for this work.
