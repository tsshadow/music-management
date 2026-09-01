import json
import logging
import re
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.music_manager.database import get_db_connection
from services.music_manager.lms_subsonic import fetch_candidate_tracks
from services.music_manager.rbac import has_permission, require_permission
from services.music_manager.routers.management import verify_api_key

router = APIRouter(tags=['radio'])
logger = logging.getLogger('music-manager.radio')


def init_db(cursor):
    cursor.execute(
        'CREATE TABLE IF NOT EXISTS radio_channels ('
        ' id INT AUTO_INCREMENT PRIMARY KEY,'
        ' slug VARCHAR(64) NOT NULL UNIQUE,'
        ' name VARCHAR(128) NOT NULL,'
        ' genre VARCHAR(128) NULL,'
        ' enabled TINYINT(1) NOT NULL DEFAULT 1,'
        ' created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
        ')'
    )
    # A channel is a stored library filter. The older `genre` column still drives
    # any channel made before this column existed, so nothing needs migrating.
    cursor.execute("SHOW COLUMNS FROM radio_channels LIKE 'filter_json'")
    if not cursor.fetchone():
        cursor.execute('ALTER TABLE radio_channels ADD COLUMN filter_json TEXT NULL AFTER genre')
    cursor.execute(
        'CREATE TABLE IF NOT EXISTS radio_timeline ('
        ' id BIGINT AUTO_INCREMENT PRIMARY KEY,'
        ' channel_id INT NOT NULL,'
        ' track_id VARCHAR(64) NOT NULL,'
        ' title VARCHAR(512) NULL,'
        ' artist VARCHAR(512) NULL,'
        ' album VARCHAR(512) NULL,'
        ' cover_art VARCHAR(64) NULL,'
        ' duration_ms INT NOT NULL,'
        ' started_at DOUBLE NOT NULL,'
        ' ends_at DOUBLE NOT NULL,'
        ' INDEX idx_channel_started (channel_id, started_at),'
        ' INDEX idx_channel_ends (channel_id, ends_at)'
        ')'
    )
    # The single beta channel: genre NULL means "draw from the whole library".
    cursor.execute("INSERT IGNORE INTO radio_channels (slug, name, genre) VALUES ('main', 'Radio', NULL)")


SCHEDULE_HORIZON_SECONDS = 600.0


def plan_entries(existing_end, now: float, candidates: list, horizon: float = SCHEDULE_HORIZON_SECONDS) -> list:
    """Lay candidates back-to-back on the timeline until `horizon` seconds past `now`.

    `existing_end` is the `ends_at` of the last scheduled entry, or None when the
    timeline is empty. If it lies in the past (the scheduler was down, or nobody
    listened for a while) we resume from `now` rather than replaying history.
    """
    cursor = now if existing_end is None else max(existing_end, now)
    entries = []
    for candidate in candidates:
        if cursor >= now + horizon:
            break
        entry = dict(candidate)
        entry['started_at'] = cursor
        entry['ends_at'] = cursor + candidate['duration_ms'] / 1000.0
        entries.append(entry)
        cursor = entry['ends_at']
    return entries


CANDIDATE_BATCH_SIZE = 20
HISTORY_RETENTION_SECONDS = 3600.0


def channel_filter(channel: dict) -> dict:
    """The filter a channel selects on, whichever column it was stored in."""
    raw = channel.get('filter_json')
    if raw:
        try:
            stored = json.loads(raw)
        except ValueError:
            logger.warning("Radio channel '%s': unreadable filter_json, ignoring it", channel.get('slug'))
            stored = None
        if isinstance(stored, dict):
            return stored
    genre = channel.get('genre')
    return {'genre': genre} if genre else {}


def pick_candidates(candidates: list, scheduled_track_ids) -> list:
    """Choose which candidates may go on the timeline, in the order they play.

    LMS already returns them randomised, so this only drops what is still on the
    timeline -- without it a twenty-track channel repeats itself inside the same
    ten-minute window. This is the seam for weighted selection later: the rating
    travels on the candidate, so a weighted version changes this function alone.
    """
    already = set(scheduled_track_ids or ())
    picked = []
    for candidate in candidates:
        track_id = candidate.get('track_id')
        if track_id in already:
            continue
        already.add(track_id)
        picked.append(candidate)
    return picked


def scheduled_track_ids(conn, channel_id: int, since: float) -> list:
    """Track ids on this channel's timeline that have not finished playing yet."""
    with conn.cursor() as cursor:
        cursor.execute(
            'SELECT track_id FROM radio_timeline WHERE channel_id = %s AND ends_at > %s',
            (channel_id, since),
        )
        return [row['track_id'] for row in (cursor.fetchall() or [])]


