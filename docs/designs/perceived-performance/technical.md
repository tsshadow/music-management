# Perceived performance — Technical Design

Implements [functional.md](functional.md). Issue #107; code splitting issue #114.

## Data Model

None. Nothing is persisted: the entity cache and the seeds live in module memory and are gone after a
reload.

## API Contract

No endpoint changes. The artist page issues the same four requests as before (`getArtist`,
`getSpotifyTracks`, `getArtistInfo2`, `GET /api/curation/artists/{name}`), but the first three now
start together instead of one after another. `/rest` calls do not pass the MuMa gate
(`mumaGate.js`), so starting them together takes nothing from the `/muma` proxy lanes.

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| n/a | | | |

## Cross-App Impact

Frontend only (`services/frontend`). The MuMa Mobile app gets it through the bundled web UI, so no
Kotlin change. The boot screen stages come from `bootstrapShell` in `nativeSession.js`, which already
runs only inside the shell.

## Building blocks

### 1. Boot screen: `index.html` and `src/lib/bootScreen.js`

- `index.html` holds a `#boot-screen` overlay *outside* `#app`, styled inline, so it paints before
  any CSS or JS has loaded. It shows the MuMa mark, a status line (`[data-boot-stage]`), a hint line
  (`[data-boot-hint]`) and a 3px progress bar (`[data-boot-bar]`, indeterminate by default). It
  sits on `#191414` (`muma-spotify-black`, the body colour), so the fade-out never flashes.
- A small inline script picks the Dutch or English text for the pre-bundle line ("Laden…" or
  "Loading…") from `localStorage.muma_locale`, the key `i18n/index.js` stores. After 20 s it
  reveals a retry button that calls `location.reload()`, unless `window.__mumaBootDone` has been
  set by then. This is the one piece that must work when the bundle itself never runs, which is why
  it is not in the bundle.
- `bootScreen.js` (imported by `main.js`):
  - `setBootStage(stage, { done, total })` writes the translated text for `connecting`,
    `signingIn`, `restoringQueue` or `starting`. With `total > 0` it switches the bar to
    determinate (`width: done/total`).
  - Each stage restarts an 8 s timer that shows `boot.slow`.
  - `dismissBootScreen()` sets `__mumaBootDone`, fades the overlay out (200 ms, per the style
    guide's transition range) and removes it.
  - Every function is a no-op when the element is absent (vitest, a second mount).
- `bootstrapShell(platform, fetchImpl, onStage)` gains an optional `onStage` callback. It reports
  `connecting` before `applyServerUrls`, `signingIn` before `restoreSession` and
  `restoringQueue` before the queue restore. `rehydrateQueue` reports `{done, total}` as the
  `getSong` answers come in. The order of the boot sequence is unchanged; only its visibility is
  new.
- `main.js`: in the browser it mounts and dismisses. In the shell it runs `bootstrapShell` with
  `setBootStage`, then `starting`, then mounts and dismisses. Since #114 both paths first wait for
  the active locale's file and the chunks the URL's page needs (see 7 below), still behind the
  boot screen. `setBootStage` leaves the inline "Laden…" in place while the locale file is still
  on its way, rather than writing the raw key.

### 2. Entity cache: `src/lib/entityCache.js`

`createEntityCache({ maxEntries = 100, freshMs = 60_000, maxAgeMs = 300_000, now })`:

- `peek(key)` returns `{ value, fetchedAt, fresh }`, or `null` when the entry is missing or older
  than `maxAgeMs`, in which case it is also dropped.
- `set(key, value)` and `update(key, fn)`. `update` is for optimistic edits such as a star toggle,
  so a revisit shows the edit and not the pre-edit copy.
- `load(key, loader, { force })` deduplicates in-flight requests per key: a prefetch and the page
  that follows share one request. On success it stores the value. A failure is never cached.
- `swr(key, loader, onValue)` calls `onValue(cached, { fromCache: true })` synchronously when there
  is a usable entry. When the entry is missing or older than `freshMs`, it loads and calls
  `onValue(fresh, { fromCache: false })`. It returns the promise (resolved with the cached value
  when no refresh was needed) so callers can await errors.
- `invalidate(keyOrPrefix)` and `clear()`.
- LRU eviction: a `Map` in insertion order, with every read moving the entry to the end.

The singleton `entityCache` (in `entityLoaders.js`) is cleared whenever the signed-in username
changes, so a second account on the same device never sees the first one's star state.

### 3. Seeds and prefetch: `src/lib/entitySeeds.js`, `src/lib/entityLoaders.js`

- `seedEntity(kind, id, seed)` merges a summary (`name`, `coverArt`, `artistImageUrl`, and for
  albums `artist`, `artistId`, `year`) into a bounded map (200 entries). Empty fields never
  overwrite known ones.
- `peekSeed(kind, id)` returns the seed or `null`.
- `artistSeedFromTrack(track)` and `albumSeedFromTrack(track)` build seeds from a track row.
- `openEntity(navigate, kind, entity)` seeds, then calls `navigate(\`${kind}:${id}\`)`. It is a
  drop-in for the existing `onnavigate(\`artist:${id}\`)` calls, so it works with both the
  `onnavigate` prop and Dashboard's `activeView = v`.
- `pressEntity(kind, entity)` seeds and calls the kind's registered prefetcher. Links call it
  from `onpointerdown`. A pointerdown that never becomes a click costs one request that lands in
  the cache.
- `entityLoaders.js` registers the prefetchers and holds the loaders the pages use:
  - `artistKey(id)`, `artistTracksKey(id, mode, dedupe)`, `albumKey(id)`.
  - `fetchArtist(id)`, which returns the `getArtist` artist and throws `NotFound` when it is
    absent.
  - `fetchAlbum(id)`, which returns `{ album, tracks }`.
  - `prefetchArtist(id)` and `prefetchAlbum(id)`, both through `entityCache.load`.

  Only the artist's main request is prefetched, not the tracks, to keep a press to one request.

### 4. Loading UI: `Skeleton.svelte`, `SkeletonRows.svelte`, `SkeletonTiles.svelte`, `Throbber.svelte`, `SectionState.svelte`

- `Skeleton`: a block in the new `muma-skeleton` token (`#2F2F2F`, the style guide's placeholder
  colour) with the `skeleton-pulse` animation (opacity 1 → 0.4, 700 ms, alternate; none under
  `prefers-reduced-motion`). It is `aria-hidden`, with its shape passed as `class`.
- `SkeletonRows`: `count` track-row placeholders with TrackList's geometry (`h-14 md:h-16`, a 48px
  cover, two text lines). The container is `role="status"` with `aria-label={common.loading}`.
