"""HTTP surface for the personalized feeds: the radar, the daily mix, the
listener's own taste profile, and the exclusions that shape it.

Auth is the canonical users.verify_api_key: a user key resolves its own
username and can never read or write anyone else's; the system key must say
whose feed it is asking for. See docs/designs/feeds/technical.md, "API
Contract", for the binding shape of every response below.
"""

import hashlib
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from services.common.config_store import ConfigStore as Settings
from services.music_manager.database import get_db_connection
from services.music_manager.feeds.build import (
    CLASSIC_TITLE,
    DUTCH_BAND_TITLE,
    build_feed,
    describe_feed,
    resolve_profile,
)
from services.music_manager.feeds.policy import (
    FEED_SIZE_SETTING,
    HARDNESS_EDGES_SETTING,
    POLICIES,
    STARTING_GENRES_SETTING,
    parse_feed_size,
    parse_hardness_edges,
    parse_starting_genres,
    resize,
)
from services.music_manager.feeds.queries import exclusions_query, genre_hardness_digest_query
from services.music_manager.feeds.snapshot import (
    LIST_SLUG,
)
from services.music_manager.feeds.snapshot import (
    delete_user as delete_user_snapshots,
)
from services.music_manager.feeds.snapshot import (
    extend as extend_snapshot,
)
from services.music_manager.feeds.snapshot import (
    serve as serve_snapshot,
)
from services.music_manager.identity import canonical_username
from services.music_manager.library_paths import relative_path
from services.music_manager.routers.users import verify_api_key

router = APIRouter(tags=['feeds'])
settings = Settings()

# Every policy currently agrees on this window (FeedPolicy's own default); the
# standalone profile view has no per-feed policy of its own to read it from.
PROFILE_WINDOW_DAYS = POLICIES['release-radar'].profile_window_days
# `list_body` resolves the profile once for every policy on the strength of that
# agreement; a policy that ever wanted its own window would silently be described
# from the wrong one, so the assumption fails at import rather than in a listing.
_disagreeing = [slug for slug, policy in POLICIES.items() if policy.profile_window_days != PROFILE_WINDOW_DAYS]
if _disagreeing:
    raise RuntimeError(f'feeds policies disagree on profile_window_days: {_disagreeing}')

# The fields /api/library/advanced already returns for a track, in the order
# the API Contract table documents them, plus the two fields a feed adds.
_TRACK_FIELDS = (
    'id',
    'title',
    'artist',
    'label',
    'genres',
    'duration_secs',
    'bpm',
    'release_date',
    'file_path',
)


