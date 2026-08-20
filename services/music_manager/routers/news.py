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
import re
import threading
import time
from datetime import UTC, datetime

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.music_manager.database import get_db_connection
from services.music_manager.rbac import require_permission
from services.music_manager.routers.management import verify_api_key

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

DEFAULT_SOURCE = 'nos'
SLUG_PATTERN = re.compile(r'^[a-z0-9][a-z0-9-]{0,63}$')
RANGE_PATTERN = re.compile(r'bytes=(\d*)-(\d*)')


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
    stamp = datetime.fromtimestamp(started_at, tz=UTC).strftime('%Y-%m-%dT%H-%M')
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
    from mutagen.mp3 import MP3  # pylint: disable=import-outside-toplevel
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


def _require_db():
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database unavailable')
    return conn


def _row_to_bulletin(row: dict) -> dict:
    return {'id': row['id'], 'source': row['slug'], 'started_at': row['started_at'],
            'duration_ms': row['duration_ms'], 'size_bytes': row['size_bytes']}


def _load_source(cursor, slug: str) -> dict:
    cursor.execute(
        'SELECT id, slug, stream_url, minute_of_hour, duration_seconds, lead_seconds,'
        ' retention_count FROM news_sources WHERE slug = %s',
        (slug,),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail='Unknown source')
    return row


class SourceCreate(BaseModel):
    slug: str
    name: str
    stream_url: str
    minute_of_hour: int = 0
    duration_seconds: int = DEFAULT_DURATION_SECONDS
    lead_seconds: int = DEFAULT_LEAD_SECONDS
    retention_count: int = DEFAULT_RETENTION


class SourceUpdate(BaseModel):
    """Every field optional: the management screen sends only what changed."""
    name: str | None = None
    stream_url: str | None = None
    minute_of_hour: int | None = None
    duration_seconds: int | None = None
    lead_seconds: int | None = None
    retention_count: int | None = None
    enabled: bool | None = None


@router.get('/sources')
def list_sources(_auth: dict = Depends(verify_api_key)):
    """The configured sources and how their last capture went."""
    conn = _require_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT slug, name, stream_url, minute_of_hour, duration_seconds,'
                ' retention_count, enabled, last_error, last_success_at'
                ' FROM news_sources ORDER BY id'
            )
            rows = cursor.fetchall() or []
        return {'sources': [
            {'slug': r['slug'], 'name': r['name'], 'stream_url': r['stream_url'],
             'minute_of_hour': r['minute_of_hour'], 'duration_seconds': r['duration_seconds'],
             'retention_count': r['retention_count'], 'enabled': bool(r['enabled']),
             'last_error': r['last_error'], 'last_success_at': r['last_success_at']}
            for r in rows
        ]}
    finally:
        conn.close()


@router.get('/bulletins')
def list_bulletins(source: str = DEFAULT_SOURCE, limit: int = Query(12, ge=1, le=100),
                   _auth: dict = Depends(verify_api_key)):
    conn = _require_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT b.id, s.slug, b.started_at, b.duration_ms, b.size_bytes'
                ' FROM news_bulletins b JOIN news_sources s ON s.id = b.source_id'
                ' WHERE s.slug = %s ORDER BY started_at DESC LIMIT %s',
                (source, limit),
            )
            rows = cursor.fetchall() or []
        return {'bulletins': [_row_to_bulletin(r) for r in rows]}
    finally:
        conn.close()


@router.get('/bulletins/latest')
def latest_bulletin(source: str = DEFAULT_SOURCE, _auth: dict = Depends(verify_api_key)):
    conn = _require_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT b.id, s.slug, b.started_at, b.duration_ms, b.size_bytes'
                ' FROM news_bulletins b JOIN news_sources s ON s.id = b.source_id'
                ' WHERE s.slug = %s ORDER BY started_at DESC LIMIT 1',
                (source,),
            )
            row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail='No bulletin recorded yet')
        return _row_to_bulletin(row)
    finally:
        conn.close()


def parse_range(header, size: int):
    """Return (start, end) inclusive, or None for a whole-file response.

    Handled here rather than left to FileResponse: the pinned FastAPI
    constrains Starlette to a version whose range behaviour is not worth
    gambling on, and a player that cannot seek fails silently in a car.
    """
    if not header:
        return None
    match = RANGE_PATTERN.fullmatch(header.strip())
    if not match:
        return None
    raw_start, raw_end = match.groups()
    if raw_start == '':
        if raw_end == '':
            return None
        length = min(int(raw_end), size)
        return size - length, size - 1
    start = int(raw_start)
    end = int(raw_end) if raw_end else size - 1
    return start, min(end, size - 1)


