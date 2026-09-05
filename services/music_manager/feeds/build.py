"""Orchestration: profile -> candidates -> buckets -> quota -> ordered feed.

The only module in `feeds/` that touches a database connection -- every other
module works over plain rows so it can be unit tested without one (see
scripted_cursor.py and test_feeds_build.py). `build_feed` runs the eight steps
from docs/designs/feeds/technical.md, "Algorithm, in the order build_feed runs
it", in order, recording the funnel after each stage that can shrink the set:
`candidates`, `bucketed`, `allocated`, `capped`, `emitted`.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime

from services.music_manager.feeds.buckets import bucket_of, dominant_genre
from services.music_manager.feeds.policy import FeedPolicy
from services.music_manager.feeds.profile import TasteProfile, blend, build_profile, genre_shares
from services.music_manager.feeds.queries import (
    candidates_query,
    dominant_genre_query,
    exclusions_query,
    hierarchy_query,
    listens_query,
)
from services.music_manager.feeds.quota import allocate, redistribute
from services.music_manager.feeds.scoring import daily_sample_key, score

EMPTY_FUNNEL = {'candidates': 0, 'bucketed': 0, 'allocated': 0, 'capped': 0, 'emitted': 0}

# Mirrors blend()'s own default. Kept as one constant and passed explicitly to
# blend() below so the pre-check that decides whether to bother querying the
# server at all can never drift from the value blend() actually uses.
RAMP_TRACKS = 30


@dataclass
class Feed:
    slug: str
    state: str  # 'ok' | 'no_matches' | 'not_enough_data'
    scope: str
    tracks: list
    funnel: dict


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


def _load_candidates(conn, username: str, policy: FeedPolicy, now: datetime) -> list[dict]:
    sql, params = candidates_query(username, policy, now)
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

        def key(candidate):
            weight = score(candidate, profile, policy)
            return daily_sample_key(username, feed_date, candidate['track_uid'], weight)

        return key

    def key(candidate):
        heard_rank = int(candidate.get('heard', False)) if policy.heard_rank_penalty else 0
        return (heard_rank, _release_sort_key(candidate), -score(candidate, profile, policy))

    return key


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


def build_feed(
    conn, username: str, policy: FeedPolicy, now: datetime, starting_genres: list[str] | None = None
) -> Feed:
    parents = _load_hierarchy(conn)
    exclusions = _load_exclusions(conn, username)

    # Step 1 + 2: this listener's profile, the server's, and the scope that
    # decides which one (or blend) the feed actually runs on. The server
    # profile only matters when blend() would actually consult it -- below
    # the ramp -- so a listener with a full profile of their own costs one
    # history query, not two.
    user_rows = _load_listens(conn, username, policy.profile_window_days, now)
    user_profile = build_profile(user_rows, parents, exclusions, now)
    if user_profile.distinct_tracks < RAMP_TRACKS:
        server_rows = _load_listens(conn, None, policy.profile_window_days, now)
        server_profile = build_profile(server_rows, parents, exclusions, now)
    else:
        server_profile = TasteProfile()
    profile = blend(user_profile, server_profile, ramp_tracks=RAMP_TRACKS)

    if profile.scope == 'empty':
        if not starting_genres:
            return Feed(slug=policy.slug, state='not_enough_data', scope='empty', tracks=[], funnel=dict(EMPTY_FUNNEL))
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
    shares = genre_shares(profile, parents)

    # Step 4: candidates, filtered entirely in SQL -- no window is ever
    # widened here, and an empty result is never backfilled.
    candidates = _load_candidates(conn, username, policy, now)
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
        return Feed(slug=policy.slug, state='no_matches', scope=profile.scope, tracks=[], funnel=funnel)

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
    selected.sort(key=order_key)

    # Step 8: cap per artist, then the global size.
    capped = _cap_per_artist(selected, policy.max_per_artist)
    funnel['capped'] = len(capped)
    emitted = capped[: policy.size]
    funnel['emitted'] = len(emitted)

    if not emitted:
        return Feed(slug=policy.slug, state='no_matches', scope=profile.scope, tracks=[], funnel=funnel)

    return Feed(slug=policy.slug, state='ok', scope=profile.scope, tracks=emitted, funnel=funnel)
