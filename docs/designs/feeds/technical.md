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
| `library_track_genres` / `rules_genres` | the genre dimension; `state <> 'black'` only; `rules_genres.hardness` feeds the three spectrum mixes (see "Daily mixes v2 — hardness" below) |
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

One column is added, the way this repository always adds one: `services/common/db_init.py`'s
idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, mirrored in a standalone
`migrate_v25_genre_hardness.sql` for production. A one-shot startup seed
(`feeds.hardness.seed_genre_hardness`, called from `main.py` next to the other `init_db` calls)
fills it from the anchor list and the subgenre hierarchy; see "Daily mixes v2 — hardness" below.

```sql
ALTER TABLE rules_genres ADD COLUMN IF NOT EXISTS hardness TINYINT UNSIGNED NULL;
```

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
- **A feed holds one entry per song, and it is the canonical** (step 4b). The canonical choice
  itself is muma's (`song_version_worker.py`); the feed only reads it.

### Known Limitations

**An uncurated genre splits the profile, and V1 does not fix it.** Every genre selection here takes
`rules_genres.name` where `state <> 'black'`, which is white *and* unknown. The scanner indexes a
white genre under its curated name and an unknown one under its raw name, so `'Uptempo Hardcore'`
and an undecided `'uptempo'` are two rows, two entities in the profile, and two shares. The
listener's weight for one style is split across both, and the raw variant has no
`rules_subgenre_hierarchy` row, so it cannot roll up into a parent either and falls to `__tail__`.

This is not fixed in V1, deliberately. The correct fix goes through the curation model's own rewrite
table, `rules_genre_expansions` — mapping a raw name onto the curated genre it means — and not
through `canonical_id`, which is a legacy column the tagger no longer reads (see
`migrate_v4_genre_expansions.sql`). A wrong guess in that mapping silently merges two genres that
are not the same thing and corrupts every profile built afterwards, with nothing in the output
saying so. Getting it right is curation work, not feed work.

**How it presents:** as a thin profile, never as an error. The shares look plausible, the smaller
half of a split genre falls below `min_share` and rolls into the tail, and the feed simply gives
that style fewer places than the listener's actual listening earns. `GET /api/feeds/profile` is
where it is visible: the same style appearing twice under two spellings is this, and the dry run's
share table shows it directly. That is the intended way to measure how much it costs before
deciding to fix it.

## Module Layout

New package `services/music_manager/feeds/`. Every module below is pure Python over plain rows
except `queries.py` (builds SQL) and `build.py` (the only module that touches a connection), which
is what makes the whole ranker unit-testable without a database.

| File | Responsibility |
|---|---|
| `policy.py` | `FeedPolicy` dataclass and the seven named policies |
| `hierarchy.py` | subgenre graph: ancestors, and reducing a track's tags to its deepest genres |
| `profile.py` | listen weighting, the three affinity tables, blending, and genre shares |
| `quota.py` | largest-remainder allocation and redistribution of unfilled shares |
| `buckets.py` | dominant genre per label/artist, and which share a candidate competes in |
| `scoring.py` | the per-candidate score `B`, the deterministic daily sample key, and `pick_daily_entity` (the artist/label rotation) |
| `hardness.py` | anchor list, the tempo mapping, `track_hardness`'s fallback chain, the fixed default band edges, the (now informational) band-edge percentiles, and the startup seed |
| `queries.py` | every SQL string, as `(sql, params)` builders |
| `build.py` | orchestration: profile → candidates → buckets → quota → ordered feed; also `describe_feed` (title/subtitle without the full pipeline) |
| `routers/feeds.py` | HTTP surface and `init_db` |
| `scripts/feeds_dryrun.py` | prints the funnel, the top N with the reason per track, and (for a spectrum mix) the band edges and hardness source tally |

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
    hardness_band: str | None = None              # 'soft' | 'mid' | 'hard' | None
    rotate: str | None = None                     # 'artist' | 'label' | None