def init_db(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS feeds_profile_exclusions (
            username    VARCHAR(255) NOT NULL,
            entity_type ENUM('artist', 'label', 'genre') NOT NULL,
            entity_name VARCHAR(255) NOT NULL,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (username, entity_type, entity_name)
        )
        """
    )


def _resolve_username(auth: dict, username: str | None) -> str:
    """A user key is always about its own account -- a `username` it passes is
    ignored, never honoured. Only the system key may ask for someone else's."""
    if auth.get('type') == 'system':
        if not username:
            raise HTTPException(status_code=400, detail='username is required for the system key')
        return _canonical(username)
    return auth['user']['username']


def _canonical(username: str) -> str:
    """The account's own spelling of a name the system key sent.

    The spelling is part of the feed, not just a lookup key: the daily picks are seeded on
    it (feeds/scoring.py), so "Teun" and "user" were two different mixes for one listener
    (docs/bug-reports/074-login-case-forks-user-identity.md). A database that does not
    answer leaves the name as sent -- the build that follows needs the database anyway.
    """
    conn = get_db_connection()
    if not conn:
        return username
    try:
        with conn.cursor() as cursor:
            return canonical_username(cursor, username) or username
    finally:
        conn.close()


def _starting_genres() -> list[str] | None:
    """The configured fallback genres, or None when nothing is configured."""
    return parse_starting_genres(settings.get(STARTING_GENRES_SETTING))


def _hardness_edges() -> tuple[tuple[float, float], str]:
    """The configured (soft/mid, mid/hard) band edges, and 'setting'|'default' for
    whether `feeds_hardness_edges` actually supplied them."""
    return parse_hardness_edges(settings.get(HARDNESS_EDGES_SETTING))


def _feed_size() -> int:
    """The configured feed length (`feeds_size`), or the default for anything unusable."""
    return parse_feed_size(settings.get(FEED_SIZE_SETTING))


def _sized(policy):
    """`policy` at the configured length -- every build goes through this, so the
    setting and not `FeedPolicy.size` decides how long a feed is."""
    return resize(policy, _feed_size())


#: The longest a feed's stored list grows to through continuations in one day:
#: five pages at the default length, at most four extra builds per feed per day.
MAX_FEED_LENGTH = 500


#: The snapshot slugs whose body depends on the curated per-genre hardness: the three
#: spectrum mixes, and the listing, whose subtitles describe them.
_HARDNESS_SLUGS = frozenset({LIST_SLUG, *(slug for slug, policy in POLICIES.items() if policy.hardness_band)})


def _genre_hardness_digest(conn) -> tuple:
    """`(scored genres, checksum)` over `rules_genres.hardness` -- changes on any edit."""
    with conn.cursor() as cursor:
        cursor.execute(genre_hardness_digest_query())
        row = cursor.fetchone() or {}
    return (int(row.get('genres') or 0), int(row.get('checksum') or 0))


def params_key(conn, username: str, slug: str) -> str:
    """A digest of everything a snapshot of `(username, slug)` is built under.

    Stored beside each snapshot; a snapshot whose key differs from the current one is
    stale whatever its age. It covers the settings (the hardness edges and the starting
    genres), for the spectrum mixes and the listing the curated per-genre hardness, and
    the listener's own exclusions -- so an admin who moves the edges, a curator who
    re-scores a genre and a listener who excludes an artist all see the change on the
    next read, not tomorrow. The exclusions are in here, and not only handled by
    `delete_user_snapshots`, because a build already running when the exclusion lands
    would otherwise write a row from the old ones that nothing ages. Callers compute
    the key *before* the build for the same reason. Anything new that shapes a build
    belongs in here.
    """
    edges, edges_source = _hardness_edges()
    exclusions = sorted((row['entity_type'], row['entity_name']) for row in _exclusion_rows(conn, username))
    hardness = _genre_hardness_digest(conn) if slug in _HARDNESS_SLUGS else None
    material = repr((sorted(_starting_genres() or []), edges, edges_source, exclusions, hardness, _feed_size()))
    return hashlib.sha256(material.encode('utf-8')).hexdigest()[:32]


def _track_view(track: dict) -> dict:
    view = {field: track.get(field) for field in _TRACK_FIELDS}
    # What a client hands to LMS's getSongsByPath to turn this into something playable. The
    # absolute `file_path` beside it is muma's own spelling (/mnt/music/...), which names a
    # file LMS does not have -- see library_paths.relative_path.
    view['library_path'] = relative_path(track.get('file_path'))
    view['bucket'] = track.get('bucket')
    view['reason'] = track.get('reason')
    # The song this track stands for (None for an ungrouped track): what a continuation
    # compares against, so "Meer laden" never repeats a song under another version's id.
    view['work_id'] = track.get('work_id')
    return view


def _rows(conn, sql: str, params=None) -> list[dict]:
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        return list(cursor.fetchall())


def _exclusion_rows(conn, username: str) -> list[dict]:
    sql, params = exclusions_query(username)
    return _rows(conn, sql, params)


def _affinities(values: dict[str, float]) -> list[dict]:
    return [
        {'name': name, 'affinity': affinity}
        for name, affinity in sorted(values.items(), key=lambda item: (-item[1], item[0]))
    ]


#: Every policy is listed, including the classic 'daily-mix' -- it is its own
#: policy now, not a duplicate of daily-mix-mid, so there is nothing to hide it
#: behind. Clients that already hardcode the slug need not read this list at all.
_LISTED_SLUGS = list(POLICIES)


def _fallback_title(policy) -> str:
    """A name for a feed with no listener in mind at all.

    Reached only when the caller is a system key that named no `username` -- there
    is no profile to resolve, so nothing here calls `describe_feed`, but the
    spectrum mixes' and the classic mix's Dutch names are static and do not need
    one either.
    """
    if policy.hardness_band:
        return DUTCH_BAND_TITLE.get(policy.hardness_band, policy.slug)
    if policy.rotate == 'artist':
        return 'Artiestmix'
    if policy.rotate == 'label':
        return 'Labelmix'
    if policy.slug == 'release-radar':
        return 'Release Radar'
    if policy.slug == 'daily-mix':
        return CLASSIC_TITLE
    return policy.slug


def list_body(conn, username: str | None, now: datetime) -> dict:
    """The `GET /api/feeds` body: every policy with a title and subtitle.

    One `resolve_profile` for all seven -- every policy shares `profile_window_days`,
    and resolving it per policy was most of what this listing cost. `conn` may be
    None only when there is no listener (`username` None): the titles then fall
    back to their generic spellings rather than the endpoint failing.
    """
    starting_genres = _starting_genres()
    edges, edges_source = _hardness_edges()
    size = _feed_size()
    resolution = None
    if conn and username:
        resolution = resolve_profile(conn, username, PROFILE_WINDOW_DAYS, now, starting_genres)
    feeds = []
    for slug in _LISTED_SLUGS:
        policy = POLICIES[slug]
        if resolution is not None:
            info = describe_feed(
                conn,
                username,
                policy,
                now,
                starting_genres,
                hardness_edges=edges,
                hardness_edges_source=edges_source,
                resolution=resolution,
            )
        else:
            info = {'title': _fallback_title(policy), 'subtitle': None}
        feeds.append(
            {
                'slug': policy.slug,
                'size': size,
                'window_days': policy.release_window_days,
                'title': info['title'],
                'subtitle': info['subtitle'],
            }
        )
    return {'feeds': feeds}


def feed_body(conn, username: str, policy, now: datetime) -> dict:
    """The `GET /api/feeds/{slug}` body for one policy, built live."""
    kwargs = {}
    starting_genres = _starting_genres()
    if starting_genres:
        kwargs['starting_genres'] = starting_genres
    if policy.hardness_band:
        edges, edges_source = _hardness_edges()
        kwargs['hardness_edges'] = edges
        kwargs['hardness_edges_source'] = edges_source

    feed = build_feed(conn, username, policy, now, **kwargs)
    return {
        'slug': feed.slug,
        'state': feed.state,
        'scope': feed.scope,
        'generated_at': now.isoformat(),
        'tracks': [_track_view(track) for track in feed.tracks] if feed.state == 'ok' else [],
        'funnel': feed.funnel,
        'title': feed.title,
        'subtitle': feed.subtitle,
        'hardness_band': list(feed.hardness_band) if feed.hardness_band else None,
        'hardness_edges_source': feed.hardness_edges_source,
        'hardness_source_counts': feed.hardness_source_counts,
        'hardness_percentiles': feed.hardness_percentiles,
        'relaxed_to': feed.relaxed_to,
        'filled_from_unknown': feed.filled_from_unknown,
        # Stored, never sent (`get_feed` strips it): whether a bigger build could find more.
        'exhausted': _ran_out(feed.tracks, feed.funnel, policy.size),
    }


def _ran_out(tracks: list, funnel: dict, size: int) -> bool:
    """Whether a build used every candidate it had: it came out short of `size` and the
    quota could not even hand out `size` places. Short only because the per-artist cap
    removed a few is not running out -- a bigger build may still find more -- so that
    feed stays continuable. Saves the continuation build (up to ~20 s) that would only
    find out the same thing."""
    return len(tracks) < size and int(funnel.get('allocated') or 0) < size


def snapshot_body(conn, username: str, slug: str) -> dict:
    """What the `feeds-refresh` thread stores for one key: the listing for
    `LIST_SLUG`, the full-size feed for a policy slug. Same functions the request
    path uses, so a warm row and a live answer can never differ."""
    now = datetime.now()
    if slug == LIST_SLUG:
        return list_body(conn, username, now)
    return feed_body(conn, username, _sized(POLICIES[slug]), now)


#: Every key the refresh thread keeps warm per listener.
SNAPSHOT_SLUGS = [LIST_SLUG, *_LISTED_SLUGS]


@router.get('')
@router.get('/')
def list_feeds(response: Response, username: str | None = None, auth: dict = Depends(verify_api_key)):
    """Every feed slug this caller may ask for, with a title and subtitle to show
    before it has even been built.

    A system key may look this up for a specific listener via `?username=`, the same
    optional-but-honoured parameter `GET /api/feeds/{slug}` requires; without one
    (or for a user key, always its own) the title/subtitle for the personalised
    slugs -- the rotating artist/label mixes, the spectrum's actual hardness numbers
    -- fall back to a generic description rather than failing the whole listing.

    Answered from the day's snapshot when there is one; `X-MuMa-Feed-Source` says
    which it was.
    """
    resolved = username if auth.get('type') == 'system' else auth['user']['username']

    conn = get_db_connection() if resolved else None
    now = datetime.now()
    try:
        if not conn:
            body, source = list_body(None, None, now), 'live'
        else:
            body, source = serve_snapshot(
                conn,
                resolved,
                LIST_SLUG,
                now,
                params_key(conn, resolved, LIST_SLUG),
                lambda: list_body(conn, resolved, now),
            )
    finally:
        if conn:
            conn.close()
    response.headers['X-MuMa-Feed-Source'] = source
    return body


@router.get('/profile')
def get_profile(username: str | None = None, auth: dict = Depends(verify_api_key)):
    resolved = _resolve_username(auth, username)
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        excluded = _exclusion_rows(conn, resolved)
        # The same resolution build_feed runs, so what this reports always
        # explains the feed the listener actually gets.
        profile = resolve_profile(conn, resolved, PROFILE_WINDOW_DAYS, datetime.now(), _starting_genres()).profile
    finally:
        conn.close()
    return {
        'scope': profile.scope,
        'distinct_tracks': profile.distinct_tracks,
        'artists': _affinities(profile.artists),
        'labels': _affinities(profile.labels),
        'genres': _affinities(profile.genres),
        'excluded': [{'entity_type': row['entity_type'], 'entity_name': row['entity_name']} for row in excluded],
    }


class ExclusionUpdate(BaseModel):
    entity_type: Literal['artist', 'label', 'genre']
    entity_name: str
    excluded: bool


@router.put('/profile/exclusions')
def update_exclusion(payload: ExclusionUpdate, username: str | None = None, auth: dict = Depends(verify_api_key)):
    resolved = _resolve_username(auth, username)
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    entity_name = payload.entity_name.strip().lower()
    try:
        with conn.cursor() as cursor:
            if payload.excluded:
                cursor.execute(
                    'INSERT IGNORE INTO feeds_profile_exclusions (username, entity_type, entity_name) '
                    'VALUES (%s, %s, %s)',
                    (resolved, payload.entity_type, entity_name),
                )
            else:
                cursor.execute(
                    'DELETE FROM feeds_profile_exclusions '
                    'WHERE username = %s AND entity_type = %s AND entity_name = %s',
                    (resolved, payload.entity_type, entity_name),
                )
        conn.commit()
        # The snapshots were built from a profile this exclusion has just changed;
        # the next read rebuilds rather than serving a mix the entity still shapes.
        delete_user_snapshots(conn, resolved)
    finally:
        conn.close()
    return {'status': 'ok'}


def _can_grow(body: dict) -> bool:
    """Whether a stored feed may still be continued: built `ok`, not yet found
    exhausted, and short of `MAX_FEED_LENGTH`."""
    return body.get('state') == 'ok' and not body.get('exhausted') and len(body.get('tracks') or []) < MAX_FEED_LENGTH


def continuation(conn, username: str, policy, now: datetime, stored: dict, wanted: int) -> dict | None:
    """`stored` grown to at least `wanted` tracks where the feed allows, or None for no change.

    docs/designs/feed-length/technical.md, "Continuation". The feed is built again with
    more places -- the same ranker, profile, exclusions, quota and per-song collapse -- and
    every track whose song is already stored is dropped; what is left is appended in the
    build's order. A superset build rather than "the rest of the first build" because the
    quota is allocated over the number of places: a 200-place feed is not a 100-place feed
    with 100 appended, and filtering by song keeps the first page exactly as it was.

    A build that ran out of candidates (`_ran_out`), or found nothing new, marks the result
    `exhausted`, and nothing will try again today.
    """
    tracks = list(stored.get('tracks') or [])
    if not _can_grow(stored) or len(tracks) >= wanted:
        return None
    target = min(MAX_FEED_LENGTH, len(tracks) + max(policy.size, wanted - len(tracks)))
    built = feed_body(conn, username, resize(policy, target), now)
    # Both the song and the track id: a row stored before `work_id` was part of a track has
    # only the id to go on.
    seen_ids = {track.get('id') for track in tracks}
    seen_works = {track['work_id'] for track in tracks if track.get('work_id')}
    fresh = []
    for track in built.get('tracks') or []:
        work_id = track.get('work_id')
        if track.get('id') in seen_ids or (work_id and work_id in seen_works):
            continue
        seen_ids.add(track.get('id'))
        if work_id:
            seen_works.add(work_id)
        fresh.append(track)
    exhausted = not fresh or bool(built.get('exhausted'))
    return {**stored, 'tracks': tracks + fresh, 'exhausted': exhausted}


@router.get('/{slug}')
def get_feed(
    slug: str,
    response: Response,
    offset: int = Query(0, ge=0),
    limit: int | None = Query(None, ge=1, le=100),
    username: str | None = None,
    auth: dict = Depends(verify_api_key),
):
    """One page of a feed, from the day's snapshot when it is fresh, built live when it is not.

    Without `offset` this is what it always was: `limit` takes the head of the stored list
    -- the Home row is literally the top of the page it links to -- and no `limit` returns
    the whole stored list, the configured length (`feeds_size`) until it is continued.

    `offset` is "Meer laden": the window `[offset, offset + limit)` of the same day's list,
    `limit` defaulting to the configured length. A window past the stored list continues
    it (`continuation`), stored under the snapshot's lock, so the same page asked twice on
    one day holds the same tracks and no song repeats. `next_offset` is where the next page
    starts, or null when the feed has nothing more to give.
    """
    policy = POLICIES.get(slug)
    if policy is None:
        raise HTTPException(status_code=404, detail='Unknown feed')
    policy = _sized(policy)
    resolved = _resolve_username(auth, username)
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')

    now = datetime.now()
    try:
        key = params_key(conn, resolved, slug)
        body, source = serve_snapshot(conn, resolved, slug, now, key, lambda: feed_body(conn, resolved, policy, now))
        stored = len(body.get('tracks') or [])
        # No `limit`: the whole stored list for the head, one configured length for a later page.
        default_page = stored if offset == 0 else policy.size
        page = limit if limit is not None else default_page
        end = offset + page
        if end > stored and _can_grow(body):
            grown = extend_snapshot(
                conn,
                resolved,
                slug,
                now,
                key,
                lambda current: continuation(conn, resolved, policy, now, current, end),
            )
            if grown is not None:
                body, source = grown, 'extended'
    finally:
        conn.close()

    tracks = body.get('tracks') or []
    more = end < len(tracks) or _can_grow(body)
    body = {key_: value for key_, value in body.items() if key_ != 'exhausted'}
    body['tracks'] = tracks[offset:end]
    body['offset'] = offset
    body['next_offset'] = end if more else None
    response.headers['X-MuMa-Feed-Source'] = source
    return body
