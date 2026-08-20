"""News bulletins MuMa records for itself.

No feed publishes the NOS radio bulletin on demand, so the only way to have
"the news of this hour" available is to record it off the live stream. A tap of
an icecast MP3 stream is already a playable file — the frames are
self-contained — which is why nothing here transcodes.

Bulletins deliberately live outside the music library: ratings, genre curation,
scan statistics and scrobbles all key on that library, and a dozen news files a
day would be noise in every one of them.
"""

import logging
import os
import time
from datetime import datetime, timezone

import requests
from fastapi import APIRouter

from services.music_manager.database import get_db_connection

router = APIRouter(tags=['news'])
logger = logging.getLogger('music-manager.news')

DEFAULT_STREAM_URL = 'https://icecast.omroep.nl/radio1-bb-mp3'
DEFAULT_DURATION_SECONDS = 600
DEFAULT_LEAD_SECONDS = 5
DEFAULT_RETENTION = 12

# A capture below this is treated as a failure. A truncated bulletin is worse
# than none: the button looks like it worked and then falls silent.
MIN_BULLETIN_SECONDS = 60
RETRY_DELAY_SECONDS = 20
CHUNK_BYTES = 32 * 1024


def init_db(cursor):
    cursor.execute(
        'CREATE TABLE IF NOT EXISTS news_sources ('
        ' id INT AUTO_INCREMENT PRIMARY KEY,'
        ' slug VARCHAR(64) NOT NULL UNIQUE,'
        ' name VARCHAR(128) NOT NULL,'
        ' stream_url VARCHAR(512) NOT NULL,'
        ' minute_of_hour TINYINT NOT NULL DEFAULT 0,'
        ' duration_seconds INT NOT NULL DEFAULT 600,'
        ' lead_seconds INT NOT NULL DEFAULT 5,'
        ' retention_count INT NOT NULL DEFAULT 12,'
        ' enabled TINYINT(1) NOT NULL DEFAULT 1,'
        ' last_error VARCHAR(512) NULL,'
        ' last_success_at DOUBLE NULL,'
        ' created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
        ')'
    )
    cursor.execute(
        'CREATE TABLE IF NOT EXISTS news_bulletins ('
        ' id BIGINT AUTO_INCREMENT PRIMARY KEY,'
        ' source_id INT NOT NULL,'
        ' started_at DOUBLE NOT NULL,'
        ' duration_ms INT NOT NULL,'
        ' size_bytes BIGINT NOT NULL,'
        ' filename VARCHAR(255) NOT NULL,'
        ' created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,'
        ' INDEX idx_source_started (source_id, started_at)'
        ')'
    )
    # The one seeded source: the hourly bulletin on NPO Radio 1.
    cursor.execute(
        'INSERT IGNORE INTO news_sources'
        ' (slug, name, stream_url, minute_of_hour, duration_seconds, lead_seconds,'
        ' retention_count) VALUES (%s, %s, %s, %s, %s, %s, %s)',
        ('nos', 'NOS Nieuws (NPO Radio 1)', DEFAULT_STREAM_URL, 0,
         DEFAULT_DURATION_SECONDS, DEFAULT_LEAD_SECONDS, DEFAULT_RETENTION),
    )


def next_capture_at(now: float, minute_of_hour: int, lead_seconds: int) -> float:
    """The next moment to open the stream: `minute_of_hour` minus the lead.

    The lead exists because a tap that connects a moment late would miss the
    pips. A slip the other way costs nothing: icecast bursts a backlog buffer
    the moment a client attaches, so a little too early is free.
    """
    hour_start = now - (now % 3600)
    candidate = hour_start + minute_of_hour * 60 - lead_seconds
    while candidate <= now:
        candidate += 3600
    return candidate


def bulletin_started_at(capture_at: float, lead_seconds: int) -> float:
    """The hour a capture belongs to, which is what clients label it with.

    Stored rather than the connect time, so a tap that began at 17:59:55 is
    the 18:00 bulletin and no client has to do that arithmetic.
    """
    return capture_at + lead_seconds


def bulletin_filename(slug: str, started_at: float) -> str:
    stamp = datetime.fromtimestamp(started_at, tz=timezone.utc).strftime('%Y-%m-%dT%H-%M')
    return f'{slug}-{stamp}.mp3'


def news_dir() -> str:
    directory = os.getenv('NEWS_DATA_DIR', '/app/data/news')
    os.makedirs(directory, exist_ok=True)
    return directory


def probe_duration_ms(path: str) -> int:
    """Duration of a finished capture.

    Its own function because the test suite replaces mutagen with a MagicMock,
    so this is the seam tests patch.
    """
    from mutagen.mp3 import MP3 # pylint: disable=import-outside-toplevel
    return int(MP3(path).info.length * 1000)