POLICIES: dict[str, FeedPolicy]
# 'release-radar', 'daily-mix' (classic, unrestricted -- not an alias of any
# band), 'daily-mix-soft', 'daily-mix-mid', 'daily-mix-hard', 'daily-mix-artist',
# 'daily-mix-label'

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
# Largest remainder; a remainder tie goes to the larger share, then alphabetically.
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
def pick_daily_entity(username: str, feed_date: date, ranked_names: list[str]) -> str | None
    # a hash of (username, feed_date), the same trick as daily_sample_key

# hardness.py
ANCHOR_HARDNESS: dict[str, int]                # curated genre name (lowercase) -> 0-100
DEFAULT_BAND_EDGES: tuple[float, float]        # (50.0, 75.0); used unless feeds_hardness_edges overrides it
def tempo_hardness(tempo: float | None) -> float | None
def track_hardness(genre_weighted_sum: float | None, genre_weight_sum: float | None,
                   label_mean: float | None, artist_mean: float | None,
                   tempo: float | None) -> tuple[float | None, str]
    # returns (hardness, source); source is 'genre' | 'label' | 'artist' | 'tempo' | 'none'
def hardness_percentiles(weighted_hardness: list[tuple[float, float]]) -> dict[str, float] | None
    # {'p33', 'p50', 'p67'}, or None with no data -- informational, does not decide the band edges
def classify_band(hardness: float, lo: float, hi: float) -> str   # 'soft' | 'mid' | 'hard'
def seed_genre_hardness(cursor) -> int         # rows updated; only ever fills hardness IS NULL

# policy.py (continued)
HARDNESS_EDGES_SETTING = 'feeds_hardness_edges'
def parse_hardness_edges(raw: str | None) -> tuple[tuple[float, float], str]
    # (edges, 'setting' | 'default'); garbage or unset resolves to (DEFAULT_BAND_EDGES, 'default')

# build.py
@dataclass
class Feed:
    slug: str
    state: str          # 'ok' | 'no_matches' | 'not_enough_data'
    scope: str
    tracks: list[dict]
    funnel: dict[str, int]
    title: str | None = None
    subtitle: str | None = None
    hardness_band: tuple[float, float] | None = None
    hardness_edges_source: str | None = None       # 'setting' | 'default'; hardness_band policies only
    hardness_source_counts: dict[str, int] | None = None
    hardness_percentiles: dict[str, float] | None = None   # informational; hardness_band policies only
    relaxed_to: int | str | None = None   # int, 'none', or None (no relaxation)
    filled_from_unknown: int | None = None   # hardness_band only; None elsewhere
@dataclass(frozen=True)
class ProfileResolution:
    profile: TasteProfile
    shares: dict[str, float]
    parents: dict[str, set[str]]
def resolve_profile(conn, username: str, window_days: int, now: datetime,
                    starting_genres: list[str] | None = None) -> ProfileResolution
def build_feed(conn, username: str, policy: FeedPolicy, now: datetime,
               starting_genres: list[str] | None = None,
               hardness_edges: tuple[float, float] | None = None,
               hardness_edges_source: str = 'default') -> Feed
def describe_feed(conn, username: str, policy: FeedPolicy, now: datetime,
                  starting_genres: list[str] | None = None,
                  hardness_edges: tuple[float, float] | None = None,
                  hardness_edges_source: str = 'default') -> dict
    # {'title', 'subtitle'} without running the candidate pipeline -- what GET /api/feeds uses