- `SkeletonTiles`: `count` card placeholders on the artist-page grid (`grid-cols-3`,
  `md:auto-fill minmax(180px)`), square or round.
- `Throbber`: an inline 16px (`size` prop) ring in `currentColor` with `animate-spin` and
  `role="status"`. It is for "this action is waiting", such as a play button pressed before its
  tracks arrived, and for a background refresh next to a section heading.
- `SectionState`: `status` (`loading` | `error` | `ready`), an `onretry` callback, and `skeleton`
  and `children` snippets. The error state is one muted line ("Kon dit deel niet laden") and an
  outlined "Opnieuw" pill (the Load-more pill). A section keeps rendering its `children` while it
  refreshes in the background: the style guide's Refresh rule.

### 5. Pages

**Artist (`ArtistView.svelte`)**

- Header: `artist ?? seed`. Name, picture (`getArtistImageUrl` works with a seed's
  `name`/`coverArt`) and the action buttons render at once. With neither, there is a round
  skeleton picture and a skeleton title bar.
- On `artistId`, it starts three loads together:
  - `entityCache.swr(artistKey)` feeds the header and the albums sections.
  - `swr(artistTracksKey(id, mode, dedupe))` loads the first tracks page; "load more" stays
    uncached.
  - `swr(artist-info)` loads the biography and similar artists.
  - The MuMa genre rules load once the server's name is known.
- Each has its own status. The tracks section shows `SkeletonRows` (8), the albums section
  `SkeletonTiles`, and "about"/"similar" render nothing until they have data (optional sections, as
  before). Failures are per section, except a failed `getArtist`: with no seed that is the old
  full "could not be loaded" message, and with a seed the header stays and an error line with a
  retry replaces the albums.
- A mode switch reloads only the tracks.
- Play or shuffle pressed while the tracks are loading sets `pendingPlay`. The button shows a
  `Throbber`, and the queue starts when the tracks arrive (cancelled on navigation).
- The star toggle updates the cache entry.
- `loadSeq` still guards against late answers.

**Album (`AlbumView.svelte`)**

- The header uses `album ?? seed`: name, cover, artist and year. The track list is
  `SkeletonRows` while `getAlbum` is pending, with SWR through `albumKey`.
- `getAlbumInfo2` starts in parallel with `getAlbum` instead of after it.