def fill_channel(conn, channel: dict, now: float) -> int:
    """Top up one channel's timeline. Returns how many entries were inserted."""
    with conn.cursor() as cursor:
        cursor.execute(
            'SELECT MAX(ends_at) AS last_end FROM radio_timeline WHERE channel_id = %s',
            (channel['id'],),
        )
        row = cursor.fetchone() or {}
        existing_end = row.get('last_end')

    if existing_end is not None and existing_end >= now + SCHEDULE_HORIZON_SECONDS:
        return 0

    try:
        candidates = fetch_candidate_tracks(channel_filter(channel), size=CANDIDATE_BATCH_SIZE)
    except Exception as e:
        logger.warning("Radio channel '%s': could not fetch candidates: %s", channel['slug'], e)
        return 0

    candidates = pick_candidates(candidates, scheduled_track_ids(conn, channel['id'], now))
    entries = plan_entries(existing_end, now, candidates)
    if not entries:
        return 0

    with conn.cursor() as cursor:
        for entry in entries:
            cursor.execute(
                'INSERT INTO radio_timeline'
                ' (channel_id, track_id, title, artist, album, cover_art, duration_ms, started_at, ends_at)'
                ' VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)',
                (
                    channel['id'],
                    entry['track_id'],
                    entry['title'],
                    entry['artist'],
                    entry['album'],
                    entry['cover_art'],
                    entry['duration_ms'],
                    entry['started_at'],
                    entry['ends_at'],
                ),
            )
        cursor.execute(
            'DELETE FROM radio_timeline WHERE channel_id = %s AND ends_at < %s',
            (channel['id'], now - HISTORY_RETENTION_SECONDS),
        )
    conn.commit()
    return len(entries)


def run_radio_scheduler(interval: int = 5):
    """Background loop keeping every enabled channel's timeline filled ahead of now."""
    while True:
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute('SELECT id, slug, genre, filter_json FROM radio_channels WHERE enabled = 1')
                    channels = cursor.fetchall()
                for channel in channels:
                    fill_channel(conn, channel, time.time())
            except Exception as e:
                logger.error('Radio scheduler iteration failed: %s', e)
            finally:
                conn.close()
        time.sleep(interval)


@router.get('/channels')
def list_channels(include_disabled: bool = False, auth: dict = Depends(verify_api_key)):
    """Every listener may see the channel line-up, filters included: the filter is
    what a player has to describe a channel with. A disabled channel is off the
    air, so only whoever may edit channels has any use for seeing it."""
    if include_disabled and not has_permission(auth, 'radio.manage'):
        raise HTTPException(status_code=403, detail='Missing permission: radio.manage')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database unavailable')
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT slug, name, genre, filter_json, enabled FROM radio_channels'
                + ('' if include_disabled else ' WHERE enabled = 1')
                + ' ORDER BY id'
            )
            channels = cursor.fetchall() or []
        return {
            'channels': [
                {
                    'slug': c['slug'],
                    'name': c['name'],
                    'genre': c['genre'],
                    'enabled': bool(c['enabled']),
                    'filter': channel_filter(c),
                }
                for c in channels
            ]
        }
    finally:
        conn.close()


SLUG_PATTERN = re.compile(r'^[a-z0-9][a-z0-9-]{0,63}$')
PREVIEW_PROBE_SIZE = 100
PREVIEW_SAMPLE_SIZE = 10


class ChannelFilter(BaseModel):
    """The filter a channel selects on. Every field is optional; all of them empty
    means the whole library, which is what the seeded `main` channel is."""

    label: str | None = None
    genre: str | None = None
    artist: str | None = None
    length: str | None = None
    year: str | None = None
    rating_min: int | None = None
    rating_max: int | None = None
    duration_min: int | None = None
    duration_max: int | None = None
    include_unrated: bool = False


class ChannelCreate(BaseModel):
    slug: str
    name: str
    filter: ChannelFilter = ChannelFilter()


class ChannelUpdate(BaseModel):
    name: str | None = None
    filter: ChannelFilter | None = None
    enabled: bool | None = None


class FilterPreview(BaseModel):
    filter: ChannelFilter = ChannelFilter()


def _stored_filter(channel_filter_model: ChannelFilter) -> str:
    return json.dumps(channel_filter_model.model_dump(exclude_none=True))


def _require_db():
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database unavailable')
    return conn


@router.post('/channels', status_code=201)
def create_channel(body: ChannelCreate, _auth: dict = Depends(require_permission('radio.manage'))):
    if not SLUG_PATTERN.match(body.slug):
        raise HTTPException(status_code=400, detail='Slug must be lowercase letters, digits and dashes')
    if not body.name.strip():
        raise HTTPException(status_code=400, detail='Name is required')
    conn = _require_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT id FROM radio_channels WHERE slug = %s', (body.slug,))
            if cursor.fetchone():
                raise HTTPException(status_code=409, detail='A channel with that slug already exists')
            cursor.execute(
                'INSERT INTO radio_channels (slug, name, filter_json) VALUES (%s, %s, %s)',
                (body.slug, body.name.strip(), _stored_filter(body.filter)),
            )
        conn.commit()
        return {'slug': body.slug, 'name': body.name.strip(), 'filter': body.filter.model_dump(exclude_none=True)}
    finally:
        conn.close()