```

`resolve_profile` is steps 1–3 below, and it is the **only** implementation of them.
`build_feed`, `GET /api/feeds/profile` and `scripts/feeds_dryrun.py` all call it. They each used
to carry their own copy, and the copies had already drifted — the dry run's never applied
`starting_genres`, so the configured-fallback path was invisible to the tool built to measure it.
A profile view that does not resolve exactly what the feed resolves stops explaining the feed.

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
   songs in this user's listens, `loved` requires `rating >= loved_min_rating`, and the two are
   OR-ed when both are present. `heard` and `rating` are **per song, not per file** (bug report
   096): a listen of any version of the track's work counts as heard, and the rating is the highest
   this user gave any version (the display roll-up of the song-versions design); a track without a
   work keeps its own.
   **4b. One per song.** `_collapse_to_songs` reduces the candidates to one per work *before*
   anything is bucketed, ranked or capped, so two versions of one song can never take two places.
   The representative is the work's canonical (`library_works.canonical_track_id`); when the
   canonical is not a candidate itself -- the rip is inside the window, the official release is not
   -- it is fetched with `canonical_rows_query` in the same row shape, so it is scored on its own
   label and provenance and its path is what the client plays. A canonical without a file leaves
   the lowest-id qualifying version. The song's `release_date` is the newest of the *qualifying*
   versions' dates, never the fetched canonical's own tag, which never passed the window.
   Ungrouped tracks pass through. This applies to every policy, since every policy loads through
   the same function.
5. **Buckets.** `bucket_of()` assigns each candidate to a share: its own deepest genre if that genre
   has a share, else the dominant genre of its label, else of its primary artist, else `__tail__`.
   The two dominant-genre aggregations are **bounded to the distinct labels and artists the
   candidates carry**, passed as `IN (%s, ...)` parameters. Unbounded they group over every
   `(label, genre)` and every `(artist, genre)` pair in a 300k-track library — two full-library
   aggregations on every feed request, to answer a question about a few hundred names. An empty
   name set skips the query rather than emitting `IN ()`. The audio-features subquery in the
   candidate query is deliberately *not* bounded this way; it needs a different shape.
6. **Quota.** `allocate()` splits `size` places over the shares by largest remainder — and when two
   remainders tie, the larger share takes the place (then alphabetically, so the result is
   deterministic); `redistribute()` hands unfillable places to the next largest share until nothing
   is left to give.
7. **Order.** Within a share: for `order='release'`, unheard before heard when
   `heard_rank_penalty`, then `release_date` descending, then score descending. For
   `order='daily_sample'`, ascending `daily_sample_key`, which is `-ln(U) / B` with `U` derived from
   `md5(username|feed_date|track_uid)` — stable for a whole day, different the next. The same key is
   then applied a **second time, globally**, over the tracks all the shares together produced. That
   is deliberate: the per-share sort decides *which* tracks win their share's places, the global one
   decides what the listener reads first. Without it the feed comes out grouped by bucket, in
   whatever order the allocation happens to be iterated in.
8. **Cap and emit.** At most `max_per_artist` per primary artist (unknown artists are not one
   bucket; each such track partitions on its own id), then the global `size`. Every emitted track
   carries the bucket it competed in and the reason it was placed there (`genre`, `label:<name>`,
   `artist:<name>`, `tail`). `funnel` records the row count after every stage above.

   **The artist cap can leave the feed short.** It removes tracks after their share was allocated
   and filled, and the freed places are not handed back to another share. A radar asked for 30 can
   therefore return 24, with `state = 'ok'`. That is intentional and it is the one failure mode this
   feature promises to make legible rather than paper over: `funnel.capped` below `funnel.allocated`
   is exactly this, and nothing is backfilled with an unrelated track to hide it. The `[: size]`
   slice after the cap is a guard, not a working limit — `allocate` never hands out more than `size`
   and every later stage only shrinks the list — kept so that "never more than asked for" does not
   depend on the quota's arithmetic staying correct.

The "configured starting genres" in step 2 come from a runtime setting, `feeds_starting_genres`
(`services/common/config_store.py`, group `Feeds`) — a comma-separated list of genre names, e.g.
`uptempo,raw hardcore`. It is read once per request (`routers/feeds.py:_starting_genres()`) and
passed to `build_feed` as `starting_genres`. Unset (the default, `''`) means no configured
fallback at all: when neither the listener nor the server has any listening history, the feed
reports `state = 'not_enough_data'` rather than falling back to anything, and `GET
/api/feeds/profile` reports `scope = 'empty'`.

The three spectrum mixes' band edges come from a second runtime setting in the same group,
`feeds_hardness_edges` — `"<soft/mid>,<mid/hard>"`, e.g. `"50,75"`. Read once per request
(`routers/feeds.py:_hardness_edges()`, `policy.parse_hardness_edges`) and passed to `build_feed`/
`describe_feed` as `hardness_edges`; unset or unparsable resolves to `hardness.DEFAULT_BAND_EDGES`
(`50.0, 75.0`) rather than raising, exactly like `starting_genres`'s own "garbage becomes no
override" contract. See "Daily mixes v2 — hardness" below for why the edges are fixed at all.

## Daily mixes v2 — hardness

Implements functional.md's "Daily mixes v2". Three of `POLICIES`' seven entries carry a
`hardness_band` and two carry a `rotate`; both are orthogonal to the eight-step algorithm above —
they change *which* candidates enter step 4 and *what* `describe_feed`/`build_feed` label the
result, never how steps 5-8 process what comes out of it.

### Genre hardness (the seed)

`feeds.hardness.seed_genre_hardness(cursor)` runs once per startup (`main.py`, next to the other
`init_db` calls), after `ensure_tables_exist()` has added the column:

1. Read every `rules_genres` row. A row whose `hardness` is already set (an anchor from a previous
   run, or a curator's own edit) is left alone and its value is remembered as a known point.
2. For every still-`NULL` row, match `name.lower()` against `ANCHOR_HARDNESS` and fill it in if
   found — that value also becomes a known point for step 3.
3. For every row still `NULL` after that, call `hierarchy.nearest_ancestor(name.lower(), parents,
   known_names)` over the `rules_subgenre_hierarchy` graph. `nearest_ancestor` already walks the
   whole graph per call (breadth-first, alphabetical tie-break), so a genre two or three hops from
   its nearest anchor resolves in this same pass — no second startup needed for a longer chain.
4. Anything with no anchor ancestor at all stays `NULL`.

Idempotent by construction: step 1's "already set, skip" is the only thing that matters for
re-running it, and it is exactly what makes a curator's manual edit permanent until they clear it
back to `NULL` themselves (`PUT /api/curation/genres/{name}/hardness` with `hardness: null`).

### Track hardness (the fallback chain)

`feeds.hardness.track_hardness(genre_weighted_sum, genre_weight_sum, label_mean, artist_mean,
tempo)` is pure: every input is looked up beforehand, bounded to the track ids or names actually in
play, the same pattern `_dominant_genre_map` already uses for the label/artist bucket lookup:

- `genre_hardness_query(track_ids)` — one row per track, `SUM(weight * hardness)` and `SUM(weight)`
  over genres that have a `hardness` and are not `black`. A `weight_sum` of zero (no scored genre at
  all) is what tells `track_hardness` to move to the next step.
- `entity_hardness_query('label' | 'artist', names)` — a label's or artist's mean hardness over its
  own tracks with a known hardness, `HAVING COUNT(DISTINCT track_id) >= MIN_TRACKS_FOR_ENTITY_MEAN`
  (5): one outlier release must not decide what an unrelated track on the same label inherits.
- `tempo_hardness(tempo)` — piecewise linear between fixed anchor points (140 BPM → 20, ... 200 BPM
  → 95), clamped outside them.

`build._annotate_hardness` runs these in two passes so a row whose label already answers the
question never spends a second query on its artist: first every row lacking a resolved genre asks
its label, then only the rows still unresolved ask their artist. The result is `(hardness,
source)` on every row, `source` one of `'genre' | 'label' | 'artist' | 'tempo' | 'none'`.

### Band edges and filtering

The edges are **fixed**, not measured from the listener asking: `hardness.DEFAULT_BAND_EDGES`
(`50.0, 75.0`) unless `feeds_hardness_edges` overrides them (see the runtime-setting paragraph
above). `build._describe` resolves them once — `hardness_edges if hardness_edges is not None else
DEFAULT_BAND_EDGES` — and that same pair is what both `describe_feed`'s title/subtitle and
`build_feed`'s candidate filter use, so the number a listener reads is always the number applied.
`Feed.hardness_edges_source` reports which one won, `'setting'` or `'default'`.

This replaced an earlier version that derived the two edges from *this listener's own* weighted
hardness distribution — their weighted 33rd/67th percentile, a fixed `(40, 70)` fallback below 30
heard tracks with a resolvable hardness, widened to `median ± 15` when those two percentiles landed
within 15 points of each other. Measured on production right after that version shipped (0.63.0), a
listener whose own history skewed uptempo saw their own edges come out at 62.5/92.5, which meant
"Zachter" filtered down to raw hardstyle, techno and mainstream hardstyle, "Middenin" to uptempo
hardcore, bouncy uptempo and zaagtempo, and "Harder" shrank to only terror and speedcore. A
listener's own history is exactly the wrong input for where a band starts:
whoever plays the most of one style is the person for whom that style should least be allowed to
redefine "the middle". `build._listener_hardness_stats(conn, username, window_days, now)` still
computes this distribution the same way — re-reading the same listens `build_profile` does
(`_load_listens`, same window), annotating each with a hardness the same way a candidate is
annotated, reducing to one `(hardness, listen_weight)` pair per *distinct* track — and
`hardness.hardness_percentiles()` still turns it into `{'p33', 'p50', 'p67'}`, but only to *report*
on the profile view and in the dry run (`Feed.hardness_percentiles`, `None` when nothing resolved a
hardness at all). Nothing reads it to decide a boundary any more.

`build._load_band_candidates`, for a `hardness_band` policy, loads candidates, annotates them the
same way, and keeps only the ones whose `classify_band(hardness, lo, hi)` matches the policy's own
band — a candidate with no resolvable hardness is dropped at this step, never guessed into a bucket
here. If fewer than `MIN_BAND_CANDIDATES` (15) survive, the loop retries with `release_window_days`
widened 90 → 365 → `None` (`BAND_RELAXATION_WINDOWS`), and `Feed.relaxed_to` reports whichever
widened value was actually used — the literal string `'none'` for "no window at all", never a bare
`None`, which already means "no relaxation happened" on the same field. Steps 5-8 then run on this
banded set exactly as for any other policy.

**Backfill from unknown hardness.** A design correction made after this shipped once already:
aliasing `daily-mix` to `daily-mix-mid` meant a track with no scored genre lost its place on the one
slug already in production, and the same failure mode applies to the three band mixes themselves on
a library whose tagger has not caught up — 28% genre coverage means most tracks start with no
hardness at all, so "not enough candidates in the band" is the common case, not the edge case. After
steps 5-8 run on the banded set, `build._backfill_from_unknown` checks whether `emitted` is still
short of `policy.size`; if so, it re-fetches candidates at `release_window_days=None` (a second
query, only when needed), keeps the ones with no resolvable hardness that are not already emitted,
orders them with the same `order_key` steps 5-8 used, and fills the remaining places — capped by
`max_per_artist` against the combined list, so a backfilled track still cannot flood one artist past
the cap. Every backfilled track carries `bucket='__unknown__'`, `reason='unknown_hardness'`, and the
count actually added is `Feed.filled_from_unknown` (an int for every `hardness_band` policy, `None`
for every other one — `0` when the band filled the mix on its own). A hardness_band mix therefore
never reports `no_matches` unless there is truly nothing in the library to offer it at all, both
banded and unbanded.

### Rotation

`daily-mix-artist` / `-label` restrict `candidates_query` to one artist or one label via the new
`entity_filter` parameter (`('artist' | 'label', name)`) — a plain `a.name = %s` or an `EXISTS`
against `library_track_labels`, appended after every other `WHERE` clause. Which name is `build.
_ranked_names(profile.artists | profile.labels)`'s top 10, indexed by `scoring.pick_daily_entity`
— `int(md5(username|date|'entity')[:8], 16) % len(names)` — the same day-stable-hash trick
`daily_sample_key` already uses for track ordering, applied once per request instead of once per
track. A profile with no artist (or label) affinities at all has nothing to rotate through and the
feed reports `not_enough_data`.

**Only a name with enough to play is drawn** (bug report 110). The hash alone once drew an artist
whose tracks inside the 90-day window were all heard and none loved — 0 candidates — and the day
before an artist with 2. The window, the unheard-or-loved pool and the per-artist cap of 3 together
meant almost no artist in anyone's top ten could fill an artist mix at all: measured on production
on 2026-09-26, none of Teun's top ten artists reached 15 songs at 90 days, three did at 365 days,
nine with no window. So `build._describe` now asks before it draws:

- `queries.rotation_counts_query(username, policy, now, dimension, names, windows)` — one grouped
  statement over the whole top ten, bounded to those names, applying `candidates_query`'s own
  filters (a media file, the duration bounds, the pool) and counting
  `COUNT(DISTINCT COALESCE(work_id, -id))` — the key `build.song_key` collapses on — once per window
  of `ROTATION_RELAXATION_WINDOWS` (90, 365, no window; the band ladder). Never a candidate query
  per name tried. Both queries build the window from one helper, `_release_window_conditions`.
- `scoring.pick_playable_entity` starts at the same day-stable index `pick_daily_entity` uses and
  walks the ranking from there, wrapping around, taking the first name that reaches
  `MIN_ROTATION_CANDIDATES` (15, the same floor as `MIN_BAND_CANDIDATES`: half of the 30 places) at
  the narrowest window that does. The drawn name at a wider window is preferred over the next name
  at 90 days — the rotation is what the mix is for.
- The build then runs one candidate query at that window and reports it as `relaxed_to` exactly as
  a band does (`365`, `'none'`, or `null` when 90 days sufficed).
- **No name qualifies:** the feed reports `no_matches` with `tracks: []`, the default title
  (`Artiestmix` / `Labelmix`) and no subtitle — never an `ok` mix of a handful of tracks. The client
  already renders a non-`ok` feed as empty; the snapshot keeps it for `NON_OK_TTL_SECONDS` only.

`daily-mix-artist` carries `max_per_artist = size` (30): every candidate shares the one primary
artist the mix is restricted to, and a cap of 3 cut every artist mix to three tracks. The label mix
keeps the cap of 3 — its count is of songs, not of artists, so a label whose songs are mostly one
artist's can still come out shorter than 15 after the cap.

### Titles and subtitles

`build._describe(conn, username, policy, now, profile, hardness_edges, hardness_edges_source)` is
the one implementation both `describe_feed` (cheap — no candidate query, used by `GET /api/feeds` to
list every policy at once) and `build_feed` (which needs the band edges or the chosen entity anyway,
to filter candidates) call.
`Feed.title`/`Feed.subtitle` and the list endpoint's per-slug `title`/`subtitle` therefore always
agree: `DUTCH_BAND_TITLE` (`'Zachter' | 'Middenin' | 'Harder'`) for a band policy, the chosen name
for a rotating one, `'Release Radar'` for the radar, `CLASSIC_TITLE` (`'Klassiek'`) for `daily-mix`.

## API Contract

All endpoints require the existing `X-API-Key` header (`routers/library.py:verify_api_key`
semantics: a user key or the system key). A user key resolves the username; `GET /api/feeds/{slug}`
and `PUT /api/feeds/profile/exclusions` 400 a system key that passes no `?username=`. `GET
/api/feeds` is the one exception: `username` is optional even for the system key, since listing
what exists needs no listener in mind (see "Titles and subtitles" above for what a caller with no
resolvable username gets instead).

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/feeds` | `username` (optional, either key) | `{"feeds": [{"slug", "size", "window_days", "title", "subtitle"}, ...]}` — all seven policies, including the classic `daily-mix` | 401 missing/invalid key |
| `GET /api/feeds/{slug}` | `limit` (1–100, default from policy), `username` (system key only) | `{"slug", "state", "scope", "generated_at", "tracks": [...], "funnel": {...}, "title", "subtitle", "hardness_band": [lo, hi] \| null, "hardness_edges_source": "setting" \| "default" \| null, "hardness_source_counts": {...} \| null, "hardness_percentiles": {"p33", "p50", "p67"} \| null, "relaxed_to", "filled_from_unknown"}` | 401; 404 unknown slug; 400 system key without `username`; 500 no database |
| `GET /api/feeds/profile` | `username` (system key only) | `{"scope", "distinct_tracks", "artists": [{"name","affinity"}], "labels": [...], "genres": [...], "excluded": [...]}` | 401; 400; 500 |
| `PUT /api/feeds/profile/exclusions` | `{"entity_type": "label", "entity_name": "X", "excluded": true}` | `{"status": "ok"}` | 401; 422 unknown `entity_type`; 500 |

