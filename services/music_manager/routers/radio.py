import logging
import time
from fastapi import APIRouter, HTTPException, Depends
from services.music_manager.database import get_db_connection
from services.music_manager.lms_subsonic import fetch_candidate_tracks
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
    cursor.execute(
        "INSERT IGNORE INTO radio_channels (slug, name, genre) VALUES ('main', 'Radio', NULL)"
    )


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
        candidates = fetch_candidate_tracks(channel.get('genre'), size=CANDIDATE_BATCH_SIZE)
    except Exception as e:
        logger.warning("Radio channel '%s': could not fetch candidates: %s", channel['slug'], e)
        return 0

    entries = plan_entries(existing_end, now, candidates)
    if not entries:
        return 0

    with conn.cursor() as cursor:
        for entry in entries:
            cursor.execute(
                'INSERT INTO radio_timeline'
                ' (channel_id, track_id, title, artist, album, cover_art, duration_ms, started_at, ends_at)'
                ' VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)',
                (channel['id'], entry['track_id'], entry['title'], entry['artist'], entry['album'],
                 entry['cover_art'], entry['duration_ms'], entry['started_at'], entry['ends_at']),
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
                    cursor.execute('SELECT id, slug, genre FROM radio_channels WHERE enabled = 1')
                    channels = cursor.fetchall()
                for channel in channels:
                    fill_channel(conn, channel, time.time())
            except Exception as e:
                logger.error('Radio scheduler iteration failed: %s', e)
            finally:
                conn.close()
        time.sleep(interval)


@router.get('/channels')
def list_channels(_auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database unavailable')
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT slug, name, genre FROM radio_channels WHERE enabled = 1 ORDER BY id'
            )
            return {'channels': cursor.fetchall()}
    finally:
        conn.close()