def capture_stream(url: str, target: str, duration_seconds: int) -> int:
    """Write the stream to `target` for `duration_seconds` of wall clock.

    MP3 frames are self-contained, so the bytes as they arrive are already a
    playable file. Nothing is transcoded and ffmpeg is not involved.
    """
    written = 0
    deadline = time.time() + duration_seconds
    with requests.get(url, stream=True, timeout=30) as response:
        response.raise_for_status()
        with open(target, 'wb') as handle:
            for chunk in response.iter_content(chunk_size=CHUNK_BYTES):
                if chunk:
                    handle.write(chunk)
                    written += len(chunk)
                if time.time() >= deadline:
                    break
    return written


def prune_bulletins(conn, source: dict) -> int:
    """Keep only the newest `retention_count` bulletins for this source."""
    with conn.cursor() as cursor:
        cursor.execute(
            'SELECT id, filename FROM news_bulletins WHERE source_id = %s'
            ' ORDER BY started_at DESC LIMIT 1000 OFFSET %s',
            (source['id'], source['retention_count']),
        )
        stale = cursor.fetchall() or []
        for row in stale:
            path = os.path.join(news_dir(), row['filename'])
            if os.path.exists(path):
                os.remove(path)
            cursor.execute('DELETE FROM news_bulletins WHERE id = %s', (row['id'],))
    conn.commit()
    return len(stale)


def capture_once(conn, source: dict, capture_at: float):
    """Record one bulletin. Returns its id, or None when it was discarded.

    The file is written to `.part` and renamed only once it is whole, so a
    client never sees a half-written capture.
    """
    started_at = bulletin_started_at(capture_at, source['lead_seconds'])
    filename = bulletin_filename(source['slug'], started_at)
    final_path = os.path.join(news_dir(), filename)
    part_path = f'{final_path}.part'

    size_bytes = capture_stream(source['stream_url'], part_path, source['duration_seconds'])
    duration_ms = probe_duration_ms(part_path)

    if duration_ms < MIN_BULLETIN_SECONDS * 1000:
        logger.warning(
            'News capture for %s was only %s ms, discarding', source['slug'], duration_ms
        )
        os.remove(part_path)
        return None

    os.replace(part_path, final_path)
    with conn.cursor() as cursor:
        cursor.execute(
            'INSERT INTO news_bulletins (source_id, started_at, duration_ms, size_bytes,'
            ' filename) VALUES (%s, %s, %s, %s, %s)',
            (source['id'], started_at, duration_ms, size_bytes, filename),
        )
        bulletin_id = cursor.lastrowid
    conn.commit()
    prune_bulletins(conn, source)
    return bulletin_id


def _mark_source(conn, source_id: int, error):
    with conn.cursor() as cursor:
        if error is None:
            cursor.execute(
                'UPDATE news_sources SET last_error = NULL, last_success_at = %s WHERE id = %s',
                (time.time(), source_id),
            )
        else:
            cursor.execute(
                'UPDATE news_sources SET last_error = %s WHERE id = %s',
                (str(error)[:512], source_id),
            )
    conn.commit()


def record_source(conn, source: dict, capture_at: float):
    """One capture with one retry.

    A missed hour is logged, never raised: the loop has to survive a stream
    that is briefly unreachable.
    """
    for attempt in (1, 2):
        try:
            bulletin_id = capture_once(conn, source, capture_at)
            _mark_source(
                conn, source['id'], None if bulletin_id else 'Capture too short, discarded'
            )
            return bulletin_id
        except Exception as e: # pylint: disable=broad-except
            logger.warning(
                'News capture for %s failed (attempt %s): %s', source['slug'], attempt, e
            )
            if attempt == 1:
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                _mark_source(conn, source['id'], e)
    return None


def _enabled_sources(conn) -> list:
    with conn.cursor() as cursor:
        cursor.execute(
            'SELECT id, slug, stream_url, minute_of_hour, duration_seconds,'
            ' lead_seconds, retention_count FROM news_sources WHERE enabled = 1'
        )
        return cursor.fetchall() or []


def run_news_recorder():
    """Background loop: sleep until the next boundary, then record every source."""
    while True:
        conn = get_db_connection()
        if not conn:
            time.sleep(60)
            continue
        try:
            sources = _enabled_sources(conn)
        except Exception as e: # pylint: disable=broad-except
            logger.error('News recorder could not read its sources: %s', e)
            sources = None
        finally:
            conn.close()

        if sources is None:
            time.sleep(60)
            continue
        if not sources:
            time.sleep(300)
            continue

        now = time.time()
        capture_at = min(
            next_capture_at(now, s['minute_of_hour'], s['lead_seconds']) for s in sources
        )
        time.sleep(max(0.0, capture_at - time.time()))

        conn = get_db_connection()
        if not conn:
            continue
        try:
            for source in sources:
                record_source(conn, source, capture_at)
        finally:
            conn.close()
