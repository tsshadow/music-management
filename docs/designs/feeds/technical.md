# Personalized Feeds (Release Radar & Daily Mix) — Technical Design

> Implements [`functional.md`](functional.md). V1 is **music-manager only**: the ranker, one endpoint
> and a dry-run command. No client work, no snapshot table, no background job — see "Deliberately
> not in V1" at the bottom for why each of those is absent.

## Data Model

Read-only against everything that already exists:

| Table | Used for |
|---|---|
| `scrobble_listens` | the listening history: `track_id`, `listened_at`, `username`, `match_method`, `played_secs` |
| `library_tracks` | `id`, `track_uid`, `title`, `duration_secs`, `primary_artist_id` |
| `library_artists` | the artist dimension |
| `library_track_labels` / `library_labels` | the label dimension, and the label's dominant genre |
| `library_track_genres` / `rules_genres` | the genre dimension; `state <> 'black'` only |
| `rules_subgenre_hierarchy` | `(subgenre, genre)`, used to keep only the deepest genre per track |
| `library_track_audio_features` | `release_date` (partial string), joined on `internal_track_id` |
| `library_track_channels` / `channels` | the SoundCloud demotion |
| `rating_tracks` | `entity_type='track'`, `entity_id = library_tracks.track_uid`, `username` |
| `library_media_files` | a candidate must have a file |

One table is added:

```sql
CREATE TABLE IF NOT EXISTS feeds_profile_exclusions (
    username    VARCHAR(255) NOT NULL,
    entity_type ENUM('artist', 'label', 'genre') NOT NULL,
    entity_name VARCHAR(255) NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (username, entity_type, entity_name)
);
```

Created from `feeds.init_db(cursor)`, called from `main.py`'s startup block alongside the other
`init_db` calls.

### Invariants

- **Audio features are reduced to one row per track before use.** `internal_track_id` is *not*
  unique (`migrate_v10_audio_features_relink.sql` adds an ordinary index, not a unique one), so a
  join straight into the candidate query multiplies rows and therefore scores. The candidate query
  selects `MIN(af.release_date)` in a grouped subquery, and accepts the date only when every
  non-empty value for that track agrees; disagreeing rows count as unknown.
- **`af.track_id` is never joined against `t.track_uid`.** It holds a file-path hash.
- **A rating join carries all three key columns** (`entity_type`, `entity_id`, `username`); the
  unique key is on those three, and a looser join multiplies rows or reads someone else's rating.
- **Rating is never a filter**, only a score adjustment, except in the daily mix's `loved` pool where
  it is an explicit, documented membership rule.
- **`created_at` is never used as a release date**, in any fallback, anywhere.

## Module Layout

New package `services/music_manager/feeds/`. Every module below is pure Python over plain rows
except `queries.py` (builds SQL) and `build.py` (the only module that touches a connection), which
is what makes the whole ranker unit-testable without a database.

| File | Responsibility |
|---|---|
| `policy.py` | `FeedPolicy` dataclass and the two named policies |
| `hierarchy.py` | subgenre graph: ancestors, and reducing a track's tags to its deepest genres |
| `profile.py` | listen weighting, the three affinity tables, blending, and genre shares |
| `quota.py` | largest-remainder allocation and redistribution of unfilled shares |
| `buckets.py` | dominant genre per label/artist, and which share a candidate competes in |
| `scoring.py` | the per-candidate score `B` and the deterministic daily sample key |
| `queries.py` | every SQL string, as `(sql, params)` builders |
| `build.py` | orchestration: profile → candidates → buckets → quota → ordered feed |
| `routers/feeds.py` | HTTP surface and `init_db` |
| `scripts/feeds_dryrun.py` | prints the funnel and the top N with the reason per track |

### Key signatures

