"""Orchestration: profile -> candidates -> buckets -> quota -> ordered feed.

The only module in `feeds/` that touches a database connection -- every other
module works over plain rows so it can be unit tested without one (see
scripted_cursor.py and test_feeds_build.py). `build_feed` runs the eight steps
from docs/designs/feeds/technical.md, "Algorithm, in the order build_feed runs
it", in order, recording the funnel after each stage that can shrink the set:
`candidates`, `bucketed`, `allocated`, `capped`, `emitted`.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from services.music_manager.feeds import clock
from services.music_manager.feeds.buckets import bucket_of, dominant_genre
from services.music_manager.feeds.hardness import (
    DEFAULT_BAND_EDGES,
    classify_band,
    hardness_percentiles,
    track_hardness,
)
from services.music_manager.feeds.hierarchy import warn_cycles
from services.music_manager.feeds.policy import FeedPolicy
from services.music_manager.feeds.profile import TasteProfile, blend, build_profile, genre_shares, listen_weight
from services.music_manager.feeds.queries import (
    candidates_query,
    canonical_rows_query,
    dominant_genre_query,
    entity_hardness_query,
    exclusions_query,
    genre_hardness_query,
    hierarchy_query,
    listens_query,
)
from services.music_manager.feeds.quota import allocate, redistribute
from services.music_manager.feeds.scoring import daily_sample_key, pick_daily_entity, score

EMPTY_FUNNEL = {'candidates': 0, 'bucketed': 0, 'allocated': 0, 'capped': 0, 'emitted': 0}

# Mirrors blend()'s own default. Kept as one constant and passed explicitly to
# blend() below so the pre-check that decides whether to bother querying the
# server at all can never drift from the value blend() actually uses.
RAMP_TRACKS = 30

#: Dutch titles for the three spectrum mixes -- the only client-facing strings this
#: module owns. Both /api/feeds and /api/feeds/{slug} read them from here so the list
#: and the detail response can never disagree about what a band is called.
DUTCH_BAND_TITLE = {'soft': 'Zachter', 'mid': 'Middenin', 'hard': 'Harder'}

#: The classic, unrestricted 'daily-mix' slug's title -- distinct from the three
#: spectrum mixes so a client listing all six knows which one is the one it has
#: always called, with no hardness filter to come up short on a thin library.
CLASSIC_TITLE = 'Klassiek'

#: `release_window_days` 90 -> 365 -> None, tried in order until a hardness band
#: has enough candidates (`MIN_BAND_CANDIDATES`) or there is nothing left to relax.
#: Fixed rather than derived from the policy's own window because the three band
#: policies all start at 90 by construction (`policy.py`'s `_DAILY_MIX_BASE`) --
#: if that ever changes, this sequence has to be revisited by hand, not silently
#: reinterpreted.
BAND_RELAXATION_WINDOWS = (90, 365, None)
MIN_BAND_CANDIDATES = 15


@dataclass
class Feed:
    """One built feed: its tracks, how they were filtered, and what the client shows."""

    slug: str
    state: str  # 'ok' | 'no_matches' | 'not_enough_data'
    scope: str
    tracks: list[dict]
    funnel: dict[str, int]
    # Dutch, client-facing: what the home screen shows for this feed. None for
    # release-radar and the classic 'daily-mix', which have no per-request identity
    # of their own to describe.
    title: str | None = None
    subtitle: str | None = None
    # Only set for a hardness_band policy: the (soft/mid, mid/hard) edges this
    # build actually filtered against -- fixed on the genre anchors
    # (hardness.DEFAULT_BAND_EDGES) unless the feeds_hardness_edges setting
    # overrides them; never derived from this listener's own history.
    hardness_band: tuple[float, float] | None = None
    # Only set for a hardness_band policy: 'setting' when feeds_hardness_edges
    # supplied the edges above, 'default' when hardness_band fell back to
    # DEFAULT_BAND_EDGES.
    hardness_edges_source: str | None = None
    # Only set for a hardness_band policy: how many of this listener's heard tracks
    # resolved their hardness from each source ('genre', 'label', 'artist', 'tempo',
    # 'none'), for the dry run and for judging how much the fallback chain matters.
    hardness_source_counts: dict[str, int] | None = None
    # Only set for a hardness_band policy, and only when this listener has at least
    # one heard track with a resolvable hardness: their own weighted p33/p50/p67 --
    # informational since the edges above stopped being derived from it (see
    # hardness.hardness_percentiles). None when there is nothing to report.
    hardness_percentiles: dict[str, float] | None = None
    # Only set when a hardness band came up short and release_window_days was
    # widened to reach MIN_BAND_CANDIDATES: the number of days it was widened to,
    # the literal string 'none' when it was widened all the way to no window at
    # all, or None (the default) when no relaxation was needed. A bare `None` would
    # be ambiguous between those last two -- release_window_days=None already means
    # "no window" everywhere else in this package.
    relaxed_to: int | str | None = None
    # Only set for a hardness_band policy: how many places, after the full
    # relaxation ladder still left the band short of `policy.size`, were filled
    # from candidates with no resolvable hardness rather than left empty. `0` when
    # the band filled the mix on its own; `None` for every other policy, which
    # never runs this fallback at all.
    filled_from_unknown: int | None = None


@dataclass(frozen=True)
class ProfileResolution:
    """Everything steps 1-3 produce, for whoever asked for them.

    `build_feed` needs all three: the profile to score with, the shares to
    divide the places over, and the subgenre graph to bucket candidates
    against. `GET /api/feeds/profile` needs only the profile, and the dry run
    needs the shares -- but all three must come out of one computation, or the
    profile the listener is shown stops explaining the feed they get.
    """

    profile: TasteProfile
    shares: dict[str, float]
    parents: dict[str, set[str]]
    # The listener's own listens the profile was built from, so a caller that needs
    # them again (the band mixes' hardness percentiles) reads the rows already in
    # hand instead of running the listens query a second time. Empty when the
    # profile came from the server-wide history or the configured fallback.
    listens: list[dict] = field(default_factory=list)
    # Memo for what is derived from `listens` and asked for more than once per
    # resolution: `GET /api/feeds` describes seven policies off one resolution, and
    # three of them want the same hardness percentiles. A dict on a frozen
    # dataclass is still mutable inside, which is exactly the point.
    memo: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def scope(self) -> str:
        """The scope of the taste profile this resolution settled on."""
        return self.profile.scope


def _split(csv: str | None) -> list[str]:
    return [part for part in (csv or '').split(',') if part]


def _rows(conn, sql: str, params=None) -> list[dict]:
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        return list(cursor.fetchall())


def _load_hierarchy(conn) -> dict[str, set[str]]:
    parents: dict[str, set[str]] = defaultdict(set)
    for row in _rows(conn, hierarchy_query()):
        parents[row['subgenre'].lower()].add(row['genre'].lower())
    loaded = dict(parents)
    warn_cycles(loaded, 'feeds')
    return loaded


def _load_exclusions(conn, username: str) -> dict[str, set[str]]:
    sql, params = exclusions_query(username)
    exclusions: dict[str, set[str]] = {'artist': set(), 'label': set(), 'genre': set()}
    for row in _rows(conn, sql, params):
        exclusions.setdefault(row['entity_type'], set()).add(row['entity_name'].lower())
    return exclusions


def _load_listens(conn, username: str | None, window_days: int, now: datetime) -> list[dict]:
    sql, params = listens_query(username, window_days, now)
    return [
        {**row, 'labels': _split(row.get('labels')), 'genres': _split(row.get('genres'))}
        for row in _rows(conn, sql, params)
    ]


def _load_candidates(
    conn, username: str, policy: FeedPolicy, now: datetime, entity_filter: tuple[str, str] | None = None
) -> list[dict]:
    """Step 4: the candidate rows, collapsed to one per song (see `_collapse_to_songs`)."""
    sql, params = candidates_query(username, policy, now, entity_filter=entity_filter)
    candidates = [_candidate_row(row) for row in _rows(conn, sql, params)]
    return _collapse_to_songs(conn, username, candidates)


def _candidate_row(row: dict) -> dict:
    """A raw candidate row, with its comma-joined and 0/1 columns turned into Python values."""
    label = row.get('label')
    return {
        **row,
        'genres': _split(row.get('genres')),
        'labels': [label] if label else [],
        'heard': bool(row.get('heard')),
    }


def song_key(candidate: dict) -> tuple:
    """The song a candidate belongs to: its work, or the track itself when muma has not grouped it.

    A track without a work gets a key of its own, the same fallback LMS and the web use, so an
    ungrouped track is shown rather than folded into somebody else's song.
    """
    work_id = candidate.get('work_id')
    if work_id:
        return ('work', work_id)
    return ('track', candidate['id'])


def _collapse_to_songs(conn, username: str, candidates: list[dict]) -> list[dict]:
    """One candidate per song, standing in for the canonical version (bug report 096).

    Runs before anything is bucketed, ranked or capped, so two versions of one song can
    never take two places, and the version that is ranked is the one that will play:

    - the representative is the work's canonical. When the canonical is not a candidate
      itself (outside the window its rip is inside, say) it is fetched in the same row
      shape, so it is scored on its own label and provenance; when it has no file, the
      version that qualified stands in -- lowest id, so the pick is stable.
    - `heard` and `rating` already come out of the query per song, so every version
      carries the same values and the representative's are the song's.
    - `release_date` is the newest date among the versions that qualified: a song whose
      official release came out this week is new even when the canonical's own tag is
      older. Only qualifying versions count, because the window is what keeps a
      mistagged future date out, and a canonical fetched past the window never saw it.

    Ungrouped tracks pass through untouched, in their original order.
    """
    groups: dict[tuple, list[dict]] = {}
    for candidate in candidates:
        groups.setdefault(song_key(candidate), []).append(candidate)

    by_id = {candidate['id']: candidate for candidate in candidates}
    missing = sorted(
        {
            members[0]['canonical_track_id']
            for key, members in groups.items()
            if key[0] == 'work'
            and members[0].get('canonical_track_id')
            and members[0]['canonical_track_id'] not in by_id
        }
    )
    canonicals: dict[int, dict] = {}
    if missing:
        sql, params = canonical_rows_query(username, missing)
        wanted = set(missing)
        canonicals = {row['id']: _candidate_row(row) for row in _rows(conn, sql, params) if row['id'] in wanted}

    collapsed = []
    for key, members in groups.items():
        if key[0] == 'track':
            collapsed.extend(members)
            continue
        canonical_id = members[0].get('canonical_track_id')
        canonical = (by_id.get(canonical_id) or canonicals.get(canonical_id)) if canonical_id else None
        representative = canonical or min(members, key=lambda m: m['id'])
        dates = [m['release_date'] for m in members if m.get('release_date')]
        release_date = max(dates) if dates else representative.get('release_date')
        collapsed.append({**representative, 'release_date': release_date})
    return collapsed


def _distinct(candidates: list[dict], field: str) -> list[str]:
    """The distinct non-empty values of `field`, sorted so the SQL is stable.

    Sorted because the same feed run twice should produce the same statement
    text and the same parameter list -- an unordered set would defeat any
    statement cache and make a slow-query log unreadable.
    """
    return sorted({value for row in candidates if (value := (row.get(field) or '').strip())})


def _hardness_inputs(conn, track_ids: list[int]) -> dict[int, tuple[float, float]]:
    """`track_id -> (weighted_sum, weight_sum)`, from `genre_hardness_query`.

    Bounded to the ids actually in play, the same way `_dominant_genre_map` is
    bounded to the names in play -- an empty id set skips the query rather than
    sending `IN ()`.
    """
    if not track_ids:
        return {}
    sql, params = genre_hardness_query(track_ids)
    return {
        row['track_id']: (row.get('weighted_sum') or 0.0, row.get('weight_sum') or 0.0)
        for row in _rows(conn, sql, params)
    }


def _entity_hardness(conn, dimension: str, names: list[str]) -> dict[str, float]:
    """`name.lower() -> mean_hardness`, from `entity_hardness_query`, for names with
    fewer than `MIN_TRACKS_FOR_ENTITY_MEAN` scored tracks the row is simply absent
    (the query's own `HAVING` floor), not present with a `None` mean."""
    if not names:
        return {}
    sql, params = entity_hardness_query(dimension, names)
    return {
        row['name'].lower(): row['mean_hardness']
        for row in _rows(conn, sql, params)
        if row.get('mean_hardness') is not None
    }


def _annotate_hardness(conn, rows: list[dict], id_field: str) -> None:
    """Attach `hardness` (float or None) and `hardness_source` to every row, in place.

    Shared by candidate filtering (`id_field='id'`) and listener band-edge
    computation (`id_field='track_id'`) -- both need the same fallback chain over
    the same three bounded lookups, and a second copy of this wiring is exactly how
    the two would end up disagreeing about what a track's hardness is.

    Each row must already carry `label` (a single name or falsy) and `artist`. The
    label/artist lookups are computed in two passes: first the labels of every row
    whose own genres carried no hardness, then -- only for rows still unresolved --
    the artists, so a row whose label already answered the question never spends a
    second bounded query asking about its artist too.
    """
    ids = [row[id_field] for row in rows if row.get(id_field) is not None]
    genre_inputs = _hardness_inputs(conn, ids)

    def _genre_pair(row: dict) -> tuple[float, float]:
        row_id = row.get(id_field)
        if row_id is None:
            return (0.0, 0.0)
        return genre_inputs.get(row_id, (0.0, 0.0))

    needs_label = [row for row in rows if _genre_pair(row)[1] <= 0]
    label_means = _entity_hardness(conn, 'label', _distinct(needs_label, 'label'))

    def _label_mean(row: dict) -> float | None:
        return label_means.get((row.get('label') or '').strip().lower())

    needs_artist = [row for row in needs_label if _label_mean(row) is None]
    artist_means = _entity_hardness(conn, 'artist', _distinct(needs_artist, 'artist'))

    for row in rows:
        weighted_sum, weight_sum = _genre_pair(row)
        value, source = track_hardness(
            weighted_sum,
            weight_sum,
            _label_mean(row),
            artist_means.get((row.get('artist') or '').strip().lower()),
            row.get('bpm'),
        )
        row['hardness'] = value
        row['hardness_source'] = source


def _listener_hardness_stats(
    conn, resolution: ProfileResolution, now: datetime
) -> tuple[dict[str, float] | None, dict[str, int]]:
    """This listener's own weighted p33/p50/p67 hardness (or None), and the source
    tally -- informational, no longer what decides the band edges (see
    `hardness.DEFAULT_BAND_EDGES`).

    Measured over `resolution.listens`: the very rows `build_profile` ran on, so the
    percentiles a listener sees come from exactly the history their profile is
    built from, never a second, differently windowed read of `scrobble_listens`.
    Memoised on the resolution, because `GET /api/feeds` describes the three band
    policies off one resolution and the answer is the same for all three.
    """
    memoised: tuple[dict[str, float] | None, dict[str, int]] | None = resolution.memo.get('hardness_stats')
    if memoised is not None:
        return memoised
    rows = [dict(row) for row in resolution.listens]
    for row in rows:
        row['label'] = (row.get('labels') or [None])[0]
    _annotate_hardness(conn, rows, id_field='track_id')

    per_track_weight: dict[str, float] = defaultdict(float)
    per_track_hardness: dict[str, float] = {}
    per_track_source: dict[str, str] = {}
    for row in rows:
        uid = row['track_uid']
        age_days = (now - row['listened_at']).total_seconds() / 86400.0
        per_track_weight[uid] += listen_weight(age_days, row.get('match_method') or '', row.get('played_secs'))
        if row.get('hardness') is not None:
            per_track_hardness[uid] = row['hardness']
            per_track_source[uid] = row['hardness_source']

    source_counts = Counter(per_track_source.values())
    for uid in per_track_weight:
        if uid not in per_track_hardness:
            source_counts['none'] += 1

    weighted = [(hardness, per_track_weight[uid]) for uid, hardness in per_track_hardness.items()]
    stats = (hardness_percentiles(weighted), dict(source_counts))
    resolution.memo['hardness_stats'] = stats
    return stats


def _ranked_names(affinities: dict[str, float], limit: int = 10) -> list[str]:
    """The top `limit` names of a profile dimension, most affine first.

    Ties break alphabetically so the ranking -- and therefore which index
    `pick_daily_entity` lands on -- is deterministic given the same profile.
    """
    ranked = sorted(affinities.items(), key=lambda item: (-item[1], item[0]))
    return [name for name, _ in ranked[:limit]]


def _band_subtitle(lo: float, hi: float, band: str) -> str:
    if band == 'soft':
        return f'≤ {round(lo)} hardheid'
    if band == 'hard':
        return f'≥ {round(hi)} hardheid'
    return f'{round(lo)}–{round(hi)} hardheid'


def _describe(
    conn,
    username: str,
    policy: FeedPolicy,
    now: datetime,
    resolution: ProfileResolution,
    hardness_edges: tuple[float, float] | None = None,
    hardness_edges_source: str = 'default',
) -> dict:
    """title/subtitle/entity_filter/band_edges/hardness_source_counts for one policy.

    The one place both `describe_feed` (the cheap version `GET /api/feeds` uses to
    list what is available) and `build_feed` (which needs the same numbers anyway,
    to actually filter candidates) compute a feed's identity -- so the edges a
    listener is told about are always the edges that were applied, never a second,
    possibly different pass over the same profile.

    `hardness_edges`/`hardness_edges_source` are the already-resolved
    `feeds_hardness_edges` setting (or its absence) -- resolved once by the caller
    (`routers/feeds.py`, `scripts/feeds_dryrun.py`) exactly the way
    `starting_genres` already is, so the router and the dry run can never measure a
    different band than the one shipped. `hardness_edges=None` means "no override",
    resolved here to `DEFAULT_BAND_EDGES`.
    """
    profile = resolution.profile
    edges = hardness_edges if hardness_edges is not None else DEFAULT_BAND_EDGES
    empty = {
        'title': policy.slug,
        'subtitle': None,
        'entity_filter': None,
        'band_edges': None,
        'hardness_edges_source': None,
        'hardness_source_counts': None,
        'hardness_percentiles': None,
    }
    if policy.rotate:
        names = _ranked_names(profile.artists if policy.rotate == 'artist' else profile.labels)
        chosen = pick_daily_entity(username, clock.feed_date(now), names)
        noun = 'artiest' if policy.rotate == 'artist' else 'label'
        default_title = 'Artiestmix' if policy.rotate == 'artist' else 'Labelmix'
        return {
            **empty,
            'title': chosen or default_title,
            'subtitle': f'Een {noun} uit jouw top 10, elke dag een andere' if chosen else None,
            'entity_filter': (policy.rotate, chosen) if chosen else None,
        }
    if policy.hardness_band:
        title = DUTCH_BAND_TITLE.get(policy.hardness_band, policy.slug)
        if profile.scope == 'empty':
            return {**empty, 'title': title, 'band_edges': edges, 'hardness_edges_source': hardness_edges_source}
        percentiles, counts = _listener_hardness_stats(conn, resolution, now)
        return {
            **empty,
            'title': title,
            'subtitle': _band_subtitle(edges[0], edges[1], policy.hardness_band),
            'band_edges': edges,
            'hardness_edges_source': hardness_edges_source,
            'hardness_source_counts': counts,
            'hardness_percentiles': percentiles,
        }
    if policy.slug == 'release-radar':
        return {**empty, 'title': 'Release Radar'}
    if policy.slug == 'daily-mix':
        return {**empty, 'title': CLASSIC_TITLE, 'subtitle': 'De originele daily mix, ongefilterd op hardheid'}
    return empty


def describe_feed(
    conn,
    username: str,
    policy: FeedPolicy,
    now: datetime,
    starting_genres: list[str] | None = None,
    hardness_edges: tuple[float, float] | None = None,
    hardness_edges_source: str = 'default',
    resolution: ProfileResolution | None = None,
) -> dict:
    """`{'title', 'subtitle'}` for one policy, without running the candidate pipeline.

    `GET /api/feeds` needs this for every policy at once; running `build_feed` for
    each just to describe it would mean a full candidate query per policy on every
    listing. Still goes through `resolve_profile`, the one implementation of steps
    1-3, so the description is never a guess independent of what the listener would
    actually get -- but a caller describing several policies passes the one
    `resolution` it already has, since every policy shares `profile_window_days`
    and resolving it seven times was most of what a listing cost.
    """
    if resolution is None:
        resolution = resolve_profile(conn, username, policy.profile_window_days, now, starting_genres)
    info = _describe(conn, username, policy, now, resolution, hardness_edges, hardness_edges_source)
    return {'title': info['title'], 'subtitle': info['subtitle']}


def _load_band_candidates(
    conn, username: str, policy: FeedPolicy, now: datetime, info: dict
) -> tuple[list[dict], int | str | None]:
    """Step 4, plus the hardness-band relaxation ladder.

    For a plain policy (release-radar, the classic daily-mix, the two rotating
    mixes) this is one query at `policy.release_window_days`, exactly as before
    this feature existed. For a `hardness_band` policy, `release_window_days` is
    tried at 90, then 365, then not at all, stopping as soon as `MIN_BAND_CANDIDATES`
    is reached or the ladder runs out -- returning whichever window it stopped at,
    reported back as `relaxed_to` ('none' for "no window at all", never a bare
    `None`, which already means "no relaxation was needed" on that same field).
    """
    if not policy.hardness_band:
        plain_candidates = _load_candidates(conn, username, policy, now, entity_filter=info['entity_filter'])
        return plain_candidates, None

    lo, hi = info['band_edges']
    relaxed_to: int | str | None = None
    candidates: list[dict] = []
    for window in BAND_RELAXATION_WINDOWS:
        trial_policy = policy if window == policy.release_window_days else replace(policy, release_window_days=window)
        loaded = _load_candidates(conn, username, trial_policy, now, entity_filter=info['entity_filter'])
        _annotate_hardness(conn, loaded, id_field='id')
        candidates = [
            candidate
            for candidate in loaded
            if candidate.get('hardness') is not None
            and classify_band(candidate['hardness'], lo, hi) == policy.hardness_band
        ]
        if len(candidates) >= MIN_BAND_CANDIDATES or window == BAND_RELAXATION_WINDOWS[-1]:
            if window != policy.release_window_days:
                relaxed_to = 'none' if window is None else window
            break
    return candidates, relaxed_to


def _backfill_from_unknown(
    conn,
    username: str,
    policy: FeedPolicy,
    now: datetime,
    info: dict,
    emitted: list[dict],
    order_key,
) -> tuple[list[dict], int]:
    """A hardness_band mix's last resort, once steps 4-8 have run.

    The relaxation ladder above already tried every window looking for enough
    candidates *in this band*; if the result is still short of `policy.size`, a
    thin library is better served by a fuller mix of unknown hardness than by an
    honestly short (or empty) one. This is the one place any hardness_band feed
    emits a track whose hardness could not be resolved -- everywhere else it was
    excluded, not guessed into a bucket.

    Always re-fetches at `release_window_days=None` rather than reusing the
    relaxation ladder's own last candidate set: that ladder may have already
    stopped at window=90 because the band itself had enough candidates, and never
    collected an unknown-hardness pool wider than whichever window it settled on.
    The extra query only runs in the (rare) case a mix is still short after step 8,
    not on every hardness_band request.
    """
    if len(emitted) >= policy.size:
        return emitted, 0

    widest_policy = replace(policy, release_window_days=None)
    widest_candidates = _load_candidates(conn, username, widest_policy, now, entity_filter=info['entity_filter'])
    _annotate_hardness(conn, widest_candidates, id_field='id')
    # Keyed on the song, not the track id: this load is collapsed on its own, and when a
    # work's canonical has no file the version standing in for it can differ between the
    # two loads -- two ids, one song.
    already_emitted = {song_key(track) for track in emitted}
    unknown_candidates = [
        candidate
        for candidate in widest_candidates
        if candidate.get('hardness') is None and song_key(candidate) not in already_emitted
    ]
    if not unknown_candidates:
        return emitted, 0

    ordered_unknown = sorted(unknown_candidates, key=order_key)
    for candidate in ordered_unknown:
        candidate['bucket'] = '__unknown__'
        candidate['reason'] = 'unknown_hardness'
    combined = _cap_per_artist(emitted + ordered_unknown, policy.max_per_artist)[: policy.size]
    return combined, len(combined) - len(emitted)


def _dominant_genre_map(conn, dimension: str, names: list[str]) -> dict[str, str]:
    """Per-entity dominant genre, from the raw per-(name, genre) counts.

    `dominant_genre_query` groups by `(name, genre)` already; this collapses
    that into one genre per name, or drops the name when it has none.

    `names` bounds the aggregation to the entities this feed's candidates
    actually carry -- unbounded it is a full-library group-by, run twice, on
    every request. No names means nothing to ask about, and the query is
    skipped entirely rather than sent with an empty `IN ()`.
    """
    if not names:
        return {}
    counts: dict[str, Counter] = defaultdict(Counter)
    sql, params = dominant_genre_query(dimension, names)
    for row in _rows(conn, sql, params):
        counts[row['name'].lower()][row['genre'].lower()] += row['count']
    dominant = {}
    for name, genre_counts in counts.items():
        genre = dominant_genre(dict(genre_counts))
        if genre is not None:
            dominant[name] = genre
    return dominant


def _release_sort_key(candidate: dict) -> float:
    """Negated ordinal so ascending sort reads as release-date descending.

    A missing release date sorts last -- neither policy currently allows one
    through (both set `release_window_days`), but nothing here should crash if
    that ever changes.
    """
    release_date = candidate.get('release_date')
    if not release_date:
        return float('inf')
    try:
        return -datetime.strptime(release_date, '%Y-%m-%d').toordinal()
    except ValueError:
        return float('inf')


def _order_key_fn(policy: FeedPolicy, profile, username: str, feed_date):
    """The step-7 order, as a sort key: within a share for 'release', globally
    stable for 'daily_sample'."""
    if policy.order == 'daily_sample':

        def sample_key(candidate):
            weight = score(candidate, profile, policy)
            return daily_sample_key(username, feed_date, candidate['track_uid'], weight)

        return sample_key

    def release_key(candidate):
        heard_rank = int(candidate.get('heard', False)) if policy.heard_rank_penalty else 0
        return (heard_rank, _release_sort_key(candidate), -score(candidate, profile, policy))

    return release_key


def _cap_per_artist(tracks: list[dict], max_per_artist: int) -> list[dict]:
    """At most `max_per_artist` per primary artist.

    A track with no artist name is not one bucket with every other untagged
    track -- each partitions on its own id, so an unknown artist never gets
    capped alongside an unrelated one.
    """
    seen: dict = defaultdict(int)
    capped = []
    for track in tracks:
        artist = (track.get('artist') or '').strip().lower()
        key = artist if artist else ('__untagged__', track['id'])
        if seen[key] >= max_per_artist:
            continue
        seen[key] += 1
        capped.append(track)
    return capped


def resolve_profile(
    conn,
    username: str,
    window_days: int,
    now: datetime,
    starting_genres: list[str] | None = None,
) -> ProfileResolution:
    """Steps 1-3 of docs/designs/feeds/technical.md, for every caller of them.

    `build_feed`, `GET /api/feeds/profile` and `scripts/feeds_dryrun.py` all
    need this, and each used to carry its own copy. Three copies of a
    computation whose whole job is to explain a feed is three chances for the
    explanation and the feed to disagree, and they already had: the dry run's
    copy never applied `starting_genres`, so the one path the measurement tool
    existed to measure was the one it could not see.

    The returned profile's `scope` is authoritative: `'empty'` means neither
    this listener, nor the server, nor a configured fallback produced anything,
    and the caller decides what that means (for a feed, `not_enough_data`).
    """
    parents = _load_hierarchy(conn)
    exclusions = _load_exclusions(conn, username)

    # Step 1 + 2: this listener's profile, the server's, and the scope that
    # decides which one (or blend) the feed actually runs on. The server
    # profile only matters when blend() would actually consult it -- below
    # the ramp -- so a listener with a full profile of their own costs one
    # history query, not two.
    user_rows = _load_listens(conn, username, window_days, now)
    user_profile = build_profile(user_rows, parents, exclusions, now)
    if user_profile.distinct_tracks < RAMP_TRACKS:
        server_rows = _load_listens(conn, None, window_days, now)
        server_profile = build_profile(server_rows, parents, exclusions, now)
    else:
        server_profile = TasteProfile()
    profile = blend(user_profile, server_profile, ramp_tracks=RAMP_TRACKS)

    if profile.scope == 'empty' and starting_genres:
        # Nobody on the server has ever listened to anything either: fall back
        # to a configured taste rather than declaring not_enough_data, same
        # weight for every configured genre.
        profile = TasteProfile(
            genres=dict.fromkeys((genre.lower() for genre in starting_genres), 1.0),
            distinct_tracks=0,
            total_weight=0.0,
            scope='configured',
        )

    # Step 3: the shares this feed's places are divided over.
    return ProfileResolution(profile=profile, shares=genre_shares(profile, parents), parents=parents, listens=user_rows)


def build_feed(
    conn,
    username: str,
    policy: FeedPolicy,
    now: datetime,
    starting_genres: list[str] | None = None,
    hardness_edges: tuple[float, float] | None = None,
    hardness_edges_source: str = 'default',
) -> Feed:
    """The eight steps of technical.md's algorithm, in order.

    On exclusions: an exclusion removes an entity from the *profile* only. An
    excluded artist stops contributing weight, stops earning a share and stops
    scoring, but their tracks are not filtered out of the candidate set -- one
    can still be emitted, bucketed by its genre or by its label. That is the
    reading of functional criterion 10 ("removes its influence") this
    implements: the exclusion is about what the feed is built *from*, not a
    blocklist of what may appear in it. Both readings satisfy the criterion as
    written; if a listener ever needs the other one, it is a candidate-query
    filter and a second, differently-named control.

    `hardness_edges`/`hardness_edges_source` are the already-resolved
    `feeds_hardness_edges` setting -- see `_describe`'s docstring; `None` means "no
    override, use `hardness.DEFAULT_BAND_EDGES`".
    """
    resolution = resolve_profile(conn, username, policy.profile_window_days, now, starting_genres)
    profile, shares, parents = resolution.profile, resolution.shares, resolution.parents

    if profile.scope == 'empty':
        info = _describe(conn, username, policy, now, resolution, hardness_edges, hardness_edges_source)
        return Feed(
            slug=policy.slug,
            state='not_enough_data',
            scope='empty',
            tracks=[],
            funnel=dict(EMPTY_FUNNEL),
            title=info['title'],
            subtitle=info['subtitle'],
            hardness_band=info['band_edges'],
            hardness_edges_source=info['hardness_edges_source'],
        )

    # Which title/subtitle this response carries, and -- for the two rotating mixes
    # -- which artist or label today's build is restricted to; for the three
    # spectrum mixes, the band edges the candidate filter below actually applies.
    # One computation, shared with GET /api/feeds's cheap listing (`describe_feed`),
    # so the number on the home screen is always the number that was applied.
    info = _describe(conn, username, policy, now, resolution, hardness_edges, hardness_edges_source)
    if policy.rotate and info['entity_filter'] is None:
        # A profile with no artist (or label) affinities at all -- nothing to
        # rotate through today.
        return Feed(
            slug=policy.slug,
            state='not_enough_data',
            scope=profile.scope,
            tracks=[],
            funnel=dict(EMPTY_FUNNEL),
            title=info['title'],
            subtitle=info['subtitle'],
        )

    # Step 4: candidates, filtered entirely in SQL -- no window is ever widened here
    # for release-radar or a rotating mix, and an empty result is never backfilled.
    # A hardness-band mix is the one exception: its release window may be relaxed
    # below, in Python, once the band filter has had a chance to run against it.
    candidates, relaxed_to = _load_band_candidates(conn, username, policy, now, info)
    funnel = {'candidates': len(candidates)}

    # Step 5: which share each candidate competes in. The two dominant-genre
    # aggregations are asked only about the labels and artists these candidates
    # carry; over the whole library they are two unbounded group-bys per
    # request, for an answer about a few hundred names at most.
    label_genre = _dominant_genre_map(conn, 'label', _distinct(candidates, 'label'))
    artist_genre = _dominant_genre_map(conn, 'artist', _distinct(candidates, 'artist'))
    bucketed = [
        {**candidate, 'bucket': bucket, 'reason': reason}
        for candidate in candidates
        for bucket, reason in [bucket_of(candidate, shares, label_genre, artist_genre, parents)]
    ]
    funnel['bucketed'] = len(bucketed)

    order_key = _order_key_fn(policy, profile, username, clock.feed_date(now))

    if bucketed:
        # Step 6: how many places each share gets, capped by what is available.
        available = Counter(track['bucket'] for track in bucketed)
        allocation = redistribute(allocate(shares, policy.size), dict(available))
        funnel['allocated'] = sum(allocation.values())

        # Step 7: order within each share, then take that share's places.
        by_bucket: dict[str, list[dict]] = defaultdict(list)
        for track in bucketed:
            by_bucket[track['bucket']].append(track)

        selected = []
        for bucket, count in allocation.items():
            if count <= 0:
                continue
            ordered = sorted(by_bucket.get(bucket, []), key=order_key)
            selected.extend(ordered[:count])
        # Sorted twice on purpose. The per-bucket sort decides *which* tracks win
        # their share's places; this one decides what the listener reads first,
        # over the whole list -- newest release first for the radar, the daily
        # draw for the mix. Without it the feed comes out grouped by bucket, in
        # the arbitrary order the allocation dict happens to have.
        selected.sort(key=order_key)

        # Step 8: cap per artist, then the global size. The cap *removes*
        # tracks after their share was already allocated and filled, and the
        # freed places are not handed back to anyone -- so a feed can
        # legitimately come out shorter than policy.size. For release-radar and
        # the two rotating mixes that is the honest final answer: `capped`
        # below `allocated` in the funnel is exactly this, and nothing here is
        # backfilled with an unrelated track to hide it. A hardness_band policy
        # gets one more chance below, from candidates this pipeline never
        # considered at all.
        capped = _cap_per_artist(selected, policy.max_per_artist)
        funnel['capped'] = len(capped)
        # A guard, not a working limit: `allocate` hands out at most
        # policy.size places, `redistribute` never raises that total, the
        # per-bucket take is bounded by it and the artist cap only shrinks the
        # list, so `capped` is already no longer than policy.size. Kept
        # because it is the one line that makes "the API never returns more
        # than it asked for" independent of the quota's arithmetic staying
        # correct.
        emitted = capped[: policy.size]
    else:
        funnel.update(allocated=0, capped=0)
        emitted = []
    funnel['emitted'] = len(emitted)

    # A hardness_band mix's last resort: the relaxation loop above already tried
    # every window looking for enough candidates *in this band*; if the result is
    # still short of policy.size, a thin library is better served by a fuller mix
    # of unknown hardness than by an honestly short (or empty) one. This is the
    # one place any hardness_band feed emits a track whose hardness could not be
    # resolved -- everywhere else in this function such a track was excluded, not
    # guessed into a bucket.
    filled_from_unknown = None
    if policy.hardness_band:
        emitted, filled_from_unknown = _backfill_from_unknown(conn, username, policy, now, info, emitted, order_key)
        funnel['emitted'] = len(emitted)

    if not emitted:
        return Feed(
            slug=policy.slug,
            state='no_matches',
            scope=profile.scope,
            tracks=[],
            funnel=funnel,
            title=info['title'],
            subtitle=info['subtitle'],
            hardness_band=info['band_edges'],
            hardness_edges_source=info['hardness_edges_source'],
            hardness_source_counts=info['hardness_source_counts'],
            hardness_percentiles=info['hardness_percentiles'],
            relaxed_to=relaxed_to,
            filled_from_unknown=filled_from_unknown,
        )

    return Feed(
        slug=policy.slug,
        state='ok',
        scope=profile.scope,
        tracks=emitted,
        funnel=funnel,
        title=info['title'],
        subtitle=info['subtitle'],
        hardness_band=info['band_edges'],
        hardness_edges_source=info['hardness_edges_source'],
        hardness_source_counts=info['hardness_source_counts'],
        hardness_percentiles=info['hardness_percentiles'],
        relaxed_to=relaxed_to,
        filled_from_unknown=filled_from_unknown,
    )
