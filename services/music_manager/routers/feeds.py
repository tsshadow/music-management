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
from services.music_manager.feeds.build import RAMP_TRACKS, build_feed
from services.music_manager.feeds.policy import POLICIES
from services.music_manager.feeds.profile import TasteProfile, blend, build_profile
from services.music_manager.feeds.queries import exclusions_query, hierarchy_query, listens_query

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


def _auth_dependency(x_api_key: str | None = Header(None)) -> dict:
    """Indirection so `Depends` re-reads `verify_api_key` from this module's
    namespace on every request, the same way `verify_api_key` itself re-reads
    `verify_token` -- tests patch the module attribute, not the object FastAPI
    would otherwise have captured once at route-registration time."""
    return verify_api_key(x_api_key)


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
    raw = settings.get('feeds_starting_genres') or ''
    genres = [genre.strip() for genre in raw.split(',') if genre.strip()]
    return genres or None


def _track_view(track: dict) -> dict:
    view = {field: track.get(field) for field in _TRACK_FIELDS}
    view['bucket'] = track.get('bucket')
    view['reason'] = track.get('reason')
    return view


def _split(csv: str | None) -> list[str]:
    return [part for part in (csv or '').split(',') if part]


def _rows(conn, sql: str, params=None) -> list[dict]:
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        return list(cursor.fetchall())


def _hierarchy(conn) -> dict[str, set[str]]:
    parents: dict[str, set[str]] = {}
    for row in _rows(conn, hierarchy_query()):
        parents.setdefault(row['subgenre'].lower(), set()).add(row['genre'].lower())
    return parents


def _exclusion_rows(conn, username: str) -> list[dict]:
    sql, params = exclusions_query(username)
    return _rows(conn, sql, params)


def _exclusions(conn, username: str) -> dict[str, set[str]]:
    exclusions: dict[str, set[str]] = {'artist': set(), 'label': set(), 'genre': set()}
    for row in _exclusion_rows(conn, username):
        exclusions.setdefault(row['entity_type'], set()).add(row['entity_name'].lower())
    return exclusions


def _listens(conn, username: str | None, window_days: int, now: datetime) -> list[dict]:
    sql, params = listens_query(username, window_days, now)
    return [
        {**row, 'labels': _split(row.get('labels')), 'genres': _split(row.get('genres'))}
        for row in _rows(conn, sql, params)
    ]


def _taste_profile(conn, username: str, now: datetime, starting_genres: list[str] | None) -> TasteProfile:
    """The listener's blended taste, resolved the same way build_feed resolves
    it (docs/designs/feeds/technical.md, Algorithm steps 1-2) so that what
    /api/feeds/profile reports always explains the feed the listener actually
    sees."""
    parents = _hierarchy(conn)
    exclusions = _exclusions(conn, username)
    user_rows = _listens(conn, username, PROFILE_WINDOW_DAYS, now)
    user_profile = build_profile(user_rows, parents, exclusions, now)
    if user_profile.distinct_tracks < RAMP_TRACKS:
        server_rows = _listens(conn, None, PROFILE_WINDOW_DAYS, now)
        server_profile = build_profile(server_rows, parents, exclusions, now)
    else:
        server_profile = TasteProfile()
    profile = blend(user_profile, server_profile, ramp_tracks=RAMP_TRACKS)
    if profile.scope == 'empty' and starting_genres:
        profile = TasteProfile(
            genres=dict.fromkeys((genre.lower() for genre in starting_genres), 1.0),
            distinct_tracks=0,
            total_weight=0.0,
            scope='configured',
        )
    return profile


def _affinities(values: dict[str, float]) -> list[dict]:
    return [
        {'name': name, 'affinity': affinity}
        for name, affinity in sorted(values.items(), key=lambda item: (-item[1], item[0]))
    ]


@router.get('')
@router.get('/')
def list_feeds(_auth: dict = Depends(_auth_dependency)):
    return {
        'feeds': [
            {'slug': policy.slug, 'size': policy.size, 'window_days': policy.release_window_days}
            for policy in POLICIES.values()
        ]
    }


@router.get('/profile')
def get_profile(username: str | None = None, auth: dict = Depends(_auth_dependency)):
    resolved = _resolve_username(auth, username)
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        excluded = _exclusion_rows(conn, resolved)
        profile = _taste_profile(conn, resolved, datetime.now(), _starting_genres())
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
def update_exclusion(payload: ExclusionUpdate, username: str | None = None, auth: dict = Depends(_auth_dependency)):
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
    auth: dict = Depends(_auth_dependency),
):
    policy = POLICIES.get(slug)
    if policy is None:
        raise HTTPException(status_code=404, detail='Unknown feed')
    resolved = _resolve_username(auth, username)
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')

    if limit is not None and limit != policy.size:
        policy = replace(policy, size=limit)

    kwargs = {}
    starting_genres = _starting_genres()
    if starting_genres:
        kwargs['starting_genres'] = starting_genres

    now = datetime.now()
    feed = build_feed(conn, resolved, policy, now, **kwargs)
    return {
        'slug': feed.slug,
        'state': feed.state,
        'scope': feed.scope,
        'generated_at': now.isoformat(),
        'tracks': [_track_view(track) for track in feed.tracks] if feed.state == 'ok' else [],
        'funnel': feed.funnel,
    }
