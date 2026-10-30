# Oude hitjes — Technical Design

Implements [functional.md](functional.md). Code: `services/music_manager/feeds/old_hits.py` (rules,
pure), `feeds/old_hits_queries.py` (SQL), `feeds/old_hits_build.py` (the build),
`services/music_manager/popular_tracks/` (external top tracks), wired in `routers/feeds.py`.

## Data Model

Two new tables (db_init, `migrate_v49_artist_popular_tracks.sql`, `tests/integration/test_schema.py`):

| Table | Key | Columns | Written by |
|---|---|---|---|
| `artist_popularity_fetches` | `(artist_key, source)` | `artist_name`, `external_artist_id` (NULL = not found), `status` `ok`/`not_found`/`error`, `track_count`, `matched_count`, `fetched_at` | popular-tracks loop |
| `artist_popular_tracks` | `id`; unique `(artist_key, source, external_track_id)` | `title`, `normalized_title`, `popularity` (Deezer `rank`, Last.fm listeners), `position` (1 = top), `matched_track_uid`, `matched_work_id`, `fetched_at` | popular-tracks loop |

- `artist_key` is `library_artists.normalized_name` (`scrobble_matching.normalize` of the name), not
  an artist id: a library rebuild renumbers artists and tracks, and the crawl must survive it.
- `matched_track_uid` is the join key the feed reads (`track_uid` survives a rebuild). The work is
  resolved at read time through `library_tracks.work_id`, so a regrouped song is read as it is now;
  `matched_work_id` is only what the matcher saw.
- Nothing else changes. Ratings, listens, works and exclusions are read as they are.

### Popularity crawl (`popular_tracks/worker.py`, thread `popular-tracks`)

- Hourly. Per source, the artists that are *due*: a primary artist of a track any listener rated
  4-5, or of at least `popular_tracks_min_listens` (5) listens over all listeners, whose list is
  missing, older than `popular_tracks_refresh_days` (7), or failed more than a day ago. Oldest
  first, at most `popular_tracks_max_artists` (150) per source per round, a round stops after 30
  minutes. Production has 943 such artists: about a week-end's worth of rounds to crawl, then
  ~135 artists a day to keep fresh.
