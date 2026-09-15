"""HTTP surface for the personalized feeds: the radar, the daily mix, the
listener's own taste profile, and the exclusions that shape it.

Auth mirrors routers/library.py's verify_api_key: a user key resolves its own
username and can never read or write anyone else's; the system key must say
whose feed it is asking for. See docs/designs/feeds/technical.md, "API
Contract", for the binding shape of every response below.
"""

from dataclasses import replace
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from services.common.config_store import ConfigStore as Settings
from services.music_manager.api_key import is_system_api_key
from services.music_manager.database import get_db_connection
from services.music_manager.feeds.build import DUTCH_BAND_TITLE, build_feed, describe_feed, resolve_profile
from services.music_manager.feeds.policy import POLICIES, STARTING_GENRES_SETTING, parse_starting_genres
from services.music_manager.feeds.queries import exclusions_query
from services.music_manager.library_paths import relative_path

router = APIRouter(tags=['feeds'])
settings = Settings()

# Every policy currently agrees on this window (FeedPolicy's own default); the
# standalone profile view has no per-feed policy of its own to read it from.
PROFILE_WINDOW_DAYS = POLICIES['release-radar'].profile_window_days

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


def verify_api_key(x_api_key: str | None = Header(None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail='Missing API Key')
    if is_system_api_key(x_api_key):
        return {'type': 'system'}
    from services.music_manager.routers.users import verify_token

    try:
        res = verify_token(x_api_key)
        if res.get('status') == 'ok':
            return res
    except Exception:
        pass
    raise HTTPException(status_code=401, detail='Invalid API key')


def _resolve_username(auth: dict, username: str | None) -> str:
    """A user key is always about its own account -- a `username` it passes is
    ignored, never honoured. Only the system key may ask for someone else's."""
    if auth.get('type') == 'system':
        if not username:
            raise HTTPException(status_code=400, detail='username is required for the system key')
        return username
    return auth['user']['username']


def _starting_genres() -> list[str] | None:
    """The configured fallback genres, or None when nothing is configured."""
    return parse_starting_genres(settings.get(STARTING_GENRES_SETTING))


def _track_view(track: dict) -> dict:
    view = {field: track.get(field) for field in _TRACK_FIELDS}
    # What a client hands to LMS's getSongsByPath to turn this into something playable. The
    # absolute `file_path` beside it is muma's own spelling (/mnt/music/...), which names a
    # file LMS does not have -- see library_paths.relative_path.
    view['library_path'] = relative_path(track.get('file_path'))
    view['bucket'] = track.get('bucket')
    view['reason'] = track.get('reason')
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


#: The alias for daily-mix-mid is not offered here, so a client discovering feeds
#: never sees the same mix described twice under two names -- it stays reachable
#: at /api/feeds/daily-mix because the car and the phone already hardcode that slug.
_LISTED_SLUGS = [slug for slug in POLICIES if slug != 'daily-mix']


def _fallback_title(policy) -> str:
    """A name for a feed with no listener in mind at all.

    Reached only when the caller is a system key that named no `username` -- there
    is no profile to resolve, so nothing here calls `describe_feed`, but the three
    spectrum mixes' Dutch names are static and do not need one either.
    """
    if policy.hardness_band:
        return DUTCH_BAND_TITLE.get(policy.hardness_band, policy.slug)
    if policy.rotate == 'artist':
        return 'Artiestmix'
    if policy.rotate == 'label':
        return 'Labelmix'
    if policy.slug == 'release-radar':
        return 'Release Radar'
    return policy.slug


@router.get('')
@router.get('/')
def list_feeds(username: str | None = None, auth: dict = Depends(verify_api_key)):
    """Every feed slug this caller may ask for, with a title and subtitle to show
    before it has even been built.

    A system key may look this up for a specific listener via `?username=`, the same
    optional-but-honoured parameter `GET /api/feeds/{slug}` requires; without one
    (or for a user key, always its own) the title/subtitle for the personalised
    slugs -- the rotating artist/label mixes, the spectrum's actual hardness numbers
    -- fall back to a generic description rather than failing the whole listing.
    """
    resolved = username if auth.get('type') == 'system' else auth['user']['username']

    conn = get_db_connection() if resolved else None
    starting_genres = _starting_genres()
    now = datetime.now()
    feeds = []
    try:
        for slug in _LISTED_SLUGS:
            policy = POLICIES[slug]
            if conn:
                info = describe_feed(conn, resolved, policy, now, starting_genres)
            else:
                info = {'title': _fallback_title(policy), 'subtitle': None}
            feeds.append(
                {
                    'slug': policy.slug,
                    'size': policy.size,
                    'window_days': policy.release_window_days,
                    'title': info['title'],
                    'subtitle': info['subtitle'],
                }
            )
    finally:
        if conn:
            conn.close()
    return {'feeds': feeds}


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
    finally:
        conn.close()
    return {'status': 'ok'}


@router.get('/{slug}')
def get_feed(
    slug: str,
    limit: int | None = Query(None, ge=1, le=100),
    username: str | None = None,
    auth: dict = Depends(verify_api_key),
):
    policy = POLICIES.get(slug)
    if policy is None:
        raise HTTPException(status_code=404, detail='Unknown feed')
    resolved = _resolve_username(auth, username)
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')

    try:
        if limit is not None and limit != policy.size:
            policy = replace(policy, size=limit)

        kwargs = {}
        starting_genres = _starting_genres()
        if starting_genres:
            kwargs['starting_genres'] = starting_genres

        now = datetime.now()
        feed = build_feed(conn, resolved, policy, now, **kwargs)
    finally:
        conn.close()

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
        'hardness_source_counts': feed.hardness_source_counts,
        'relaxed_to': feed.relaxed_to,
    }
