"""Orchestration: profile -> candidates -> buckets -> quota -> ordered feed.

The only module in `feeds/` that touches a database connection -- every other
module works over plain rows so it can be unit tested without one (see
scripted_cursor.py and test_feeds_build.py). `build_feed` runs the eight steps
from docs/designs/feeds/technical.md, "Algorithm, in the order build_feed runs
it", in order, recording the funnel after each stage that can shrink the set:
`candidates`, `bucketed`, `allocated`, `capped`, `emitted`.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import datetime

from services.music_manager.feeds.buckets import bucket_of, dominant_genre
from services.music_manager.feeds.hardness import classify_band, hardness_band_edges, track_hardness
from services.music_manager.feeds.policy import FeedPolicy
from services.music_manager.feeds.profile import TasteProfile, blend, build_profile, genre_shares, listen_weight
from services.music_manager.feeds.queries import (
    candidates_query,
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
    slug: str
    state: str  # 'ok' | 'no_matches' | 'not_enough_data'
    scope: str
    tracks: list[dict]
    funnel: dict[str, int]
    # Dutch, client-facing: what the home screen shows for this feed. None for
    # release-radar and the alias 'daily-mix', which have no per-request identity
    # of their own to describe.
    title: str | None = None
    subtitle: str | None = None
    # Only set for a hardness_band policy: the (soft/mid, mid/hard) edges this
    # listener's own build actually filtered against.
    hardness_band: tuple[float, float] | None = None
    # Only set for a hardness_band policy: how many of this listener's heard tracks
    # resolved their hardness from each source ('genre', 'label', 'artist', 'tempo',
    # 'none'), for the dry run and for judging how much the fallback chain matters.
    hardness_source_counts: dict[str, int] | None = None
    # Only set when a hardness band came up short and release_window_days was
    # widened to reach MIN_BAND_CANDIDATES: the number of days it was widened to,
    # the literal string 'none' when it was widened all the way to no window at
    # all, or None (the default) when no relaxation was needed. A bare `None` would
    # be ambiguous between those last two -- release_window_days=None already means
    # "no window" everywhere else in this package.
    relaxed_to: int | str | None = None


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

    @property
    def scope(self) -> str:
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
    return dict(parents)


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
    sql, params = candidates_query(username, policy, now, entity_filter=entity_filter)
    candidates = []
    for row in _rows(conn, sql, params):
        label = row.get('label')
        candidates.append(
            {
                **row,
                'genres': _split(row.get('genres')),
                'labels': [label] if label else [],
                'heard': bool(row.get('heard')),
            }
        )
    return candidates


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


def _listener_band_edges(
    conn, username: str, window_days: int, now: datetime
) -> tuple[tuple[float, float], dict[str, int]]:
    """This listener's own (soft/mid, mid/hard) hardness edges, and the source tally.

    Reads the same listens `build_profile` does (`_load_listens`, same window), so
    the number a listener sees on the daily mix ("<= 42 hardheid") is measured from
    exactly the history their profile is built from, never a second, differently
    windowed read of `scrobble_listens`.
    """
    rows = _load_listens(conn, username, window_days, now)
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
    return hardness_band_edges(weighted), dict(source_counts)


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


def _describe(conn, username: str, policy: FeedPolicy, now: datetime, profile: TasteProfile) -> dict:
    """title/subtitle/entity_filter/band_edges/hardness_source_counts for one policy.

    The one place both `describe_feed` (the cheap version `GET /api/feeds` uses to
    list what is available) and `build_feed` (which needs the same numbers anyway,
    to actually filter candidates) compute a feed's identity -- so the edges a
    listener is told about are always the edges that were applied, never a second,
    possibly different pass over the same profile.
    """
    empty = {
        'title': policy.slug,
        'subtitle': None,
        'entity_filter': None,
        'band_edges': None,
        'hardness_source_counts': None,
    }
    if policy.rotate:
        names = _ranked_names(profile.artists if policy.rotate == 'artist' else profile.labels)
        chosen = pick_daily_entity(username, now.date(), names)
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
            return {**empty, 'title': title}
        edges, counts = _listener_band_edges(conn, username, policy.profile_window_days, now)
        return {
            **empty,
            'title': title,
            'subtitle': _band_subtitle(edges[0], edges[1], policy.hardness_band),
            'band_edges': edges,
            'hardness_source_counts': counts,
        }
    if policy.slug == 'release-radar':
        return {**empty, 'title': 'Release Radar'}
    return empty


def describe_feed(
    conn, username: str, policy: FeedPolicy, now: datetime, starting_genres: list[str] | None = None
) -> dict:
    """`{'title', 'subtitle'}` for one policy, without running the candidate pipeline.

    `GET /api/feeds` needs this for every policy at once; running `build_feed` for
    each just to describe it would mean a full candidate query per policy on every
    listing. Still calls `resolve_profile`, the one implementation of steps 1-3, so
    the description is never a guess independent of what the listener would actually
    get.
    """
    resolution = resolve_profile(conn, username, policy.profile_window_days, now, starting_genres)
    info = _describe(conn, username, policy, now, resolution.profile)
    return {'title': info['title'], 'subtitle': info['subtitle']}


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
    return ProfileResolution(profile=profile, shares=genre_shares(profile, parents), parents=parents)


def build_feed(
    conn, username: str, policy: FeedPolicy, now: datetime, starting_genres: list[str] | None = None
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
    """
    resolution = resolve_profile(conn, username, policy.profile_window_days, now, starting_genres)
    profile, shares, parents = resolution.profile, resolution.shares, resolution.parents

    if profile.scope == 'empty':
        info = _describe(conn, username, policy, now, profile)
        return Feed(
            slug=policy.slug,
            state='not_enough_data',
            scope='empty',
            tracks=[],
            funnel=dict(EMPTY_FUNNEL),
            title=info['title'],
            subtitle=info['subtitle'],
        )

    # Which title/subtitle this response carries, and -- for the two rotating mixes
    # -- which artist or label today's build is restricted to; for the three
    # spectrum mixes, the band edges the candidate filter below actually applies.
    # One computation, shared with GET /api/feeds's cheap listing (`describe_feed`),
    # so the number on the home screen is always the number that was applied.
    info = _describe(conn, username, policy, now, profile)
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
    relaxed_to = None
    windows = BAND_RELAXATION_WINDOWS if policy.hardness_band else (policy.release_window_days,)
    candidates: list[dict] = []
    for window in windows:
        trial_policy = policy if window == policy.release_window_days else replace(policy, release_window_days=window)
        candidates = _load_candidates(conn, username, trial_policy, now, entity_filter=info['entity_filter'])
        if policy.hardness_band:
            _annotate_hardness(conn, candidates, id_field='id')
            lo, hi = info['band_edges']
            candidates = [
                candidate
                for candidate in candidates
                if candidate.get('hardness') is not None
                and classify_band(candidate['hardness'], lo, hi) == policy.hardness_band
            ]
        if not policy.hardness_band or len(candidates) >= MIN_BAND_CANDIDATES or window == windows[-1]:
            if policy.hardness_band and window != policy.release_window_days:
                relaxed_to = 'none' if window is None else window
            break
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

    if not bucketed:
        funnel.update(allocated=0, capped=0, emitted=0)
        return Feed(
            slug=policy.slug,
            state='no_matches',
            scope=profile.scope,
            tracks=[],
            funnel=funnel,
            title=info['title'],
            subtitle=info['subtitle'],
            hardness_band=info['band_edges'],
            hardness_source_counts=info['hardness_source_counts'],
            relaxed_to=relaxed_to,
        )

    # Step 6: how many places each share gets, capped by what is available.
    available = Counter(track['bucket'] for track in bucketed)
    allocation = redistribute(allocate(shares, policy.size), dict(available))
    funnel['allocated'] = sum(allocation.values())

    # Step 7: order within each share, then take that share's places.
    by_bucket: dict[str, list[dict]] = defaultdict(list)
    for track in bucketed:
        by_bucket[track['bucket']].append(track)

    order_key = _order_key_fn(policy, profile, username, now.date())
    selected = []
    for bucket, count in allocation.items():
        if count <= 0:
            continue
        ordered = sorted(by_bucket.get(bucket, []), key=order_key)
        selected.extend(ordered[:count])
    # Sorted twice on purpose. The per-bucket sort decides *which* tracks win
    # their share's places; this one decides what the listener reads first, over
    # the whole list -- newest release first for the radar, the daily draw for
    # the mix. Without it the feed comes out grouped by bucket, in the arbitrary
    # order the allocation dict happens to have.
    selected.sort(key=order_key)

    # Step 8: cap per artist, then the global size. The cap *removes* tracks
    # after their share was already allocated and filled, and the freed places
    # are not handed back to anyone -- so a feed can legitimately come out
    # shorter than policy.size. That is the honest outcome and the funnel says
    # so: `capped` below `allocated` is exactly this, and nothing is
    # backfilled with an unrelated track to hide it.
    capped = _cap_per_artist(selected, policy.max_per_artist)
    funnel['capped'] = len(capped)
    # A guard, not a working limit: `allocate` hands out at most policy.size
    # places, `redistribute` never raises that total, the per-bucket take is
    # bounded by it and the artist cap only shrinks the list, so `capped` is
    # already no longer than policy.size. Kept because it is the one line that
    # makes "the API never returns more than it asked for" independent of the
    # quota's arithmetic staying correct.
    emitted = capped[: policy.size]
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
            hardness_source_counts=info['hardness_source_counts'],
            relaxed_to=relaxed_to,
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
        hardness_source_counts=info['hardness_source_counts'],
        relaxed_to=relaxed_to,
    )
