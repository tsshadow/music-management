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
| H | `MumaPlayer` Capacitor plugin, new method `outputRoute()` + event `outputRouteChanged` | See Cross-App Impact. |

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

- `NowPlaying.svelte` gets a `sections` block below the bottom row: `NextUp` (from `playlist` and the
  current index by *position*, respecting `shuffleMode` order when `player.ownsQueue` exposes it,
  otherwise the linear order), `MoreFromArtist` (lazy fetch on open, keyed by `track.artistId`,
  stale-guarded), `OtherVersions` (lazy, only when `track.workId`).
- `handleTouchEnd` closes only when the scroll container's `scrollTop === 0`.
- `addAfterCurrent()` uses the current queue position (from `playerState`/native snapshot) instead of
  `findIndex` by id.

### G — rankings

- `listeningStats.js` already wraps the endpoints; a small `rankingToView()` maps a MuMa artist name
  to `artist:<lmsId>` through `search3` (cached per session). Rows hidden without data or when the
  resolution fails.

### H — audio output (Kotlin)

- `MumaPlayerPlugin.kt`: method `outputRoute()` → `{name, type}` from
  `AudioManager.getDevices(GET_DEVICES_OUTPUTS)` preferring the active Bluetooth A2DP device's
  `productName`, else the built-in speaker; `AudioDeviceCallback` emits `outputRouteChanged`.
  Method `openOutputPicker()` fires the `com.android.settings.panel.action.MEDIA_OUTPUT` intent with
  `EXTRA_PACKAGE_NAME`; on `ActivityNotFoundException` falls back to
  `Settings.ACTION_BLUETOOTH_SETTINGS`. Both are plain Activity intents, not `MediaController`
  commands, so the empty command-grant set does not apply.
- `platform/index.js` contract gains optional `player.outputRoute()` / `player.openOutputPicker()`;
  the browser implementation returns `null` and the UI hides the control.

## Cross-App Impact

- **Web (desktop)**: `Artwork.svelte`, `HomeShelf` and chip changes are shared components; desktop
  keeps its layouts. Visual snapshots in `tests/browser/__screenshots__/` will change for the phone
  project and must be refreshed (`MUMA_UPDATE_SNAPSHOTS=1`, see `docs/frontend-screenshots.md`).
- **Android**: only H adds native code; A–G ship through the web bundle. A `MumaPlayer` plugin
  method is additive; an older bundle simply never calls it.
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
8. `NextUp` lists the three entries after the current *position* with duplicate ids in the queue.
9. `platformPlayer.test.js`: browser `outputRoute()` is `null`; the capacitor adapter forwards it.
10. Coverage floors in `vite.config.js` hold (82/65/79/81) after every increment.

## Related Docs

- [`universal-ui/`](../universal-ui/technical.md) — the shell these screens run in.
- [`mobile-cover-art/`](../mobile-cover-art/technical.md) — the genre-tint contract reused here.
- [`home-sections/`](../home-sections/) — the section modes `PhoneHome.svelte` renders.
- [`docs/styleguide.md`](../../styleguide.md) — the design backlog entry for this work.