- Deezer (no key): `search/artist?q=<name>&limit=5`, the first result whose name normalizes to the
  same key (a collaboration or namesake listed first is skipped), then `artist/<id>/top?limit=50`,
  using `title_short` (the title without Deezer's "(Original Mix)" suffix).
- Last.fm, only when `lastfm_api_key` (existing secret, group "3rd Party APIs") is set:
  `artist.getTopTracks&autocorrect=1&limit=50`. Error 6 is "not found", not a failure.
- Politeness: at most four requests a second per source; HTTP 429, Deezer error code 4 (quota) and
  Last.fm error 29 back off 5, 10, 20 s, then the source is dropped for the rest of the round and
  resumed next round. Other failures mark the artist `error` (retried after a day) and keep its
  previous list.
- Only artist names are sent. Tests replay recorded responses
  (`services/music_manager/tests/fixtures/popular_tracks/`); none touches the network.
- Matching (`popular_tracks/matcher.py`): against the library tracks credited to that artist
  (primary, or `library_track_artists` primary/featuring), by three keys tried strict to loose:
  `normalize(title)`, `normalize(base_title(title))` (the scrobble matcher's, the same values as
  `normalized_title` / `normalized_base_title`), and the title with every bracket group removed
  ("Scrap Attack (Defqon.1 2009 anthem)" → "scrap attack"). Restricting to the artist's own tracks
  means a loose key can at worst pick another version of the same song, which the feed collapses
  anyway. The work's canonical is stored when it matched, else the lowest track id.

## Algorithm (`build_old_hits`)

1. **Touched songs.** The listener's ratings (`rating_tracks` → `library_tracks` by `track_uid`)
   and listens (`scrobble_listens`, grouped per song), sets/live sets/podcasts excluded
   (`form` other than `track`). A song is its work, or the track when ungrouped (the same key as
   `build.song_key`). Rating per song follows `_SONG_RATING`: the canonical's own rating, else the
   highest. Listens: count and latest over every version.
2. **Affinity** per primary artist: 5★ +3, 4★ +2, 3★ +0.5, 2★ −1, 1★ −2 per song, plus
   `0.5·ln(1+plays)` per played song; only positive totals count. For the 300 most liked artists:
   the stored top-list matches (best position per song, any source) and the works with at least
   `old_hits_min_versions` (4) library versions.
3. **Age.** Cutoff = today − `old_hits_min_age_years` (3) calendar years. A song is old when:
   the earliest `library_tracks.release_date` over its versions is before the cutoff; else, the
   earliest analyzer `release_year` (> 1900) over its versions is before the cutoff's year; else
   its primary artist has at least 3 dated tracks and at least 80% of them are old. The file's own
   age is **not** used: every `library_tracks.created_at` dates from the May 2026 rebuild and the
   tagger rewrites files (mtime). Measured for the user's 4-5★ songs: 329 old by date, 157 by year, 92
   undated (half of those qualify through the artist).
4. **Excluded everywhere** ("resting"): not old, rated 1-2, or any version played within
   `old_hits_rest_days` (90).
5. **Tiers**, each ordered by `scoring.daily_sample_key(username, day, song, weight)` (the daily
   mixes' stable weighted draw):
   - *favourites*: rated 4-5; weight `1 + (days unheard / 30)²`, never heard = 3 years.
   - *worn*: ≥ `old_hits_min_plays` (3) plays, last one ≥ `old_hits_stale_days` (180) ago;
     weight `plays × days unheard / 180`.
   - *hits*: a liked artist, unrated or rated ≥ 3, and a hit strength > 0: `10 / (9 + position)`
     for a top-list match, `0.8 × min(1, versions / (2 × min_versions))` for a many-version work;
     weight = strength × affinity / top affinity.
6. **Display rows** (`queries.canonical_rows_query`, the feeds' own row shape) for the first
   `max(3 × size, 300)` songs of each tier: the canonical version when it has a file, else the
   version that qualified. Dropped: no file, duration outside 0-600 s, or an artist/label/genre in
   the listener's `feeds_profile_exclusions`.
7. **Fill** (`fill_tiers`): quotas from `old_hits_tier_shares` (40,30,30) by largest remainder;
   each tier takes its quota plus what the previous tiers left; what the last tier leaves goes
   round once more from the first. One place per song, at most `old_hits_max_per_artist` (3) per
   artist. **Interleave**: a weighted round robin, so the tiers take turns in proportion.
8. Each track carries `bucket` `old-hits:<tier>` and `reason` `favourite:<stars>`,
   `worn:<plays>`, `hit:<source>:<position>` or `hit:versions:<n>`. States: `ok`, `no_matches`
   (nothing qualified), `not_enough_data` (no ratings and no listens).

Every query starts from the listener's own rows or the bounded popular table, never a scan of the
library; id lists are chunked at 500.

## API Contract

No new endpoint. The existing feed endpoints gain one slug:

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/feeds` | unchanged | the list gains `{slug: 'old-hits', title: 'Oude hitjes', subtitle: 'Oude favorieten die je minder draait', size, window_days: null}` | unchanged |
| `GET /api/feeds/old-hits` | `offset`, `limit`, `username` (system key) as for every feed | the feed body of every feed (`state`, `tracks`, `funnel`, `title`, `subtitle`, `next_offset`, ...); `hardness_*`, `relaxed_to`, `filled_from_unknown` are null | 400 system key without `username`, 500 no database |

Snapshots: stored per day like the daily mixes (`feeds_snapshot`, `is_fresh` treats it as a
day-stable slug); `params_key` for `old-hits` additionally covers the `old_hits_*` settings, so a
change there rebuilds it on the next read without moving any other feed's key. The `feeds-refresh`
thread keeps it warm through `SNAPSHOT_SLUGS`. Not a breaking change: a client that ignores the new
slug is unaffected.

Settings (group "Feeds"): `old_hits_min_age_years` 3, `old_hits_rest_days` 90,
`old_hits_stale_days` 180, `old_hits_min_plays` 3, `old_hits_tier_shares` "40,30,30",
`old_hits_max_per_artist` 3, `old_hits_min_versions` 4, `popular_tracks_enabled` on,
`popular_tracks_refresh_days` 7, `popular_tracks_max_artists` 150, `popular_tracks_min_listens` 5;
plus the existing `lastfm_api_key`. Garbage falls back to the default per field.

## Cross-App Impact

- **music-manager**: the feed, the crawl, the router wiring, the thread (`/health` lists
  `popular-tracks`).
- **frontend**: `OLD_HITS` and `SHELF_FEEDS` in `feeds.js`; the shelf and the phone's "Daily
  mixes" page draw it after the five mixes (name-derived colour from the existing palette, no new
  style); route `/old-hits` and the feed page chunk. The phone Home is this frontend inside
  Capacitor.
- **muma-mobile (Android Auto)**: `FeedRepository.OLD_HITS`, listed last in the "Daily mixes"
  folder; playback of `MEDIA_FEED_ID|old-hits` was already generic.
- **LMS**: none.

## Technical Acceptance Criteria

1. `tests/integration/test_router_sql.py::OldHitsPipelineTest` runs every old-hits query and the
   popular-tracks store against MariaDB and gets one track per tier.
2. Unit tests pin: age rules including the leap day and the artist fallback; each tier's
   inclusion and exclusion; fill proportions, hand-over in both directions, dedupe and the
   artist cap; interleave; daily stability; the router dispatch, listing and snapshot key; the
   Deezer/Last.fm clients against recorded responses including quota back-off; the matcher's
   three keys; a crawl round with found, not-found, failed and throttled artists.
3. `GET /api/feeds/old-hits` never calls the daily-mix ranker (`build_feed`).
4. With `popular_tracks_enabled` off, no request leaves the process; without `lastfm_api_key`,
   only Deezer is asked.

## Related Docs

- [docs/designs/feeds/technical.md](../feeds/technical.md) — the feeds package this reuses (song
  collapse, snapshots, exclusions, daily-stable draw).
- [docs/designs/song-versions/](../song-versions/) — works and canonical versions.