```python
# policy.py
@dataclass(frozen=True)
class FeedPolicy:
    slug: str
    size: int = 30
    profile_window_days: int = 90
    release_window_days: int | None = 7   # None means "no release-date requirement"
    max_track_seconds: int = 600
    pools: frozenset[str] = frozenset({'any'})   # subset of {'any', 'unheard', 'loved'}
    loved_min_rating: int = 4
    heard_rank_penalty: bool = True
    order: str = 'release'                        # 'release' | 'daily_sample'
    max_per_artist: int = 3
    label_bonus: float = 0.10
    soundcloud_penalty: float = 0.10

POLICIES: dict[str, FeedPolicy]   # 'release-radar', 'daily-mix'

# hierarchy.py
def ancestors(genre: str, parents: dict[str, set[str]], max_depth: int = 8) -> set[str]
def deepest(genres: set[str], parents: dict[str, set[str]]) -> set[str]

# profile.py
def listen_weight(age_days: float, match_method: str, played_secs: int | None,
                  half_life_days: float = 30.0) -> float
@dataclass
class TasteProfile:
    artists: dict[str, float]      # name -> affinity in [0, 1]
    labels: dict[str, float]
    genres: dict[str, float]
    distinct_tracks: int
    total_weight: float
    scope: str                     # 'user' | 'blended' | 'server' | 'configured' | 'empty'
def build_profile(rows: list[dict], parents: dict[str, set[str]],
                  exclusions: dict[str, set[str]], now: datetime) -> TasteProfile
def blend(user: TasteProfile, server: TasteProfile, ramp_tracks: int = 30) -> TasteProfile
def genre_shares(profile: TasteProfile, parents: dict[str, set[str]],
                 min_share: float = 0.03) -> dict[str, float]

# quota.py
def allocate(shares: dict[str, float], places: int) -> dict[str, int]
def redistribute(allocation: dict[str, int], available: dict[str, int]) -> dict[str, int]

# buckets.py
def dominant_genre(counts: dict[str, int], min_share: float = 0.6) -> str | None
def bucket_of(candidate: dict, shares: dict[str, float], label_genre: dict[str, str],
              artist_genre: dict[str, str], parents: dict[str, set[str]]) -> tuple[str, str]
    # returns (bucket, reason); reason is 'genre' | 'label:<name>' | 'artist:<name>' | 'tail'

# scoring.py
def taste_score(candidate: dict, profile: TasteProfile) -> float
def score(candidate: dict, profile: TasteProfile, policy: FeedPolicy) -> float
def daily_sample_key(username: str, feed_date: date, track_uid: str, weight: float) -> float

# build.py
@dataclass
class Feed:
    slug: str
    state: str          # 'ok' | 'no_matches' | 'not_enough_data'
    scope: str
    tracks: list[dict]
    funnel: dict[str, int]
def build_feed(conn, username: str, policy: FeedPolicy, now: datetime) -> Feed
```

### Algorithm, in the order `build_feed` runs it

1. **Profile.** Load the user's listens inside `profile_window_days`, one row per listen with its
   track's artist, labels and non-black genres. Reduce each track's genres with
   `hierarchy.deepest()`. Weight each listen by
   `0.5 ** (age_days / 30) × confidence × engagement`, where confidence is `1.0` for `exact` and
   `normalized`, `0.5` for `base_title` and `0.25` for `fuzzy`, and engagement is `1.0` when
   `played_secs IS NULL` and `min(1, played_secs / 120)` otherwise. Cap the summed weight per track
   at `3.0`. Split a track's weight equally across its memberships within each dimension, sum per
   entity, drop entities supported by fewer than two distinct tracks, and divide by that dimension's
   maximum so affinities land in `[0, 1]`. Drop excluded entities before normalising.
2. **Scope.** Fewer than 5 distinct tracks → the server profile (same computation, no `username`
   filter), scope `server`. Between 5 and 30 → `blend()`, scope `blended`. Above → scope `user`. A
   server with no listens either → the configured starting genres, scope `configured`. All four
   empty → `state = 'not_enough_data'`.
3. **Shares.** `genre_shares()` normalises the genre affinities to sum to 1. A genre below
   `min_share` is rolled up into its nearest parent that is itself above the threshold; what remains
   unattached becomes the `__tail__` share.