@router.put('/channels/{slug}')
def update_channel(slug: str, body: ChannelUpdate, _auth: dict = Depends(require_permission('radio.manage'))):
    conn = _require_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT id FROM radio_channels WHERE slug = %s', (slug,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail='Unknown channel')

            assignments = []
            params = []
            if body.name is not None:
                if not body.name.strip():
                    raise HTTPException(status_code=400, detail='Name is required')
                assignments.append('name = %s')
                params.append(body.name.strip())
            if body.filter is not None:
                # A channel edited here stops using the legacy genre column, so the
                # two can never disagree about what the channel plays.
                assignments.append('filter_json = %s')
                params.append(_stored_filter(body.filter))
                assignments.append('genre = NULL')
            if body.enabled is not None:
                assignments.append('enabled = %s')
                params.append(1 if body.enabled else 0)
            if not assignments:
                raise HTTPException(status_code=400, detail='Nothing to update')

            params.append(slug)
            cursor.execute(f"UPDATE radio_channels SET {', '.join(assignments)} WHERE slug = %s", tuple(params))
        conn.commit()

        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT slug, name, genre, filter_json, enabled FROM radio_channels WHERE slug = %s', (slug,)
            )
            channel = cursor.fetchone()
        return {
            'slug': channel['slug'],
            'name': channel['name'],
            'enabled': bool(channel['enabled']),
            'filter': channel_filter(channel),
        }
    finally:
        conn.close()


@router.delete('/channels/{slug}')
def delete_channel(slug: str, _auth: dict = Depends(require_permission('radio.manage'))):
    conn = _require_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT id FROM radio_channels WHERE slug = %s', (slug,))
            channel = cursor.fetchone()
            if not channel:
                raise HTTPException(status_code=404, detail='Unknown channel')
            # The timeline goes with it; nothing would ever read those rows again.
            cursor.execute('DELETE FROM radio_timeline WHERE channel_id = %s', (channel['id'],))
            cursor.execute('DELETE FROM radio_channels WHERE id = %s', (channel['id'],))
        conn.commit()
        return {'deleted': slug}
    finally:
        conn.close()


@router.post('/channels/preview')
def preview_filter(body: FilterPreview, _auth: dict = Depends(require_permission('radio.manage'))):
    """What a filter would play, so a channel can be judged before it is saved."""
    try:
        matches = fetch_candidate_tracks(body.filter.model_dump(exclude_none=True), size=PREVIEW_PROBE_SIZE)
    except Exception as e:
        logger.warning('Radio filter preview failed: %s', e)
        raise HTTPException(status_code=502, detail=f'LMS could not answer this filter: {e}') from e
    return {
        'matched': len(matches),
        # LMS was asked for a bounded number, so a full response means "at least".
        'truncated': len(matches) >= PREVIEW_PROBE_SIZE,
        'sample': matches[:PREVIEW_SAMPLE_SIZE],
    }


ENTRY_COLUMNS = 'track_id, title, artist, album, cover_art, duration_ms, started_at, ends_at'


@router.get('/time')
def server_time(_auth: dict = Depends(verify_api_key)):
    """Deliberately DB-free: clients call this repeatedly to measure clock offset."""
    return {'server_time': time.time()}


@router.get('/{slug}/state')
def get_channel_state(slug: str, _auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database unavailable')
    try:
        now = time.time()
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT id, slug, name, genre FROM radio_channels WHERE slug = %s AND enabled = 1',
                (slug,),
            )
            channel = cursor.fetchone()
            if not channel:
                raise HTTPException(status_code=404, detail='Unknown channel')

            cursor.execute(
                f'SELECT {ENTRY_COLUMNS} FROM radio_timeline'
                ' WHERE channel_id = %s AND started_at <= %s AND ends_at > %s'
                ' ORDER BY started_at DESC LIMIT 1',
                (channel['id'], now, now),
            )
            current = cursor.fetchone()

            cursor.execute(
                f'SELECT {ENTRY_COLUMNS} FROM radio_timeline'
                ' WHERE channel_id = %s AND started_at > %s'
                ' ORDER BY started_at ASC LIMIT 1',
                (channel['id'], now),
            )
            nxt = cursor.fetchone()

        return {
            'server_time': now,
            'channel': {'slug': channel['slug'], 'name': channel['name'], 'genre': channel['genre']},
            'current': current,
            'next': nxt,
        }
    finally:
        conn.close()
