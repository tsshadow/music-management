# List continuation — Technical Design

Implements [`functional.md`](functional.md). Issue #100 is frontend only (`services/frontend`); the
Android shell follows the `playlist` store as it already does for the feed top-up, so the app gets
the behaviour without native changes. Issue #103 brings the same rule to Android Auto's native
lists ([Android Auto](#android-auto)) and makes LMS `getSongs` honour `seed`.

## Data Model

No database or server change. The client-side model is one object, the **continuation**, owned by
the source that built the list:

```js
/** @typedef {{
 *   kind: string,                // 'songs' | 'feed' | 'preset' | 'history' | 'artist' | 'local' | 'mix'
 *   cursor: unknown,             // where the list continues; null = exhausted
 *   fetchNext: (cursor, {queue}) => Promise<{tracks: object[], cursor: unknown, failed?: boolean}>,
 *   exhausted?: boolean,         // set by the queue once a page answered cursor: null
 * }} Continuation */
```

`fetchNext` never throws: a failure comes back as `{failed: true}` with the cursor unchanged. It
gets the current queue so a source that deduplicates song versions (`getSpotifyTracks` with the
"deduplicate" setting) can do that against what is already queued.

Factories, one per kind of source:

| Factory | Module | Source | Used by |
|---|---|---|---|
| `feedContinuation(slug, nextOffset)` | `feedQueue.js` | `GET /api/feeds/{slug}?offset=` (`loadFeedPage`) | `FeedView`, `DailyMixCard` |
| `spotifyTracksContinuation(params, offset, opts)` | `trackPages.js` | `getSpotifyTracks` (the fork's paged track list) | songs/sets lists and every sort, genre/label/podcast/festival/year/lineup lists, search, `ArtistView` |
| `getSongsContinuation(build, offset, opts)` | `trackPages.js` | `getSongs` with `offset`/`count` | `PresetView` (same seed), car-mode mix (same seed) |
| `historyContinuation(offset, opts)` | `trackPages.js` | `getSpotifyHistory` | `History` |
| `arrayContinuation(rest, opts)` | `listContinuation.js` | the unshown rest of a list already in memory | `MemoriesYearView` |

Each returns `null` when there is nothing more, so `startQueue` never records a continuation that is
exhausted from the start (no "end of list" line under a list that fit on one page).

The queue's continuation lives in the `queueContinuation` store (`store.js`), which replaces
`feedContinuation`. It is not persisted and is cleared on account switch, exactly like its
predecessor.

## Components

- **`listContinuation.js`** — `extendQueue({force})`, the generalised `extendFeedQueue`:
  - returns without a request unless a continuation with a cursor is set, no top-up is in flight,
    and (unless `force`) the current track is within `EXTEND_WHEN_LEFT` (3) of the end;
  - asks `fetchNext(cursor, {queue})`; appends only tracks whose id is neither in the queue nor
    earlier in the same page, in page order;
  - a page of nothing but repeats is followed by the next page straight away, at most
    `MAX_PAGES_PER_TOP_UP` (3) per top-up — the Android Auto continuation's rule;
  - a failed page keeps the continuation; a page with `cursor: null` marks it `exhausted`;
  - a queue replaced while the page was loading is left alone (identity check on the store value).
- **`trackPages.js`** — `fetchSpotifyTracksPage(params, offset, {pageSize, seen, signal})`, the
  page-filling loop `Dashboard.loadAllTracks` and `ArtistView.loadAllTracks` each had a copy of,
  now shared by both pages and by `spotifyTracksContinuation`. It stops on a page that neither
  returns tracks nor advances the offset, so a server that says `moreResults` forever cannot spin it.
- **`queue.js` `startQueue(tracks, {continuation})`** — records the continuation (or clears it).
- **`TrackList.svelte`** — its `continuation` prop is now any continuation; a row tap passes it to
  `startQueue`, as the feed one already did.
- **`QueueLoadMore.svelte`** (was `QueueFeedLoadMore.svelte`) — under the queue in the phone/tablet
  sheet and the desktop panel: the load-more pill while `queueContinuation` has a cursor, the muted
  "Einde van de lijst" line once it is `exhausted`, nothing otherwise.
- **`ListEnd.svelte`** — the one pill/end-line pair both the queue and the pages render, so the
  pages cannot drift from the queue (styleguide "Load more").
- **`Player.svelte`** — its near-end `$effect` calls `extendQueue()` instead of `extendFeedQueue()`.
- **Shuffle buttons** (artist, album) keep their plain queue: a shuffled first page followed by
  pages in server order would not be a shuffle, so they pass no continuation.

Order is stable because pages are appended in the order the server hands them out, and the
continuation is a snapshot of the list's query at the moment playback started: changing a filter on
the page afterwards does not change what the playing queue continues with.

Radio and news: neither starts a queue through `startQueue` with a continuation, and the near-end
check looks at the current track's index in `playlist`, which a radio stream or a bulletin is not
in, so neither triggers a top-up.

## API Contract

No endpoint is added or changed. Existing, already-paged calls are used:

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `getSpotifyTracks` (LMS fork) | the list's own params + `offset`, `count` | `tracks.track[]`, `tracks.moreResults`, `tracks.nextOffset` | failed envelope / network: page reported `failed`, cursor kept |
| `getSongs` (LMS fork) | preset/mix params + `offset`, `count`, `seed` | `songs.song[]`; fewer than `count` = last page | as above |
| `getSpotifyHistory` (LMS fork) | `offset`, `count` | `history.entry[]`, `history.moreResults` | as above |
| `GET /api/feeds/{slug}` (MuMa) | `offset` | `tracks`, `next_offset` | unchanged from feed-length |

## Cross-App Impact

The Android shell's native queue follows `playlist`, so appended pages reach it the way the feed
pages do. Android Auto does not run the web bundle; its own lists got the same top-up natively in
issue #103 — see [Android Auto](#android-auto) below.

The LMS fork's `getSongs` reads `seed` since issue #103 (`handleGetSongs`, as `getSongsByFilter`
and `getSpotifyTracks` already did). Before that the web's `getSongsContinuation` sent the preset's
seed and the server ignored it: every page of a shuffled preset was a new `RANDOM()` draw, which the
queue's dedupe hid as a shorter, overlapping list. Additive: a client that sends no seed gets the
unseeded shuffle it always got.

## Android Auto

Issue #103. `FeedQueueContinuation` (!1056, bug 112) became `ListQueueContinuation`
(`service/androidauto/ListQueueContinuation.kt`): the same queue rule with a pluggable
`Source` (`label`, `pageAt(offset): Page(tracks, nextOffset)?`, blocking, run on IO). Every guarantee
of the feed version is kept unchanged — near-end trigger (`EXTEND_WHEN_LEFT` = 3, play order),
append only ids neither in the list so far nor in the queue, a repeats-only page followed by the
next (at most `MAX_PAGES_PER_TOP_UP` = 3), single flight, a failed page keeps the offset, a page
that lands after `stop()`/a new `start()` is dropped (generation counter), main-thread append on the
session's own player (no controller grant in the way; `COMMAND_CHANGE_MEDIA_ITEMS` checked), radio
and news never extended — see [`feed-length/technical.md`](../feed-length/technical.md#continuation-in-android-auto).

| Source | Class | Asks | End of list |
|---|---|---|---|
| Feed | `FeedListSource(slug)` | `FeedRepository.pageAfter(slug, offset)` | `next_offset: null` |
| `getSongs` list | `SongsListSource(label, pageSize, load)` | the first page's `getSongs` again with `offset`, `count` = `DISPLAY_LIMIT` (100) | a page shorter than asked |

The `getSongs` sources are built where the first page is fetched, from the query that page used,
never re-derived from the media id — the car's ids carry no seed:

- `MediaLibraryDataProvider.loadList(query, page, pageSize)` (behind `tracksFor`): tag folders
  (genre, label, festival, podcast, year, lineup, and the Soort/`FORM` folders of !1064), their play
  rows, the tab Random row, preset folders and preset play rows. A random query (`BrowseQuery.isRandom`)
  is given a seed (`BrowseQuery.seeded()`, 0–999 999 like the web) *before* the first page, and the
  seed travels in the query to every later page (`getSongs … &seed=`). A preset continues past its
  saved size, as on the web.
- `MediaLibraryDataProvider.loadLengthList(length, sort, count)`: the Songs/Sets tab sorts
  ("Recent toegevoegd", "Recent uitgebracht"), which have always asked without a rating range —
  the continuation asks the same way, so the list cannot change underneath the car.

Each load returns a `LoadedList(tracks, continuation)` and remembers it next to the random-songs
cache (`rememberList`); assigning `randomSongsCache` directly clears the continuation, so a cached
list never carries the wrong list's source. A list that fit in its first page has no continuation.

Arming, in `MediaLibrarySessionCallback`, exactly where the feed was armed:

- **Row tap** (`onSetMediaItems` → `queueFromTap` → `queueForTap`): `MEDIA_SONG_RANDOM_ITEM` rows
  (tab sort lists, tag folders, preset folders) return `CarQueue(tracks, index, continuation)`
  with the continuation of the cached list; a feed row returns its `FeedListSource`.
- **Play rows** (`onAddMediaItems` → `queueForPlayAll`): `MEDIA_FEED_ID`, `MEDIA_TAG_PLAY`,
  `MEDIA_PRESET_PLAY` and a tab sort list's "Alles afspelen" (`MEDIA_SONG_RANDOM_ID`). Any other id,
  and an empty list, takes the legacy path as before.
- Every other queue replacement calls `stop()`, as before.

Browse lists stay bounded (`DISPLAY_LIMIT` per tag folder page, `maxSongs` for a tab sort, the car's
own item limits); the continuation only grows the playing queue. Filter values are the ones the
first page sent — a form only ever from `TrackForm.SET_FORMS` via `TrackForm.known` — so a
continuation page cannot hit the "unknown value fails the whole request" trap of `getSongs`.

Not continued: albums, playlists, starred songs, shares, bookmarks and search results (complete
lists, or not paged), and voice results (`tracksFromVoice`, one answer by design). A queue restored
after the service was killed plays but does not continue — the state is in memory, like the feed's.

## Technical Acceptance Criteria

1. `extendQueue` appends only unseen ids, in order; does nothing far from the end unless forced;
   keeps the continuation after a failure; marks it exhausted on `cursor: null`; skips a
   repeats-only page; leaves a replaced queue alone; asks once for a burst of calls
   (`tests/unit/listContinuation.test.js`, `tests/unit/feedQueue.test.js`).
2. `fetchSpotifyTracksPage` fills a page across calls, deduplicates versions against `seen`, and
   stops on a page that makes no progress (`tests/unit/trackPages.test.js`).
3. The songs list sorted by "Recent uitgebracht", a filtered song list and a preset each hand their
   continuation to the queue on a row tap and on the play button, and show the page pill and the end
   line (`tests/unit/listContinuationViews.test.js`).
4. `QueueLoadMore` renders the pill, the end line, or nothing (`tests/unit/queueLoadMore.test.js`).
5. Playwright: a queue started from "Nummers" ends in the pill at phone and tablet size, a tap grows
   it, and the last page leaves "Einde van de lijst" (`tests/browser/list-continuation.spec.js`).
6. Android Auto (issue #103): per source, the trigger distance, the append, the stop at the end,
   no duplicates, single flight and the replaced-queue discard (`ListQueueContinuationFeedTest`,
   `ListQueueContinuationSongsTest`); every car path that starts a queue from a tab sort, a tag
   folder (form included) or a preset carries a continuation that asks the same filters, sort and
   seed, and a random list's seed is the same on every page (`MediaLibraryListContinuationTest`,
   `BrowseQueryTest`, `MediaLibraryTapQueueTest`).
7. LMS: a seeded random `getSongs` answers one order, and paging past its end answers nothing
   (`tests/contracts/test_lms_subsonic_contract.py::test_get_songs_random_with_a_seed_is_one_shuffle`).

## Related Docs

- [`docs/designs/feed-length/technical.md`](../feed-length/technical.md) — the feed paging this generalises.
- [`docs/bug-reports/122-feed-load-more-not-visible.md`](../../bug-reports/122-feed-load-more-not-visible.md).
- [`docs/styleguide.md`](../../styleguide.md), "Load more".