`hardness_band`, `hardness_edges_source`, `hardness_source_counts`, `hardness_percentiles`,
`relaxed_to` and `filled_from_unknown` are `null` for every policy except the three spectrum mixes —
a classic feed simply never sets them (`Feed`'s own defaults). The one exception is `relaxed_to`,
which the two rotating mixes also set when today's name was only playable at a widened window (see
"Rotation" above); an additive value on a field that already existed, read by no client. `filled_from_unknown` is
`0`, not `null`, whenever a spectrum mix's own band filled `policy.size` without needing the
backfill in "Band edges and filtering" above. `hardness_percentiles` is `null` for a spectrum mix
too when nothing in the listener's history resolved a hardness at all — it never decides
`hardness_band`, so its absence changes nothing about which tracks the mix returns.

`state` is `ok`, `no_matches` (nothing survived the filters) or `not_enough_data` (no profile could
be built at all). A track object is the shape `/api/library/advanced` already returns — `id`, `title`,
`artist`, `label`, `genres`, `duration_secs`, `bpm`, `release_date`, `file_path` — plus `bucket` and
`reason`. `tracks` is `[]` for both non-`ok` states, and the state is what the caller renders on;
an empty list is never returned with `state = "ok"`.

## Cross-App Impact

**None in V1.** No client consumed these endpoints. That was deliberate: the path-based bridge
between a MuMa track and an LMS song was unproven (see `functional.md`, Open Questions), and the
returned `file_path` is exactly what a later LMS endpoint needs in order to resolve a playable song.
Web, mobile and the LMS server are a separate change, made atomically per AGENTS.md rule 7 once the
bridge is demonstrated.