def _file_chunks(path: str, start: int, end: int):
    with open(path, 'rb') as handle:
        handle.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = handle.read(min(CHUNK_BYTES, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@router.get('/bulletins/{bulletin_id}/stream')
def stream_bulletin(bulletin_id: int, request: Request, _auth: dict = Depends(verify_api_key)):
    conn = _require_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT filename FROM news_bulletins WHERE id = %s', (bulletin_id,))
            row = cursor.fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail='Unknown bulletin')

    path = os.path.join(news_dir(), row['filename'])
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail='Bulletin audio is gone')

    size = os.path.getsize(path)
    span = parse_range(request.headers.get('range'), size)
    headers = {'Accept-Ranges': 'bytes'}
    if span is None:
        headers['Content-Length'] = str(size)
        return StreamingResponse(_file_chunks(path, 0, size - 1),
                                 media_type='audio/mpeg', headers=headers)

    start, end = span
    if start >= size:
        raise HTTPException(status_code=416, detail='Range beyond end of file')
    headers['Content-Range'] = f'bytes {start}-{end}/{size}'
    headers['Content-Length'] = str(end - start + 1)
    return StreamingResponse(_file_chunks(path, start, end), status_code=206,
                             media_type='audio/mpeg', headers=headers)


@router.post('/sources', status_code=201)
def create_source(body: SourceCreate, _auth: dict = Depends(require_permission('news.manage'))):
    if not SLUG_PATTERN.match(body.slug):
        raise HTTPException(status_code=400, detail='Invalid slug')
    conn = _require_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                'INSERT INTO news_sources (slug, name, stream_url, minute_of_hour,'
                ' duration_seconds, lead_seconds, retention_count)'
                ' VALUES (%s, %s, %s, %s, %s, %s, %s)',
                (body.slug, body.name.strip(), body.stream_url, body.minute_of_hour,
                 body.duration_seconds, body.lead_seconds, body.retention_count),
            )
        conn.commit()
        return {'slug': body.slug}
    finally:
        conn.close()


@router.put('/sources/{slug}')
def update_source(slug: str, body: SourceUpdate,
                  _auth: dict = Depends(require_permission('news.manage'))):
    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail='Nothing to update')
    conn = _require_db()
    try:
        with conn.cursor() as cursor:
            _load_source(cursor, slug)
            assignments = ', '.join(f'{key} = %s' for key in fields)
            params = [int(v) if isinstance(v, bool) else v for v in fields.values()]
            params.append(slug)
            cursor.execute(f'UPDATE news_sources SET {assignments} WHERE slug = %s', tuple(params))
        conn.commit()
        return {'slug': slug, **fields}
    finally:
        conn.close()


@router.delete('/sources/{slug}')
def delete_source(slug: str, _auth: dict = Depends(require_permission('news.manage'))):
    conn = _require_db()
    try:
        with conn.cursor() as cursor:
            source = _load_source(cursor, slug)
            cursor.execute('DELETE FROM news_bulletins WHERE source_id = %s', (source['id'],))
            cursor.execute('DELETE FROM news_sources WHERE id = %s', (source['id'],))
        conn.commit()
        return {'deleted': slug}
    finally:
        conn.close()


def _record_in_background(source: dict):
    """Runs a manual capture on its own connection, off the request thread."""
    conn = get_db_connection()
    if not conn:
        logger.error('Manual news capture for %s: database unavailable', source['slug'])
        return
    try:
        record_source(conn, source, time.time() - source['lead_seconds'])
    finally:
        conn.close()


@router.post('/sources/{slug}/record-now')
def record_now(slug: str, _auth: dict = Depends(require_permission('news.manage'))):
    """Capture straight away instead of waiting for the hour.

    This is the test path in production: without it, checking a change costs an
    hour of waiting.

    It answers immediately and records in the background, because a capture
    takes as long as the recording itself -- ten minutes by default. Holding the
    request open for that would time out at the reverse proxy and report a
    failure for a capture that actually succeeded. The result shows up in the
    bulletin list, and any failure in `last_error`.
    """
    conn = _require_db()
    try:
        with conn.cursor() as cursor:
            source = _load_source(cursor, slug)
    finally:
        conn.close()

    threading.Thread(
        target=_record_in_background, args=(source,), daemon=True,
        name=f'news-record-{slug}',
    ).start()
    return {'started': True, 'slug': slug, 'duration_seconds': source['duration_seconds']}