4. **Candidates.** One query, filtered on: has a media file, `0 < duration_secs < max_track_seconds`,
   and — when `release_window_days` is set — a release date of day precision (`LENGTH(release_date)
   = 10`) inside the window. The window is **closed at both ends**: `>= now - release_window_days`
   *and* `<= now`. `release_date` is read out of a file tag and is not validated anywhere, so a
   track mistagged `2027-01-01` otherwise passes both the precision check and the lower bound, and
   step 7's release-descending order then pins it to the top of every radar for as long as the tag
   survives. Both feeds use the same bounded window. Pools are applied as SQL: `unheard` excludes
   tracks in this user's listens, `loved` requires `rating >= loved_min_rating`, and the two are
   OR-ed when both are present.
5. **Buckets.** `bucket_of()` assigns each candidate to a share: its own deepest genre if that genre
   has a share, else the dominant genre of its label, else of its primary artist, else `__tail__`.
   The two dominant-genre aggregations are **bounded to the distinct labels and artists the
   candidates carry**, passed as `IN (%s, ...)` parameters. Unbounded they group over every
   `(label, genre)` and every `(artist, genre)` pair in a 300k-track library — two full-library
   aggregations on every feed request, to answer a question about a few hundred names. An empty
   name set skips the query rather than emitting `IN ()`. The audio-features subquery in the
   candidate query is deliberately *not* bounded this way; it needs a different shape.
6. **Quota.** `allocate()` splits `size` places over the shares by largest remainder;
   `redistribute()` hands unfillable places to the next largest share until nothing is left to give.
7. **Order.** Within a share: for `order='release'`, unheard before heard when
   `heard_rank_penalty`, then `release_date` descending, then score descending. For
   `order='daily_sample'`, ascending `daily_sample_key`, which is `-ln(U) / B` with `U` derived from
   `md5(username|feed_date|track_uid)` — stable for a whole day, different the next.
8. **Cap and emit.** At most `max_per_artist` per primary artist (unknown artists are not one
   bucket; each such track partitions on its own id), then the global `size`. Every emitted track
   carries the bucket it competed in and the reason it was placed there (`genre`, `label:<name>`,
   `artist:<name>`, `tail`). `funnel` records the row count after every stage above.

The "configured starting genres" in step 2 come from a runtime setting, `feeds_starting_genres`
(`services/common/config_store.py`, group `Feeds`) — a comma-separated list of genre names, e.g.
`uptempo,raw hardcore`. It is read once per request (`routers/feeds.py:_starting_genres()`) and
passed to `build_feed` as `starting_genres`. Unset (the default, `''`) means no configured
fallback at all: when neither the listener nor the server has any listening history, the feed
reports `state = 'not_enough_data'` rather than falling back to anything, and `GET
/api/feeds/profile` reports `scope = 'empty'`.

## API Contract