### V2 — Android Auto

The bridge is demonstrated, and the feeds are now playable from the car. Three things changed:

- **`library_tracks.release_date`** (`migrate_v24_track_release_date.sql`), copied out of the
  server's `track.original_date` / `track.date` every hour by
  `services/music_manager/release_date_sync.py`, riding along in the lms.db pass that already syncs
  users, playlists, artist images and song versions. The candidate query prefers it over the
  audio-features column. **This is what made the feeds non-empty at all:** measured on production
  2026-09-10, `library_track_audio_features.release_date` was filled for 0 of 89.869 rows and that
  table covers 87.816 of 352.977 tracks, so `LENGTH(af.release_date) = 10` excluded the entire
  library. The server had a day-precision date for 238.207 of its 338.662 tracks, 169 of them
  released inside the radar's seven-day window.
- **`getSongsByPath`** on the server (`endpoints/SongsByPath.{hpp,cpp}`): repeated `path`
  parameters, library-relative the way `resolveScanScope` already defines it, answered with song
  nodes in the order asked. It never calls back out to music-manager — a Subsonic request that
  waits on an HTTP round trip holds a Wt thread, and that pool is small enough that a slow
  music-manager once took the site down.
- **`library_path`** in the feed's track view: `file_path` with the scan mount stripped, because
  MuMa's absolute path names a file the server does not have.

