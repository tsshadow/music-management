# Perceived performance — Technical Design

Implements [functional.md](functional.md). Issue #107.

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
  `setBootStage`, then `starting`, then mounts and dismisses.

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

## Risks

- **Wrong seed.** Seeds are only ever replaced by server data, never merged into it. `ArtistList`
  links carry the name shown for that id. For a legacy comma-joined `artist` string, only the first
  name carries the id, as before.
- **Stale data.** At most 5 minutes old, and always refreshed after 60 s. Stars are kept correct by
  `update`. Other edits (the artist edit page) call `invalidate`.
- **Load on LMS.** Prefetch is one request per press, deduplicated with the page load. Starting the
  artist's requests together raises the peak from one to three `/rest` calls on the same server,
  which is what the page already did one round trip later. There is no hover or viewport prefetch.
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

## Related Docs

- `docs/styleguide.md`: Loading States (boot screen, skeletons, optimistic page shell, throbber).
- `docs/designs/feeds/home-load.md`: the MuMa gate lanes.
- Memories: "LMS thread pool starvation", "/muma proxy is a serial queue".