All endpoints require the existing `X-API-Key` header (`routers/library.py:verify_api_key`
semantics: a user key or the system key). A user key resolves the username; the system key must pass
`?username=` and 400s without it.

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/feeds` | — | `{"feeds": [{"slug": "release-radar", "size": 30, "window_days": 7}, ...]}` | 401 missing/invalid key |
| `GET /api/feeds/{slug}` | `limit` (1–100, default from policy), `username` (system key only) | `{"slug", "state", "scope", "generated_at", "tracks": [...], "funnel": {...}}` | 401; 404 unknown slug; 400 system key without `username`; 500 no database |
| `GET /api/feeds/profile` | `username` (system key only) | `{"scope", "distinct_tracks", "artists": [{"name","affinity"}], "labels": [...], "genres": [...], "excluded": [...]}` | 401; 400; 500 |
| `PUT /api/feeds/profile/exclusions` | `{"entity_type": "label", "entity_name": "X", "excluded": true}` | `{"status": "ok"}` | 401; 422 unknown `entity_type`; 500 |

`state` is `ok`, `no_matches` (nothing survived the filters) or `not_enough_data` (no profile could
be built at all). A track object is the shape `/api/library/advanced` already returns — `id`, `title`,
`artist`, `label`, `genres`, `duration_secs`, `bpm`, `release_date`, `file_path` — plus `bucket` and
`reason`. `tracks` is `[]` for both non-`ok` states, and the state is what the caller renders on;
an empty list is never returned with `state = "ok"`.

## Cross-App Impact

**None in V1.** No client consumes these endpoints yet. That is deliberate: the path-based bridge
between a MuMa track and an LMS song is unproven (see `functional.md`, Open Questions), and the
returned `file_path` is exactly what a later LMS endpoint needs in order to resolve a playable song.
Web, mobile and the LMS server are a separate change, made atomically per AGENTS.md rule 7 once the
bridge is demonstrated.

## Dry Run

`python scripts/feeds_dryrun.py --username user --slug release-radar --window 7 --limit 30` prints
the funnel per stage (candidates after the window, after the pool, after bucketing, after quota,
after the artist cap), the computed shares, and the resulting tracks with their bucket and reason.
It takes `--window`, `--size` and `--max-seconds` overrides so a policy can be tuned against real
data without editing code. This is the tool that answers whether the seven-day window is viable.

## Technical Acceptance Criteria

1. `deepest({'Uptempo', 'Hardcore'}, parents)` returns `{'Uptempo'}`; `deepest({'Hardcore'}, parents)`
   returns `{'Hardcore'}`; a cycle in `rules_subgenre_hierarchy` terminates at `max_depth` instead of
   recursing forever.
2. `listen_weight` halves over 30 days, returns a quarter weight for `fuzzy`, and treats
   `played_secs=None` as full engagement rather than zero.
3. `build_profile` drops an entity supported by only one distinct track, and normalises the largest
   remaining entity in each dimension to exactly `1.0`.
4. An excluded label contributes nothing to the profile, and its exclusion changes the shares.
5. `allocate({'uptempo': 0.5, 'raw': 0.25, 'hardtechno': 0.10, '__tail__': 0.15}, 30)` returns
   `{'uptempo': 15, 'raw': 7, 'hardtechno': 3, '__tail__': 5}` and the values sum to exactly 30.
6. `redistribute` moves the places of a share with zero available candidates to the next largest
   share, and never returns an allocation larger than `available` for any share.
7. `bucket_of` places a candidate with no genre tag on a label whose catalogue is 100% uptempo into
   `uptempo`, with reason `label:<name>`; a candidate with no genre, no label and an unknown artist
   into `__tail__`.
8. `dominant_genre` returns `None` when the top genre holds less than 60% of a label's tagged
   tracks.
9. The candidate SQL contains `LENGTH(af.release_date) = 10` when a release window is set, never
   contains `created_at`, joins audio features on `internal_track_id`, and joins `rating_tracks` on
   all three key columns. It bounds the window at both ends, so a track tagged with a release date
   in the future is outside the window and never appears, in either feed.
10. The candidate SQL for `pools={'unheard', 'loved'}` produces one `OR` group, not two `AND`ed
    conditions.
11. `daily_sample_key` returns the same value for the same `(username, date, track_uid)` and a
    different value for the next date.
12. `GET /api/feeds/release-radar` returns `state='no_matches'` with `tracks=[]` when the window is
    empty, and never falls back to a wider window.
13. `GET /api/feeds/unknown-slug` returns 404; a system key without `username` returns 400.
14. A user with fewer than five distinct listens gets `scope='server'`; one with fifteen gets
    `scope='blended'`.
15. `scripts/feeds_dryrun.py` runs against the integration database and prints a funnel whose stages
    are monotonically non-increasing.

## Deliberately Not In V1

- **No snapshot table and no nightly job.** The daily mix is stable because its order is a hash of
  `(username, date, track_uid)`, not because it is stored. The radar is filtered by a window first,
  so its candidate set is small. Materialisation buys nothing until a measurement shows the live
  query is slow.
- **No client work.** See Cross-App Impact.
- **No new genre inference, no BPM or audio-feature matching, no collaborative filtering, no
  listener-adjustable weights, no set feed.**

## Related Docs

- [`functional.md`](functional.md) — the agreed behaviour, and the measurements this design still
  depends on.
- [`docs/designs/genre-curation/`](../genre-curation/) — `rules_subgenre_hierarchy` and the genre
  states this reads.