The client makes two calls, in that order, and re-sorts nothing: the order MuMa returns *is* the
feed.

## Dry Run

`python scripts/feeds_dryrun.py --username user --slug release-radar --window 7 --limit 30` prints
the funnel per stage (candidates after the window, after the pool, after bucketing, after quota,
after the artist cap), the computed shares, and the resulting tracks with their bucket and reason.
It takes `--window`, `--size` and `--max-seconds` overrides so a policy can be tuned against real
data without editing code, `--starting-genres` to try a configured fallback without writing it to
the runtime setting first (unset, it reads `feeds_starting_genres` exactly as the API does), and
`--hardness-edges` for the same trick with `feeds_hardness_edges` (unset, it reads that setting).
The shares it prints come out of the same `resolve_profile` call the feed itself runs, not out of a
second implementation. This is the tool that answers whether the seven-day window is viable.

For a spectrum slug (`--slug daily-mix-soft`, `-mid` or `-hard`), it additionally prints the edges
actually applied and whether the setting or the default supplied them, the tally of which fallback
source (`genre`/`label`/`artist`/`tempo`/`none`) resolved each heard track's hardness, the
listener's own weighted p33/p50/p67 (informational — it no longer decides the edges), and whether
the release window had to be widened to reach `MIN_BAND_CANDIDATES` — the anchor list is still an
unmeasured guess (functional.md, Open Questions), and this is the tool for judging it against real
listening history.

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
   `{'uptempo': 15, 'raw': 8, 'hardtechno': 3, '__tail__': 4}` and the values sum to exactly 30.
   `raw` and `__tail__` tie on a remainder of exactly 0.5, and **a remainder tie goes to the larger
   share** — so the last place goes to `raw` (25%) rather than to the tail (15%).
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
16. `resolve_profile` is the only implementation of steps 1–3: with no listens anywhere and
    `starting_genres` set it returns `scope='configured'` and shares over exactly those genres;
    with `starting_genres` unset it returns `scope='empty'`; and a listener with a profile of
    their own is never overruled by a configured fallback.
