# One entry per song in feeds and lists — Technical Design

Implements [functional.md](functional.md). Bug report 096.

## Data Model

No schema change in music-manager. Reads `library_tracks.work_id` and
`library_works.canonical_track_id` (the pin already folded in by `song_version_worker.py`).

LMS: no migration. A startup index `track_work_id_idx ON track(work_id)` (`Session.cpp`, created
with the other `CREATE INDEX IF NOT EXISTS`) backs the per-row work lookups below.

## Feeds (music-manager)

- `candidates_query` and the new `canonical_rows_query` share one SELECT (`_candidate_select`),
  which adds `t.work_id`, `w.canonical_track_id` and makes two columns song-level:
  - `heard`: a listen of this track, or of any track with the same `work_id`.
  - `rating`: the canonical's own rating, else `MAX` over the work's versions, else the track's own.
  The `unheard` and `loved` pools use the same two expressions.
- `build._collapse_to_songs` runs inside `_load_candidates`, so before bucketing, ranking and the
  artist cap, for every policy: group by `work_id` (ungrouped tracks pass through); pick the
  canonical if it is a candidate, else fetch it with `canonical_rows_query` (no policy filters, only
  "has a file"), else keep the lowest-id qualifying version; set `release_date` to the newest of the
  qualifying versions' dates. The hardness backfill dedupes on `song_key` rather than on track id.
- See [feeds technical design](../feeds/technical.md), step 4b.

## API Contract

No request or response shape changes; which rows come back changes.

| Endpoint | Change |
|---|---|
| `GET /api/feeds/{slug}` | One track per song, the canonical's path and id |
| Subsonic `search2`/`search3` | With a non-empty query, `canonicalOnly` (ungrouped tracks stay). Empty query unchanged (full-library sync cursor) |
| Subsonic `getStarred`/`getStarred2` | Each favourite mapped to its canonical, deduplicated, in rated-date order; listed only if the song's rolled-up rating is a favourite |
| Subsonic `getRandomSongs`, `getSongsByGenre`, `getSongsByFilter` | `canonicalOnly` |
| Subsonic song node (`userRating`, `starred`) | For the canonical of a work: the song's rating (own, else highest of the versions) |
| Subsonic `unstar`, `setRating` rating=0 on a canonical | Clears the rating on every version of the work for this user |
| `getSpotifyTracks` from the phone home shelves | Now sent with `deduplicate=true` |
| Albums, playlists, `workId=` | Unchanged |

Not breaking for any client: every field keeps its meaning; lists are shorter.

## Cross-App Impact

- music-manager: feeds.
- LMS: `Track::find` (`createQuery`) now honours `canonicalOnly` and `workId`, as `find_advanced`
  does; `Track::findCanonicalVersion`; `RatedTrack::findHighestInWork`;
  `IFeedbackService::getSongRating` (one implementation); the endpoints above.
- frontend: `PhoneHome.svelte` sends `deduplicate=true`. The client-side `deduplicateTracks` in
  search stays as a harmless second pass.
- MuMa Mobile: nothing to change; it speaks Subsonic to LMS and plays the feed's paths.

## Technical Acceptance Criteria

1. Two versions of one work among the candidates yield one feed entry, the canonical
   (`CollapseToSongsTest`).
2. A canonical outside the candidate set is fetched and emitted, dated by the qualifying version
   (`CollapseToSongsTest`, `test_feed_song_collapse.py` on MariaDB).
3. A listen of any version makes the song heard; the `unheard` pool drops it (MariaDB test).
4. The phone home shelves request `deduplicate=true` (`phoneHome.test.js`).
5. `Track::find` with `canonicalOnly` in the shape of each endpoint returns the canonical and
   ungrouped tracks only; `findCanonicalVersion` maps a version to its canonical and falls back to
   itself (`database/test/SongVersions.cpp`).
6. `getSongRating` returns the canonical's own rating, else the highest version's, and a version's
   own for a non-canonical (`FeedbackService` GTest).

## Related Docs

- [Song versions and canonical design](../../superpowers/specs/2026-08-23-song-versions-and-canonical-design.md)
- [Feeds technical design](../feeds/technical.md)
- [Bug report 096](../../bug-reports/096-feeds-collapse-per-song.md)