**Feeds (`FeedView.svelte`, issue #110)**

- `feeds.js` gains `streamFeedDetail(slug, auth, { limit, onHeader, onChunk })`. `onHeader` fires
  as soon as `GET /api/feeds/{slug}` answers, with the title/subtitle/band numbers,
  `nextOffset` and `chunks` (the paths cut into `SONGS_BY_PATH_LIMIT` = 100). The chunks are then
  resolved **in parallel** (they were sequential), each reporting `onChunk(index, {songs, failed})`
  as it lands; the joined result keeps chunk order, never arrival order. `loadFeedDetail` is
  `streamFeedDetail` without handlers and gains `failedChunks`. A chunk that fails is no longer
  counted as `unresolved`; `loadFeedPage` reports a page with a failed chunk as `failed` so its
  caller keeps the continuation. `resolveFeedChunk(paths, auth)` is exported for a retry.
- Why parallel is safe: `getSongsByPath` goes to `/rest`, which does not pass the serial MuMa gate,
  and a feed is at most two chunks (`feeds_size` ≤ 200), so the peak on LMS is two requests.
- The page holds one entry per chunk (`loading` | `ready` | `error`). The list shows every
  answered chunk up to the first one still loading (a failed one is skipped, not waited on), with
  `SkeletonRows` for what is still loading and a `SectionState` error with a per-chunk retry. A
  failed feed answer (`state: "error"`) is a `SectionState` error with a retry of the whole load,
  instead of the "nothing here" copy it used to share with an empty feed.
- Header: `detail.title ?? seed.name ?? fixed copy (radar, classic daily mix)`; with none of those
  a skeleton bar. The subtitle prefers the fixed copy over the seed, because the Home shelf's
  radar card carries its own placeholder text. `DailyMixCard` seeds `feed:<slug>` with `name` and
  `subtitle` (`subtitle` is a new seed field) before it navigates.
- The unresolved count sums the answered chunks' missing paths plus "Meer laden" pages. "Meer
  laden" only appears once every chunk has answered. The queue continuation is null until then, so
  a row tapped mid-load cannot start a queue that skips the chunk still loading. Play pressed while
  loading shows a `Throbber` and starts once the first page is whole.
- SWR: a whole first page (no failed chunk) is stored under `feedKey(slug)`. A revisit renders it
  at once; a stale one refreshes in the background with `loadFeedDetail` and is swapped in only if
  the listener has not used "Meer laden" meanwhile. `DailyMixCard`'s play button reads and fills
  the same entry.
- The daily mixes page shows five card-shaped skeletons instead of "Laden...".

**Song versions (`SongView.svelte`, issue #111)**

- `openSong(navigate, track)` in `entitySeeds.js` seeds `song:<workId>` with the row's title
  (`name`), `artist`, `artistId` and `coverArt`. TrackList's versions button, the track details
  sheet's "Versies" and Now Playing's versions button use it.
- `versions.js` `loadVersions(workId, { max, onPage })` calls `onPage(soFar, done)` after each
  page. The page draws each page as it lands, with `SkeletonRows` under it while more are coming
  and a `Throbber` next to the running count.
- Header: the version marked canonical once seen; before that the seed (the row that was tapped,
  usually that canonical) rather than whichever version came first; with neither, skeleton cover,
  title and artist. The header now carries the cover.
- A failed load keeps the pages that did arrive and shows the error line with "Opnieuw" (a forced
  reload). A whole list is cached under `songVersionsKey(workId)`; a revisit renders it at once.

**Track details (`TrackDetailsSheet.svelte`, issue #111)**

- The sheet already drew everything from the track at once. The tags section (the one MuMa call)
  now shows key/value skeleton rows instead of "Tags ophalen…", and its error line gains an
  "Opnieuw" pill that re-runs the fetch.

**Daily-mix card play button (issue #99)**

- Visible on `pointer-coarse` (always, 48px), revealed on hover or `focus-visible` otherwise. The
  screenshot projects run without touch emulation, so their references do not change.

**Link sites seeded in this MR:**

- `ArtistList` (every track row's artist, the player and Now Playing) and the TrackList album cells.
- Dashboard's album and artist grids and its search-results page.
- SearchBar results, SearchMoreModal and StarredView.
- ArtistView's albums and similar artists, AlbumView's artist.
- Now Playing's and the track sheet's "go to artist/album".

A link that is not seeded still works: it gets the no-seed skeleton header.

### 6. Tag lists and search (issues #109, #112)

**Tag track lists (`Dashboard.svelte`)**: songs, sets, `genre:`, `label:`, `podcast:`,
`festival:`, `year:`, `lineup:`.

- The heading is the route argument, so the name is right from the first frame. There is nothing to
  seed: the link *is* the name.
- `tracksStatus` (`loading` | `error` | `ready`) drives a `SectionState` with `SkeletonRows`
  (10). The track list has its own `tracksLoading` flag; the collection grids keep `isLoading`.
  Sharing one let a finished grid load mark the track list done.
- `loadAllTracks()` decides what stays on screen before it asks:
  - a cached copy of the exact query: shown at once (`ready`), refreshed in the background unless
    fresh;
  - a different place (`activeView` changed), or nothing on screen: rows cleared, `loading`;
  - the same place under new filters: rows kept and marked stale (`opacity-50`, `data-stale`), with
    a `Throbber` next to the heading.
- A `tracksLoadSeq` counter drops a late answer, and the previous request is aborted. A background
  refresh never replaces rows once "load more" has added pages to them.
- Failure: with no cached rows, `error` (offline: `ready` and the offline empty state); a failed
  refresh leaves the cached rows.
- **Cache**: `src/lib/trackListCache.js`, a second `createEntityCache` instance (60 entries,
  `freshMs` 60 s, `maxAgeMs` 5 min), cleared when the signed-in user changes. The key is
  `listKey("tracks", query + count + dedupe)`, where the query is `trackQueryParams()`, the same
  object the page and its queue continuation send. The value is the first page with its
  `nextOffset`, `hasMore` and the version keys folded so far (`seen`, as entries), so "load more"
  after a cached first page continues exactly as after a fresh one. Only the first page is cached.
- **Small first page**: without a cached copy, the first request asks
  `firstTrackPageSize(pageSize)` = `min(pageSize, FIRST_TRACK_PAGE)` (50) rows. Once those are on
  screen, `topUpFirstPage` calls `topUpTrackPage`, which continues from the page's `nextOffset`
  with `count` = what is missing and folds versions against a *copy* of the page's `seen` entries
  (a failed or aborted top-up leaves `seenKeys` untouched, so no row is dropped as a duplicate of
  one never shown). The filled page replaces the cache entry; the key stays the full page size. A
  cached copy that is still short (a press prefetch, which asks only 50, or a top-up that never
  finished) is topped up the same way. A background refresh of cached rows asks the whole page in
  one go, so the rows on screen never shrink. `tracksLoading` is true during a top-up, which keeps
  "load more" and the scroll sentinel (both check it) off the same offset.
- **Abort**: `tracksController` is aborted by every new `loadAllTracks`, by the view effect when
  the new view is not a track list (`isTrackListView`), and on unmount; the top-up and "load more"
  travel with the same signal.
- **Prefetch**: `CollectionGrid` takes `onpress`, called on `pointerdown` (the favourite toggle
  stops propagation). Dashboard's `prefetchTrackView(view)` builds the query the view will ask,
  with the filter bar's genre, year and search cleared unless the view is the one it was last reset
  for (`resetTrackFiltersFor`), and calls `prefetchTrackList`, which goes through
  `trackListCache.load`: deduplicated with the page's own load, nothing when a fresh copy exists,
  and nothing offline. One request per press, as for artists.

**Search results page (`search:`)**

- Three sections, each with its own status: tracks through the path above, artists and albums
  through `loadSearchSection(kind, query)`, which uses `trackListCache.swr` with a
  `listKey(method, params)` key. Their rows live in `searchArtists`/`searchAlbums`, apart from the
  Artists and Albums grids, so neither page shows the other's rows.
- A section renders while `loading` (skeleton: `SkeletonRows` 5, or `SkeletonTiles` 6, round for
  artists), `error` (its own retry) or with rows. `searchPending` puts "Zoeken…" and a throbber
  next to the heading; "No results" needs all three `ready`, empty and not pending.
- A `searchSeq` counter drops answers for an earlier query.

**Search dropdown (`SearchBar.svelte`, `SearchResults.svelte`)**

- `loading` turns true on the input event, before the 300 ms debounce, and `error` is new.
  `SearchResults` shows the "Zoeken…" line (throbber, `search.searching`) while loading, with three
  `SkeletonRows` when there is nothing yet and the previous results at `opacity-50`
  (`data-stale`) when there are. "No results" only when not loading and not failed; a failure
  clears the results and shows `SectionState` error with `onretry`.

**Search "more" modal, History, Starred, Memories**

- `SearchMoreModal`: `SkeletonRows` (tracks) or `SkeletonTiles` (artists round, albums square)
  instead of the spinner; a failed or non-OK `search3` is `SectionState` error with retry.
- `History`: `SkeletonRows` on the first load (`isLoading` starts true), `SectionState` error with
  retry when the first page fails; the Refresh button keeps the rows and shows a `Throbber`.
- `StarredView`: header at once; the body is a "Nummers" section with `SkeletonRows` or the error
  and retry.
- `MemoriesView`: skeleton year tiles in the real grid (`minmax(220px)`); `MemoriesYearView`:
  a skeleton line beside the year and `SkeletonRows`. Memories keep their silent empty state on
  failure (an older server has no memories), as before.

### 7. Code splitting (issue #114)

**Measured before** (develop `e2f6b6a81`, `vite build` with the report below): one JS file,
1,289.18 kB (350.04 kB gzip), plus 83.66 kB CSS. Largest modules: `nl.json` 102 kB and
`en.json` 96 kB (all four locale files were imported eagerly), `Dashboard.svelte` 82 kB,
`Player.svelte` 70 kB, `GeneralSettings.svelte` 52 kB, `DeviceSettings.svelte` 50 kB, then
twenty-odd management tabs of 11-48 kB each (`UsersTab`, `GenreCurationTab`,
`ArtistCurationTab`, `ArtistImagesTab`, `ScannerTab`, `DownloadersTab` ...), `TrackList`,
`NowPlaying`, `FilterBar`. Sizes are Rolldown's rendered length, before minification.

**Measured after**: 99 chunks, 1,334.84 kB in total. The entry is 370.25 kB (106.80 kB gzip).
Its static imports -- `vendor` 70.27 kB, `platform`, `store`, `i18n` (the translator without any
dictionary) and a few small shared modules -- bring what loads before `main.js` runs to
488.95 kB (153.16 kB gzip). Before mounting it also waits for one locale: `nl` 90.61 kB
(31.02 kB gzip) or `en` 83.84 kB (28.71 kB gzip), so the first screen waits for about 580 kB
(184 kB gzip): 45 % of the old bundle, and the entry chunk alone is 29 %. The largest lazy chunks:
`Settings` 79 kB, `DownloadersTab` 49 kB, `AdvancedLibraryTab` 38 kB, `GenreCurationTab` 37 kB,
`UsersTab` 29 kB. Opening Management on its overview tab fetches `Management` 15 kB,
`ManagementSidebar` 7 kB and `OverviewTab` 12 kB instead of every tab.

**Measuring.** `vite.config.js` has a `bundleReport` plugin: `BUNDLE_REPORT=<file> vite build`
writes every chunk with its size, gzip size, static imports and modules by size, outside `dist/`
so it never ships. `node scripts/bundle-report.mjs <file> [modules-per-chunk]` prints it and sums
the entry's static-import closure. It is in-tree rather than `rollup-plugin-visualizer` so a
measurement needs no network install.

**The registry: `src/lib/lazyViews.js`.**

- `createLazyRegistry(loaders)` wraps a table of `() => import(...)`. `load(name)` memoises the
  promise (a preload racing the real open fetches once) and forgets a failure (the retry fetches
  again); `peek(name)` returns the component once it is in; `has`, `names`.
- `lazyViews`: `nowPlaying` (issue #119), `settings`, `settingsSidebar`, `management`, `managementSidebar`, `history`,
  `listening`, `starred`, `memories`, `memoriesYear`, `artistEdit`, `labelEdit`, `genreEdit`,
  `presetBuilder`, `voice`, `downloads`, `song`, `car`, `setup`, `searchMore`, `trackDetails`,
  `equalizer`.
- `settingsTabs` (issue #119): one chunk per settings tab, see the follow-up below.
- `managementTabs`: every entry of `MANAGEMENT_TABS` except `scrobble`, which takes two `bind:`
  props a props object cannot carry and stays in the `Management` chunk. A unit test keeps the
  two lists in step.
- `chunksForState(state)` maps a `pathToState` result to the chunks it needs: the page, the
  sidebar for settings and Management, and Management's open tab. `preloadState` fetches them and never
  rejects.
- `likelyNextChunks()` (settings and its sidebar, song versions, the search "more" modal, the
  details sheet) and `adminNextChunks()` (Management's shell, sidebar and overview tab);
  `preloadOnIdle(chunks)` fetches them one per `requestIdleCallback` slot (a 1.5 s timeout where
  there is none), so a tap in between never waits behind a parse.

**The renderer: `src/lib/LazyView.svelte`.** `name`, `registry` (default `lazyViews`), `props`
(spread onto the view) and `fallback` (`rows` or `none`). A chunk already in renders on the first
frame; otherwise `SkeletonRows` (8) for a page, nothing for an overlay or sidebar, and a failure
is `SectionState` error whose retry fetches again. `Dashboard.svelte`, `App.svelte`,
`Management.svelte` (`tabProps(tab)` builds each tab's props, read in the template so the tab
follows the shell's data), `Settings.svelte` (its tabs, issue #119), `TrackList.svelte`,
`NowPlaying.svelte` and `Player.svelte` render through it; `Player.svelte` holds `NowPlaying`
itself through `lazyComponent` (issue #119). `Management.svelte` also starts its tab's chunk while its own data is loading.

**Boot: `src/lib/bootChunks.js` and `main.js`.**

- `initialState(pathname)`: the login view when signed out, else `pathToState`, with Management's
  remembered tab filled in when the path names none.
- `mountApp` awaits `localeReady()` and `preloadState(initialState(...))` together, then mounts;
  in the shell this runs after `bootstrapShell` under the "starting" stage. The app therefore
  appears with the page the URL names, never with a skeleton in its place.
- After the first frame, `preloadLikelyNext()` runs `preloadOnIdle(likelyNextChunks())` and
  subscribes to `isAdmin`; the first `true` preloads `adminNextChunks()` once.
- `installChunkReload(window)` listens for Vite's `vite:preloadError`: a tab left open across a
  deploy asks for chunk names the new build replaced. It reloads once, and a second failure within
  10 s is left to `LazyView`'s retry, so an unreachable server never loops.

**Locales: `src/lib/i18n/index.js`.** `import.meta.glob("./locales/*.json")` without `eager`: each
locale is a chunk. `dictionaries` is a store, and `t` derives from it and the locale, so the page
re-renders when a file arrives. `requiredLocales(code)` is the fallback chain minus the trailing
English (`nl` -> `nl`, `sallands` -> `sallands, nl`, `en` -> `en`): Dutch is key-complete
(`localeFiles.test.js`), so a Dutch listener never reads English and does not wait for it.
`loadLocale` fetches the required files, then the rest of the chain in the background.
`locale.set`, `setLocaleFromAccount` and `resetLocaleToBrowser` switch at once when the files are
in, otherwise after the fetch (last switch wins), so the interface never shows keys. The unit
tests' setup file awaits `loadAllLocales()`, so tests render in any language synchronously.

**Vendor chunk.** `build.rolldownOptions.output.codeSplitting.groups` puts `svelte`,
`@capacitor/core`, `esm-env` and `clsx` in `vendor`, which only changes with a dependency bump and
so stays cached across deploys. The icon packages are left out: most icons belong to lazy views,
and a shared icon chunk would put them back on the first screen. The cost is a few dozen sub-1 kB
icon chunks, fetched in parallel with the view that needs them (Vite's preload helper), never in a
waterfall.

**Served by LMS.** `SpotifyResource` (`services/music-management-server/src/lms/main.cpp`)
serves `docroot/spotify`; it sent no cache headers. `cacheControlFor(relativePath)` now answers
`public, max-age=31536000, immutable` for files under `assets/` (content-hashed by Vite) and
`no-cache` for everything else, `index.html` and the SPA fallback included. The nginx reverse
proxy passes both through. `base` stays `/`: LMS serves the bundle at the root (or `/spotify`
behind the proxy's rewrite), and chunk URLs are `/assets/...` exactly like the entry's.

**Inside the app.** Capacitor serves `dist/` from the APK at `http://localhost/`
(`androidScheme: http`), so `/assets/<chunk>.js` is a local file read. No shell change;
`frontend:bundle` and `mobile:smoke` are unchanged.

**Follow-up: one-tap pages and the locale preload (issue #118).**

*Measured before* (develop `47fb21f4f`): entry 370.32 kB (106.81 kB gzip), initial JS (entry and
its static imports) 489.02 kB (153.17 kB gzip), plus the `nl` locale 90.61 kB (31.02 kB gzip):
579.63 kB (184.19 kB gzip) before the first screen. The entry still held `FilterBar` 38 kB,
`ArtistView` 29 kB, `CollectionBar` 21 kB, `AlbumView` 19 kB, `FeedView` 15 kB, `CollectionGrid`
11 kB, `PresetView` 10 kB and `PlaylistView` 5 kB (pre-minify).

*Measured after*: 109 chunks. Entry 299.94 kB (89.25 kB gzip, -19 % / -16 %), initial JS 420.33 kB
(136.53 kB gzip); with the locale 510.94 kB (167.55 kB gzip) before the first screen -- and the
locale no longer waits for the entry to run. The new chunks (minified): `FilterBar` 19.94 kB,
`ArtistView` 15.38 kB, `CollectionBar` 11.71 kB, `AlbumView` 10.28 kB, `FeedView` 7.77 kB,
`CollectionGrid` 6.14 kB, `PresetView` 5.83 kB, `PlaylistView` 3.23 kB. What remains big in the
entry is the first screen itself: `Dashboard` 89 kB, `Player` 70 kB, `TrackList` 41 kB,
`NowPlaying` 40 kB, `App` 24 kB, `LoginPage` 18 kB, `PhoneHome` 18 kB (pre-minify).

- *Registry.* `lazyViews` gained `artistPage`, `albumPage`, `feedPage`, `presetPage`,
  `playlistPage`, `filterBar`, `collectionBar` and `collectionGrid`. `chunksForState` maps
  `artist:`, `album:`, `preset:`, `playlist-detail` and the feed slugs to their page, and
  `listPartsForView(view)` the list pages to their parts: the track, album and artist lists (and
  `genre:`, `label:`, `podcast:`, `festival:`, `year:`, `lineup:`) to `filterBar`, the collection
  pages (`genres` ... `lineups`, `lineups:`) to `collectionGrid`, `playlists` to `collectionBar`.
  So a URL that opens on one of these still mounts with the page complete, behind the boot screen.
- *The optimistic heading.* `ArtistView` and `AlbumView` render through `LazyView` with its new
  `placeholder` snippet prop: `EntityPageShell.svelte` (4.6 kB pre-minify, in the entry) draws the
  page header from the seed -- picture, kind line, the name as `h1`, placeholder buttons -- with
  the same classes as the page, and skeleton rows below. The heading is therefore on screen at
  once whether or not the page's code is in, and when the page arrives nothing moves but the
  content. The page itself still renders its header from the same seed, so the swap is invisible.
- *Preloading.* `entitySeeds.registerPagePreloader(kind, fn)`; `pressEntity` calls it next to the
  data prefetch, and `lazyViews.js` registers `artist`, `album` and `feed`, so a press starts the
  page's code and its data in the same instant (`DailyMixCard` now presses as well as seeds).
  `likelyNextChunks` lists the one-tap pages first (artist, album, feed, filter bar, preset,
  collection grid, playlist, then settings and the rest), so in practice they are in before the
  first tap.
- *`bind:` parts.* `FilterBar`, `CollectionBar` and `CollectionGrid` take `bind:` props, which
  `LazyView`'s props object cannot carry. `lazyComponent(registry, name)`
  (`lazyComponent.svelte.js`) exposes the component as reactive `current` (set at once when the
  chunk is already in) and `load()`; `Dashboard` loads the parts `listPartsForView(activeView)`
  names and renders the component variable with its `bind:`s. While a grid's chunk is on its way
  the page shows `SkeletonTiles`; the bars render nothing for that moment. `CollectionGrid`
  imports `CollectionBar` statically, so the two share one chunk fetch.
- *Locale `modulepreload`.* The `localePreload` plugin in `vite.config.js` reads the locale chunks'
  hashed names from the bundle in `transformIndexHtml` (build only) and inlines
  `preloadLocaleFiles` (`src/lib/i18n/localePreload.js`) into `index.html`'s `<head>` with a plan
  of locale -> files (`localePreloadPlan`: a dialect needs itself and `nl`, the rest only
  themselves, exactly `requiredLocales`; a unit test keeps the two in step). The script picks the
  locale as `resolveInitialLocale` does (stored `muma_locale`, else the browser language when there
  is a file, else English) and appends `<link rel="modulepreload" crossorigin>` for its files, so
  the locale downloads in parallel with the entry instead of one round trip after it. It never
  throws, and avoids `Object.hasOwn` for older WebViews. The URLs use `base` (`/assets/...`) like
  the entry's own `<script>`, which is what LMS (immutable `assets/`, `no-cache` index) and the
  APK's `http://localhost/` both serve. The dev server has no bundle and gets no script. An account
  language that differs from the browser's still switches after sign-in, as before.
- *Not done here.* Splitting `Settings` per tab and moving `NowPlaying` out of the entry: done
  in issue #119, below.

**Follow-up: settings tabs and Now Playing (issue #119).**

*Measured before* (develop `061eeb062`): entry 299.94 kB (89.25 kB gzip), initial JS 420.33 kB
(136.53 kB gzip). The `Settings` chunk was 79.25 kB (17.27 kB gzip) with all five tabs in it
(`GeneralSettings` 52 kB, `DeviceSettings` 50 kB, `About` 18 kB, `Advanced` 8 kB, `Help` 5 kB
pre-minify), and the entry still held `NowPlaying` (40 kB pre-minify).

*Measured after*: 120 chunks. Entry 255.22 kB (75.93 kB gzip, -15 % / -15 %); initial JS
405.04 kB (133.26 kB gzip, -15 kB / -3 kB). The initial figure falls by less than the entry
because `lazyViews.js`, `router.js` and `collections.js` (29 kB together) left the entry for
shared chunks that the settings tab chunks import too, which are still static imports of the
entry; and the entry gained `NowPlayingShell` (8 kB pre-minify). `NowPlaying` is 23.30 kB
(7.60 kB gzip). `Settings` is now 2.00 kB, and each tab is its own chunk: `GeneralSettings`
31.75 kB, `DeviceSettings` 29.65 kB, `About` 10.16 kB, `Advanced` 4.92 kB, `Help` 3.57 kB. Opening
settings on General in a browser fetches `Settings`, `SettingsSidebar` and `GeneralSettings`:
36.11 kB (9.11 kB gzip) instead of 81.49 kB (18.49 kB gzip); the device tab is never fetched
outside the shell.

- *Settings tabs.* `settingsTabs` in `lazyViews.js` registers `general`, `advanced`, `about`,
  `help` and `device` (a unit test keeps it in step with `SETTINGS_TABS`).
  `visibleSettingsTabs(native)` is the sidebar's list (`device` only in the shell),
  `settingsTabName(tab)` the tab `Settings.svelte` actually renders (an unknown name, or
  `device` outside the shell, is `general`), and `nextSettingsTab(tab)` the one after it in the
  sidebar, wrapping round. `Settings.svelte` renders the tab through `LazyView` with its
  `placeholder` snippet set to `SettingsTabSkeleton.svelte` (title and subtitle bars, two panels
  of label-and-toggle rows, the tabs' density classes), and once the tab is in asks
  `preloadOnIdle` for the next one. `SettingsSidebar` starts a tab's fetch on `pointerdown`.
  `chunksForState` adds the open tab to settings' chunks, and `initialState` fills it in from
  `activeSettingsTab` when the path names none, so `/settings` opened by URL still mounts
  complete behind the boot screen. `likelyNextChunks` preloads `general` after the settings
  shell and sidebar.
- *Now Playing.* `lazyViews.nowPlaying` is `NowPlaying.svelte`. `Player.svelte` holds it as
  `lazyComponent(lazyViews, 'nowPlaying')` rather than through `LazyView`: once loaded it stays
  mounted open or closed, exactly as before, so its `in:fly` on open and its own state (the
  details sheet, fetched versions) behave as they did. It loads on idle as the first entry of
  `likelyNextChunks`, on `pointerdown` on the mini player (not on its buttons), and at the
  latest when `nowPlayingOpen` turns true. Until it is in, an open Now Playing renders
  `NowPlayingShell.svelte` from the same props the mini player already has: the tinted
  background, the header with "Playing from", the cover (`Artwork`), title, artist and album,
  and a working play/pause; the rating, progress bar and other transport buttons are skeleton
  blocks of the same geometry. The shell's root carries `in:fly`, so opening animates at once;
  when the real view arrives, its `{#if open}` block is created together with the component,
  a local transition does not play, and the swap is a single frame with nothing moving. The
  "Playing from" line and the tinted background come from `nowPlayingContext.js`
  (`playingFromLabel`, `nowPlayingBackground`), which both components use, so the two never
  disagree. `lazyComponent` gained a reactive `failed`; the shell shows the section error with
  "Opnieuw" under its header when the chunk fails, and the retry calls `load()` again. The mini
  player and the desktop player bar stay in the entry; phone, tablet (portrait and landscape)
  and desktop layouts are unchanged.
- *Deterministic unit tests (issue #120).* "the event log tab is reachable" timed out once on
  CI (pipeline 4022): the tab is a chunk, and under vitest its first `import()` compiles the
  component, which on a busy runner can outlast `waitFor`'s default second.
  `tests/unit/lazyTestUtils.js` has `loadLazy(...entries)`, `loadManagementTab`,
  `loadSettingsTab` and `loadLazyState(state)` (via `chunksForState`); a test that is about
  what a view does loads its chunk in a `beforeAll` (with `LAZY_HOOK_TIMEOUT_MS`, 60 s, since a
  cold compile of several can pass the 10 s hook default), and the view is then on the first
  frame because `LazyView` and `lazyComponent` `peek` first. This is applied to every test that
  !1106/!1109 had switched to `findBy`/`waitFor` (management, the proxy gate, the mobile drawer,
  the details sheet in `nowPlaying` and `trackDetails`, the filter bar in `dashboard` and
  `listContinuationViews`), which query synchronously again, and to the player tests that open
  Now Playing. Tests about the loading itself (skeletons, the seeded shell, retries) spy on the
  registry's `peek`/`load` instead. `LAZY_TIMEOUT_MS`/`lazyWait` (10 s) is there for the rare
  wait a click decides.

## Risks

- **Wrong seed.** Seeds are only ever replaced by server data, never merged into it. `ArtistList`
  links carry the name shown for that id. For a legacy comma-joined `artist` string, only the first
  name carries the id, as before.
- **Stale data.** At most 5 minutes old, and always refreshed after 60 s. Stars are kept correct by
  `update`. Other edits (the artist edit page) call `invalidate`.
- **Load on LMS.** Prefetch is one request per press, deduplicated with the page load. Starting the
  artist's requests together raises the peak from one to three `/rest` calls on the same server,
  which is what the page already did one round trip later. There is no hover or viewport prefetch.
- **A page opened before its chunk is in** shows skeleton rows for as long as the chunk takes:
  a local file read in the app, one request in a browser. The idle preload covers the most likely
  next pages; everything else pays it once per session.
- **A stale tab after a deploy.** Its `index.html` names chunks the new build replaced. It reloads
  once on `vite:preloadError`; `index.html` is `no-cache`, so the reload gets the new build.
- **The locale file.** Preloaded from `index.html` together with the entry (issue #118), so it no
  longer costs a round trip after the entry in a browser; a local read in the app. A listener whose
  account language differs from the browser's gets the browser's file preloaded and the account's
  fetched after sign-in, as before.
- **A one-tap page opened before its chunk is in** (issue #118): the artist and album pages show
  the seeded header and skeleton rows (`EntityPageShell`), the feed, preset and playlist pages
  skeleton rows, for one request in a browser. A press starts the chunk with the data, and the idle
  preload normally has it in before the first tap.
- **Screenshot suite.** The skeletons only exist while a request is pending. The captured routes
  (`/artists`, `/albums`...) are lists whose markup does not change. The boot screen is removed
  before the first capture.

## Technical Acceptance Criteria

1. `entityCache`: SWR returns the cached value synchronously and refreshes after `freshMs`. It drops
   entries after `maxAgeMs`, deduplicates in-flight loads, never caches a failure, evicts the least
   recently used entry, and `invalidate` accepts a prefix (`tests/unit/entityCache.test.js`).
2. Seeds: `openEntity` seeds and navigates, empty fields never overwrite, and track-derived seeds
   are built correctly (`tests/unit/entitySeeds.test.js`).
3. `ArtistView` with a seed and a never-resolving `getArtist` shows the seed's name and skeleton
   rows. With no seed it shows a skeleton header. `getSpotifyTracks` is requested before
   `getArtist` resolves. A failing `getArtistInfo2` leaves the tracks on screen. Play pressed while
   loading starts the queue when the tracks land (`tests/unit/artistView.test.js`).
4. `AlbumView` renders the seed header with skeleton rows while `getAlbum` is pending
   (`tests/unit/albumView.test.js`).
5. `SectionState` renders the skeleton, error (retry calls `onretry`) and content states
   (`tests/unit/sectionState.test.js`).
6. Boot screen: `setBootStage` writes the stage text and a determinate width, the slow hint appears
   after 8 s, dismiss removes the overlay, everything is a no-op without the element, and
   `bootstrapShell` reports the stages in order (`tests/unit/bootScreen.test.js`,
   `tests/unit/nativeSession.test.js`).
7. Playwright (`tests/browser/optimistic-navigation.spec.js`, phone, and tablet 1024x1366 with
   touch): with `getArtist` and `getSpotifyTracks` held back by `page.route`, clicking an artist
   link shows the artist's name as a heading within 100 ms of the click, while the requests are
   still pending.
8. Tag lists: skeleton before the first answer, no previous rows after navigating (also across
   kinds), a late answer dropped, error and retry, a revisit from the cache without a request, a
   background refresh after `freshMs`, one request for a press and the page together, none for the
   favourite toggle, stale rows dimmed on a filter change (`tests/unit/tagListLoading.test.js`).
9. Search page: a skeleton per section and no "No results" until all three answered, sections fill
   independently, no previous query's rows, a section error with retry, a revisit from the cache
   (`tests/unit/tagListLoading.test.js`). Dropdown: "searching" from the first keystroke, stale
   results dimmed, "No results" only after the answer, retry after a failure
   (`tests/unit/searchBar.test.js`). History, Starred, Memories and the "more" modal: skeletons
   and error/retry (`tests/unit/loadingSections.test.js`).
10. Playwright (`tests/browser/list-loading-states.spec.js`, phone, and tablet 1024x1366 with
   touch): with the second genre's tracks held back, its page shows its name, skeleton rows and
   none of the first genre's rows; back to the first genre it renders from the cache. With the
   search requests held back, the search page shows skeleton sections and "No results" only after
   they are released.

8. Feeds (`tests/unit/feeds.test.js`, `tests/unit/feedView.test.js`): every chunk is requested
   before the first answers and the result keeps MuMa's order; the header comes before any song;
   the page shows the card's title and skeleton rows before MuMa answers, draws a chunk landing
   out of order only once the one before it is in, retries only a failed chunk, retries a failed
   feed, starts a pending play once whole, and answers a revisit from the cache. The existing
   continuation and unresolved tests still pass.
9. Song versions (`tests/unit/songView.test.js`, `tests/unit/versions.test.js`): the seed header
   and cover before any answer, a skeleton header without a seed, the first page shown while the
   second is pending, the seed kept over a non-canonical first version, retry after a failure,
   the cached revisit, and `onPage` after every page.
10. Track details (`tests/unit/trackDetailsSheet.test.js`): tag skeleton rows while MuMa is asked,
    and the retry pill re-fetches.
11. Mix card (`tests/unit/dailyMixCard.test.js`): the coarse-pointer, hover and focus classes, the
    seed left on open, and play from the cache.
12. Playwright (`tests/browser/progressive-feeds.spec.js`, phone and tablet 1024x1366 with touch):
    the mix card's play button has opacity 1 and is at least 48px wide without hover (and opacity 0
    until hover with a mouse); tapping a card shows the mix's heading and skeleton rows while the
    feed is held back, then the rows; `/song/<id>` shows its header skeleton while the versions are
    held back, then both pages.

13. Code splitting (issue #114): the registry fetches once, forgets a failure and peeks only a
    loaded chunk; every management tab except Scrobble has a chunk; every loader resolves to a
    component; `chunksForState` maps views to chunks; `preloadState` never rejects; the idle
    preload takes one chunk per slot (`tests/unit/lazyViews.test.js`). `LazyView` shows skeleton
    rows then the view, renders a loaded chunk at once, shows nothing for `fallback="none"`,
    retries a failure and follows new props without reloading (same file). `initialState`, the
    once-per-window chunk reload and the admin preload (`tests/unit/bootChunks.test.js`).
    `requiredLocales` and loading (`tests/unit/i18n.test.js`).
14. Playwright (`tests/browser/lazy-views.spec.js`, desktop and phone against the built bundle):
    `/management/config` by URL renders its heading with the `Management` and `ConfigTab` chunks
    fetched and not `UsersTab`; the statistics page reached from the desktop sidebar fetches
    `ListeningStatsView` only on the click and renders; the first screen fetches no management,
    settings or statistics chunk.
15. Contract (`tests/contracts/test_spotify_static_cache.py`, against the test stack's LMS):
    `index.html` and an SPA route are `no-cache`, the entry chunk under `/assets/` is
    `public, max-age=31536000, immutable`, `version.json` is `no-cache`.
16. `frontend:bundle` and `mobile:smoke` pass: the APK still launches and reaches its server URL.
17. One-tap pages (issue #118): `chunksForState` maps the artist, album, preset, playlist and feed
    views to their page chunk and the list pages to `filterBar`, `collectionGrid` or
    `collectionBar`; the artist and album pages lead `likelyNextChunks`; `LazyView` renders its
    `placeholder` snippet while loading (`tests/unit/lazyViews.test.js`). A press starts the
    registered page chunk and swallows its failure; `artist`, `album` and `feed` are registered
    (`tests/unit/entitySeeds.test.js`). `EntityPageShell` draws the seeded name as `h1` and the
    seeded picture, and without a seed only skeletons (`tests/unit/entityPageShell.test.js`).
    `lazyComponent` is null until loaded, fetches once, is there at once when preloaded, and
    retries after a failure (`tests/unit/lazyComponent.test.js`).
18. Locale preload (`tests/unit/localePreload.test.js`): the plan equals `requiredLocales` for every
    supported locale; the stored choice wins, then the browser language, then English; a corrupted
    or unsupported stored value is ignored; it never throws; it runs from its own source text.
19. Playwright: with the `ArtistView` chunk held back as well as the artist's requests, a tap still
    shows the seeded heading in `EntityPageShell` within the loose guard, and the page replaces it
    once released (`tests/browser/optimistic-navigation.spec.js`). The first screen fetches none of
    the one-tap chunks while idle preload is held; `index.html` carries a `modulepreload` for the
    `nl` file and not `en`, and `nl` is fetched once (`tests/browser/lazy-views.spec.js`).

## Related Docs

- `docs/styleguide.md`: Loading States (boot screen, skeletons, optimistic page shell, throbber).
- `docs/designs/feeds/home-load.md`: the MuMa gate lanes.
- Memories: "LMS thread pool starvation", "/muma proxy is a serial queue".