17. `seed_genre_hardness` fills an anchor name directly, resolves a multi-level subgenre chain to
    its nearest anchor ancestor in one pass, leaves a genre with no anchor ancestor `NULL`, and
    never overwrites a row whose `hardness` is already set — including on a second run.
18. `track_hardness` returns `'genre'` whenever `genre_weight_sum > 0`, regardless of what the
    label or artist mean would otherwise say; falls through to `'label'`, then `'artist'`, then
    `'tempo'` only when the step before it had nothing; and returns `(None, 'none')` when every
    signal is absent.
19. A `hardness_band` policy's edges are `hardness.DEFAULT_BAND_EDGES` (`50.0, 75.0`) regardless of
    the listener's own history, unless `feeds_hardness_edges` is set to two ascending values inside
    0–100, in which case those win; `Feed.hardness_edges_source` reports which one applied
    (`'default'` or `'setting'`). An unset, malformed, non-ascending or out-of-range setting value
    falls back to the default rather than raising. `hardness_percentiles` still reports the
    listener's own weighted p33/p50/p67 (or `None` with no resolvable history) alongside the edges,
    but nothing reads it to decide `hardness_band`.
20. A `hardness_band` policy excludes a candidate with no resolvable hardness from the band-matching
    step (`funnel.bucketed`); a policy with too few candidates in its band after filtering relaxes
    `release_window_days` 90 → 365 → `None` in that order and reports the widened value (`'none'`
    for no window, never a bare `None`) as `Feed.relaxed_to`.
