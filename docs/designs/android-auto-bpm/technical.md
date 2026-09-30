# Browse by BPM in Android Auto — Technical Design

Implements [functional.md](functional.md). App-only: no server change.

## Data Model

None. The app caches in memory only.

## API Contract

Consumes two existing endpoints unchanged ([bpm-browse technical design](../bpm-browse/technical.md)):

| Endpoint | Request (from the car) | Used for |
|---|---|---|
| `GET /api/library/bpm/histogram` | `bpm_from=100&bpm_to=500` | Counts: bins (one per whole BPM) summed per row, with `default_tolerance`. |
| `GET /api/library/bpm/tracks` | `bpm=<row>&limit=100&offset=<n>`; for 210+: `bpm_from=<210 - tolerance>&limit=100&offset=<n>` | A row's pages. `tol` is not sent, so the server's `bpm_browse_tolerance` applies; `min_confidence` is not sent (all tracks). |

Order is the server's: with `bpm`, nearest first, then more trusted, then id; for the range row, by
tempo. Paths are resolved with LMS `getSongsByPath` (at most 100 per call, `FeedRepository.
SONGS_BY_PATH_LIMIT`), order kept — the feeds' pattern.

The counts are approximate at the edges: a histogram bin holds every tempo that rounds to it, a
list asks for an exact window. One request for ten rows was preferred over ten exact `limit=1`
requests while the car waits.

## App structure

- `service/BpmRepository.kt`: `BpmBucket`/`BpmBuckets` (the ten rows, key = media-id part `150`,
  `210+`), `BpmBuckets.counts(bins, tolerance)`, and `BpmRepository` (`counts()`, `firstPage()`,
  `pageAfter()`). Cached per server for 10 minutes (the server's index refresh); failures and
  partly resolved pages are never cached. Koin single in `MusicServiceModule`, reached through
  `MediaLibraryDataProvider.bpm`.
- `androidauto/BpmBrowseArea.kt`: `MEDIA_BPM_LIST` (the rows; count as subtitle via `plurals
  auto.bpm_tracks`) and `MEDIA_BPM_TRACKS|<key>` (play-all + tracks as `MEDIA_BPM_ITEM|<key>|<id>`).
- `androidauto/BpmPlayback.kt`: the playback side (page, legacy one-track path, play-all with
  continuation), held by `MediaLibraryPlaybackController.bpm` — a separate class because the
  controller is at detekt's function limit.
- `ListQueueContinuation.kt`: `BpmListSource`, like `FeedListSource` (`next_offset`).
- `MediaLibrarySessionCallback.TRACK_IN_LIST_IDS` gets `MEDIA_BPM_ITEM`, so a tapped track plays
  its row (tap-plays-list); `queueForPlayAll` handles `MEDIA_BPM_TRACKS`. The key travels in the
  media id because Android Auto drops a command's extras on a car tap.

## Cross-App Impact

MuMa Mobile only. No API change; nothing else changes.

## Technical Acceptance Criteria

1. `BpmBuckets.ALL` is the ten rows; `counts()` sums bins within the tolerance and the whole tail
   for 210+ (`BpmRepositoryTest`).
2. A row asks `bpm=<row>` with the server's tolerance and `limit=100`; 210+ asks `bpm_from` =
   210 − the histogram's tolerance; MuMa's order survives resolution; `next_offset` is carried
   (`BpmRepositoryTest`).
3. A page is cached 10 minutes per server; a failure or a partial resolve is not; a failed later
   page is null, not an end (`BpmRepositoryTest`).
4. The Songs tab has the BPM row, Sets does not, the root keeps four tabs; the folder lists ten
   browsable rows titled "150 BPM"/"210+ BPM" with counts, without counts when MuMa is down; a row
   lists play-all plus tracks; an unknown key is empty (`MediaLibraryBpmTest`).
5. Play-all and a tapped track produce a queue from the right index with a `BpmListSource`
   continuation that pages by `next_offset`; a short row does not continue; a track no longer in
   the row falls back (`MediaLibraryBpmTest`).

## Related Docs

- [docs/designs/android-auto-browse/functional.md](../android-auto-browse/functional.md)
- [docs/designs/bpm-browse/technical.md](../bpm-browse/technical.md)
- [docs/designs/feed-length/technical.md](../feed-length/technical.md) — the `next_offset` paging.
