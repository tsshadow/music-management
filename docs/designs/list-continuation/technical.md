# List continuation — Technical Design

Implements [`functional.md`](functional.md). Frontend only (`services/frontend`); the Android shell
follows the `playlist` store as it already does for the feed top-up, so the app gets the behaviour
without native changes. Issue #100.

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

None beyond the frontend. The Android shell's native queue follows `playlist`, so appended pages
reach it the way the feed pages do. Android Auto's own browse lists (`MediaLibraryBrowser.kt`: the
Songs tab sorts, the `TagQuery` genre/label/festival lists, preset tiles) are fixed-size `getSongs`
calls; giving them the same top-up is follow-up work (`FeedQueueContinuation.kt` from !1056 is the
model), tracked in issue #103.

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

## Related Docs

- [`docs/designs/feed-length/technical.md`](../feed-length/technical.md) — the feed paging this generalises.
- [`docs/bug-reports/122-feed-load-more-not-visible.md`](../../bug-reports/122-feed-load-more-not-visible.md).
- [`docs/styleguide.md`](../../styleguide.md), "Load more".