21. `pick_daily_entity` is stable for the same `(username, date)` and changes for a different one;
    two different usernames are not guaranteed to diverge on every date pair, but do so across a
    handful of them.
22. `GET /api/feeds` lists all seven policies including the classic `daily-mix`, and reports a
    title/subtitle for every listed slug that `GET /api/feeds/{slug}` would independently agree
    with for the same listener (both call `_describe`/`describe_feed`, never a second computation).
23. `daily-mix` never excludes a candidate for lacking a resolvable hardness -- it carries no
    `hardness_band` at all, and a track with no scored genre competes for a place exactly as it did
    before this feature existed.
24. When a `hardness_band` policy's emitted tracks are still short of `policy.size` after the full
    relaxation ladder, `_backfill_from_unknown` fills the remainder from candidates with no
    resolvable hardness, tagged `bucket='__unknown__'`, `reason='unknown_hardness'`, capped by
    `max_per_artist` against the combined list; `Feed.filled_from_unknown` reports the count added
    (`0` when the band already filled the mix, `None` for every non-`hardness_band` policy). A
    `hardness_band` mix with any eligible candidates at all -- banded or not -- never reports
    `no_matches`.

## Deliberately Not In V1

- **No snapshot table and no nightly job.** The daily mix is stable because its order is a hash of
  `(username, date, track_uid)`, not because it is stored. The radar is filtered by a window first,
  so its candidate set is small. Materialisation buys nothing until a measurement shows the live
  query is slow. *Superseded 2026-09-18:* the measurement arrived as the web Home taking seconds
  per feed, and the band mixes' relaxation ladder (added after this was written) can widen a
  candidate set to the whole library. [`home-load.md`](home-load.md) adds `feeds_snapshot` and
  the `feeds-refresh` thread; the ranking itself is unchanged.
- **No client work.** See Cross-App Impact.
- **No new genre inference, no BPM or audio-feature matching, no collaborative filtering, no
  listener-adjustable weights, no set feed.**

## Related Docs

- [`functional.md`](functional.md) — the agreed behaviour, and the measurements this design still
  depends on.
- [`docs/designs/genre-curation/`](../genre-curation/) — `rules_subgenre_hierarchy` and the genre
  states this reads.
