import base64
import binascii
import ipaddress
import logging
import os
import socket
from urllib.parse import urljoin, urlsplit

import requests
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from services.music_manager.database import get_db_connection
from services.music_manager.rbac import require_permission

router = APIRouter(tags=['artists'])
logger = logging.getLogger(__name__)
fetch_progress = {'active': False, 'total': 0, 'current': 0, 'last_artist': None, 'status': 'idle', 'message': None}


def verify_api_key(x_api_key: str | None = Header(None)):
    """Delegates to the canonical users.verify_api_key; read-only routes use it."""
    from services.music_manager.routers.users import verify_api_key as _verify

    return _verify(x_api_key)


# Changing which picture an artist carries is curation, the same as editing the artist.
require_rules_manage = require_permission('rules.manage')

# Both ways in -- a URL this service fetches, and bytes a browser uploads -- stop here.
# A real artist photo is a few hundred kilobytes; ten megabytes is generous and still
# far short of what a hostile URL could stream into memory.
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_REDIRECTS = 3
DOWNLOAD_TIMEOUT_SECONDS = 10


class UnsafeImageUrl(ValueError):
    """A URL this service refuses to fetch: wrong scheme, unresolvable, or not public."""


class ImageTooLarge(ValueError):
    """An image that exceeds MAX_IMAGE_BYTES."""


def ensure_public_url(url: str) -> None:
    """Refuse a URL that is not http(s) or whose host resolves to a non-public address.

    Without this, "set image from URL" is a request this server makes on the caller's
    behalf to anything it can reach: the database, the Docker socket proxy, LMS, the
    router's admin page. Every address the name resolves to must be globally routable,
    so loopback, RFC 1918, link-local (cloud metadata), CGNAT (the tailnet) and the
    reserved ranges are all refused. A name that resolves differently between this
    check and the fetch (DNS rebinding) is not covered; each redirect hop is re-checked.
    """
    parts = urlsplit(url)
    if parts.scheme.lower() not in ('http', 'https') or not parts.hostname:
        raise UnsafeImageUrl('Only http(s) image URLs are supported')
    try:
        port = parts.port or (443 if parts.scheme.lower() == 'https' else 80)
        infos = socket.getaddrinfo(parts.hostname, port, proto=socket.IPPROTO_TCP)
    except (ValueError, OSError) as e:
        raise UnsafeImageUrl(f'Cannot resolve {parts.hostname}') from e
    if not infos:
        raise UnsafeImageUrl(f'Cannot resolve {parts.hostname}')
    for info in infos:
        address = ipaddress.ip_address(str(info[4][0]).split('%', 1)[0])
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        if not address.is_global or address.is_multicast:
            raise UnsafeImageUrl('Image URL points at a non-public address')


def download_public_image(url: str) -> bytes:
    """Fetch an image from a public http(s) URL, at most MAX_IMAGE_BYTES of it.

    Redirects are followed by hand so every hop passes ensure_public_url, and the body
    is streamed so an oversized or endless response is cut off rather than buffered.
    """
    for _ in range(MAX_IMAGE_REDIRECTS + 1):
        ensure_public_url(url)
        with requests.get(url, timeout=DOWNLOAD_TIMEOUT_SECONDS, stream=True, allow_redirects=False) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers.get('Location', ''))
                continue
            response.raise_for_status()
            declared = response.headers.get('Content-Length', '')
            if declared.isdigit() and int(declared) > MAX_IMAGE_BYTES:
                raise ImageTooLarge('Image is larger than 10 MB')
            data = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                data.extend(chunk)
                if len(data) > MAX_IMAGE_BYTES:
                    raise ImageTooLarge('Image is larger than 10 MB')
            return bytes(data)
    raise UnsafeImageUrl('Too many redirects')


STORAGE_PATH = os.getenv('STORAGE_PATH', '/mnt/music/artists')


def init_db(cursor):
    cursor.execute(
        '\n        CREATE TABLE IF NOT EXISTS library_artist_images (\n            id INT AUTO_INCREMENT PRIMARY KEY,\n            artist_id INT NOT NULL,\n            source VARCHAR(50),\n            source_id VARCHAR(255),\n            original_url TEXT,\n            cached_path TEXT,\n            public_path TEXT,\n            width INT,\n            height INT,\n            mime_type VARCHAR(50),\n            file_size INT,\n            confidence INT DEFAULT 0,\n            is_primary TINYINT(1) DEFAULT 0,\n            created_at DATETIME,\n            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,\n            INDEX (artist_id),\n            INDEX (is_primary)\n        )\n    '
    )
    # external_url and verified are in production but were missing here, so a fresh
    # database got a narrower table than the code reads from. See migrate_v13 for the
    # matching ALTER on databases that already have the narrow shape.
    cursor.execute(
        '\n        CREATE TABLE IF NOT EXISTS artist_external_ids (\n            artist_id INT NOT NULL,\n            source VARCHAR(50) NOT NULL,\n            external_id VARCHAR(255) NOT NULL,\n            external_url TEXT NULL,\n            verified TINYINT(1) NOT NULL DEFAULT 0,\n            created_at DATETIME,\n            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,\n            PRIMARY KEY (artist_id, source)\n        )\n    '
    )
    columns_to_add = [
        ('primary_image_id', 'INT NULL'),
        ('image_updated_at', 'DATETIME NULL'),
        ('image_status', 'VARCHAR(50) NULL'),
        ('mbid', 'VARCHAR(100) NULL'),
    ]
    for col_name, col_type in columns_to_add:
        cursor.execute(f"SHOW COLUMNS FROM library_artists LIKE '{col_name}'")
        if not cursor.fetchone():
            cursor.execute(f'ALTER TABLE library_artists ADD COLUMN {col_name} {col_type}')


@router.get('/search')
def search_artist_images(q: str = '', _auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            if q == '':
                cursor.execute(
                    '\n                    SELECT a.id, a.name, a.primary_image_id, i.width, i.height, i.mime_type, a.image_status\n                    FROM library_artists a\n                    JOIN library_artist_images i ON a.primary_image_id = i.id\n                    ORDER BY a.name\n                    LIMIT 100\n                '
                )
            else:
                cursor.execute(
                    '\n                    SELECT a.id, a.name, a.primary_image_id, i.width, i.height, i.mime_type, a.image_status\n                    FROM library_artists a\n                    JOIN library_artist_images i ON a.primary_image_id = i.id\n                    WHERE a.name LIKE %s\n                    ORDER BY a.name\n                    LIMIT 100\n                ',
                    (f'%{q}%',),
                )
            return cursor.fetchall()
    finally:
        conn.close()


@router.get('/search-all')
def search_all_artists(q: str = '', _auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            if q == '':
                cursor.execute(
                    '\n                    SELECT a.id, a.name, a.primary_image_id, a.image_status\n                    FROM library_artists a\n                    ORDER BY a.name\n                    LIMIT 100\n                '
                )
            else:
                cursor.execute(
                    '\n                    SELECT a.id, a.name, a.primary_image_id, a.image_status\n                    FROM library_artists a\n                    WHERE a.name LIKE %s\n                    ORDER BY a.name\n                    LIMIT 100\n                ',
                    (f'%{q}%',),
                )
            return cursor.fetchall()
    finally:
        conn.close()


@router.get('/images/stats')
def get_artist_image_stats(_auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) as total FROM library_artists')
            total = cursor.fetchone()['total']
            cursor.execute('SELECT COUNT(*) as with_image FROM library_artists WHERE primary_image_id IS NOT NULL')
            with_image = cursor.fetchone()['with_image']
            return {
                'total_artists': total,
                'artists_with_images': with_image,
                'artists_without_images': total - with_image,
            }
    finally:
        conn.close()


@router.get('/fetch-progress')
def get_fetch_progress(_auth: dict = Depends(verify_api_key)):
    return fetch_progress


# --- Artist image manager -------------------------------------------------
#
# The manager UI talks to MuMa through LMS's `MumaResource` proxy (`/muma/api/...`),
# which shaped the routes below:
#   * every path ending in exactly "/image" is intercepted by the proxy and turned
#     into a GET of the artist-image file, so mutations live on deeper sub-paths
#     ("/image/url", "/image/upload", "/image/clear", "/image/select/{id}");
#   * the mutations are POST-only because, when they were written, the proxy
#     forwarded every DELETE to MuMa as a POST. The proxy now forwards the real
#     verb (PUT and DELETE included); these routes stay POST so existing clients
#     keep working.


class ArtistImageUrlRequest(BaseModel):
    url: str


class ArtistImageUploadRequest(BaseModel):
    filename: str | None = None
    # Raw image bytes, base64-encoded (optionally as a "data:image/png;base64,..."
    # data URL). The proxy forwards request bodies as text, so binary multipart
    # uploads would be corrupted in transit.
    data: str


MANAGE_SEARCH_MAX_LIMIT = 200


@router.get('/manage/search')
def manage_search_artists(
    q: str = '', only: str = 'all', limit: int = 60, offset: int = 0, _auth: dict = Depends(verify_api_key)
):
    """Single search endpoint for the artist image manager.

    Unlike ``/search`` (only artists that already have an image) and ``/search-all``
    (no image metadata at all), this returns *every* matching artist together with
    the metadata of its primary image when it has one, so the manager can render one
    unified, complete result list.
    """
    if only not in ('all', 'with', 'without'):
        raise HTTPException(status_code=400, detail="'only' must be one of: all, with, without")
    limit = max(1, min(limit, MANAGE_SEARCH_MAX_LIMIT))
    offset = max(0, offset)
    where = []
    params = []
    if q:
        where.append('a.name LIKE %s')
        params.append(f'%{q}%')
    if only == 'with':
        where.append('a.primary_image_id IS NOT NULL')
    elif only == 'without':
        where.append('a.primary_image_id IS NULL')
    where_sql = f"WHERE {' AND '.join(where)}" if where else ''
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute(f'SELECT COUNT(*) AS total FROM library_artists a {where_sql}', tuple(params))
            row = cursor.fetchone()
            total = (row or {}).get('total', 0)
            cursor.execute(
                f'''
                SELECT a.id, a.name, a.primary_image_id, a.image_status, a.image_updated_at,
                       i.width, i.height, i.mime_type, i.file_size, i.source, i.original_url
                FROM library_artists a
                LEFT JOIN library_artist_images i ON a.primary_image_id = i.id
                {where_sql}
                ORDER BY a.name
                LIMIT %s OFFSET %s
            ''',
                tuple(params) + (limit, offset),
            )
            items = []
            for artist in cursor.fetchall():
                updated_at = artist.get('image_updated_at')
                items.append(
                    {
                        'id': artist['id'],
                        'name': artist['name'],
                        'primary_image_id': artist['primary_image_id'],
                        'has_image': artist['primary_image_id'] is not None,
                        'image_status': artist['image_status'],
                        'image_updated_at': updated_at.isoformat() if hasattr(updated_at, 'isoformat') else updated_at,
                        'width': artist.get('width'),
                        'height': artist.get('height'),
                        'mime_type': artist.get('mime_type'),
                        'file_size': artist.get('file_size'),
                        'source': artist.get('source'),
                        'original_url': artist.get('original_url'),
                    }
                )
            return {'items': items, 'total': total, 'limit': limit, 'offset': offset}
    finally:
        conn.close()


@router.get('/{artist_id}/images')
def list_artist_images(artist_id: int, _auth: dict = Depends(verify_api_key)):
    """All images stored for one artist, so the manager can switch the primary one."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT id, name, primary_image_id FROM library_artists WHERE id = %s', (artist_id,))
            artist = cursor.fetchone()
            if not artist:
                raise HTTPException(status_code=404, detail='Artist not found')
            cursor.execute(
                '''
                SELECT id, source, source_id, original_url, cached_path, public_path,
                       width, height, mime_type, file_size, confidence, is_primary
                FROM library_artist_images
                WHERE artist_id = %s
                ORDER BY is_primary DESC, confidence DESC, id DESC
            ''',
                (artist_id,),
            )
            images = []
            for image in cursor.fetchall():
                image = dict(image)
                image['exists_on_disk'] = bool(image.get('cached_path')) and os.path.exists(image['cached_path'])
                images.append(image)
            return {
                'artist_id': artist['id'],
                'artist_name': artist['name'],
                'primary_image_id': artist['primary_image_id'],
                'images': images,
            }
    finally:
        conn.close()


def _set_primary_image(cursor, artist_id: int, image_id: int):
    cursor.execute('UPDATE library_artist_images SET is_primary = 0 WHERE artist_id = %s', (artist_id,))
    cursor.execute('UPDATE library_artist_images SET is_primary = 1 WHERE id = %s', (image_id,))
    cursor.execute(
        """
        UPDATE library_artists
        SET primary_image_id = %s, image_updated_at = NOW(), image_status = 'active'
        WHERE id = %s
    """,
        (image_id, artist_id),
    )


def _store_manual_image(artist_id: int, image_data: bytes, original_url: str | None = None):
    """Saves manually supplied image bytes and makes them the artist's primary image."""
    from services.music_manager.artist_image_fetcher.storage import ImageStorage

    storage_path = os.getenv('ARTIST_IMAGE_STORAGE_PATH') or os.getenv('STORAGE_PATH') or '/mnt/music/artists'
    public_base_url = os.getenv('ARTIST_IMAGE_PUBLIC_BASE_URL', '/media/artist-images')
    storage = ImageStorage(storage_path, public_base_url)
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT id, name FROM library_artists WHERE id = %s', (artist_id,))
            artist = cursor.fetchone()
            if not artist:
                raise HTTPException(status_code=404, detail='Artist not found')
        try:
            meta = storage.save_image(artist_id, 'manual', image_data)
        except Exception as e:
            logger.error(f'Failed to store manual image for artist {artist_id}: {e}')
            raise HTTPException(status_code=400, detail=f'Could not process image: {e}') from e
        with conn.cursor() as cursor:
            cursor.execute(
                '''
                INSERT INTO library_artist_images
                (artist_id, source, source_id, original_url, cached_path, public_path,
                 width, height, mime_type, file_size, confidence, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ''',
                (
                    artist_id,
                    'manual',
                    None,
                    original_url,
                    meta['cached_path'],
                    meta['public_path'],
                    meta['width'],
                    meta['height'],
                    meta['mime_type'],
                    meta['file_size'],
                    100,
                ),
            )
            image_id = cursor.lastrowid
            _set_primary_image(cursor, artist_id, image_id)
        conn.commit()
        return {
            'status': 'ok',
            'artist_id': artist_id,
            'artist_name': artist['name'],
            'image_id': image_id,
            'width': meta['width'],
            'height': meta['height'],
            'mime_type': meta['mime_type'],
            'file_size': meta['file_size'],
        }
    finally:
        conn.close()


@router.post('/{artist_id}/image/url')
def set_artist_image_from_url(artist_id: int, req: ArtistImageUrlRequest, _auth: dict = Depends(require_rules_manage)):
    """Fetch an image from a public URL and make it the artist's primary image."""
    url = (req.url or '').strip()
    try:
        image_data = download_public_image(url)
    except UnsafeImageUrl as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ImageTooLarge as e:
        raise HTTPException(status_code=413, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f'Could not download image: {e}') from e
    if not image_data:
        raise HTTPException(status_code=400, detail='Could not download image')
    return _store_manual_image(artist_id, image_data, original_url=url)


@router.post('/{artist_id}/image/upload')
def upload_artist_image(artist_id: int, req: ArtistImageUploadRequest, _auth: dict = Depends(require_rules_manage)):
    """Store uploaded base64 image bytes as the artist's primary image, up to 10 MB."""
    payload = (req.data or '').strip()
    if ',' in payload and payload.lower().startswith('data:'):
        payload = payload.split(',', 1)[1]
    # Checked on the encoded text first, so an oversized body is never decoded.
    if len(payload) > (MAX_IMAGE_BYTES * 4) // 3 + 4:
        raise HTTPException(status_code=413, detail='Image is larger than 10 MB')
    try:
        image_data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(status_code=400, detail='Image data is not valid base64') from e
    if not image_data:
        raise HTTPException(status_code=400, detail='Image data is empty')
    if len(image_data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail='Image is larger than 10 MB')
    return _store_manual_image(artist_id, image_data)


@router.post('/{artist_id}/image/select/{image_id}')
def select_artist_primary_image(artist_id: int, image_id: int, _auth: dict = Depends(require_rules_manage)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT id FROM library_artist_images WHERE id = %s AND artist_id = %s', (image_id, artist_id)
            )
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail='Image not found for this artist')
            _set_primary_image(cursor, artist_id, image_id)
        conn.commit()
        return {'status': 'ok', 'artist_id': artist_id, 'image_id': image_id}
    finally:
        conn.close()


@router.post('/{artist_id}/image/clear')
def clear_artist_primary_image(artist_id: int, _auth: dict = Depends(require_rules_manage)):
    """Unsets the artist's primary image.

    The stored image rows and files are kept so a previously fetched image can be
    re-selected from the manager; only the artist's pointer to it is removed. The
    status becomes `cleared`, which the bulk run (started on every boot) and a plain
    single-artist fetch leave alone -- with `none` the next restart fetched the
    portrait that had just been removed.
    """
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT id FROM library_artists WHERE id = %s', (artist_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail='Artist not found')
            cursor.execute('UPDATE library_artist_images SET is_primary = 0 WHERE artist_id = %s', (artist_id,))
            cursor.execute(
                """
                UPDATE library_artists
                SET primary_image_id = NULL, image_updated_at = NOW(), image_status = 'cleared'
                WHERE id = %s
            """,
                (artist_id,),
            )
        conn.commit()
        return {'status': 'ok', 'artist_id': artist_id}
    finally:
        conn.close()


@router.get('/{artist_name}/image')
def get_artist_image(artist_name: str):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                '\n                SELECT i.cached_path\n                FROM library_artists a\n                JOIN library_artist_images i ON a.primary_image_id = i.id\n                WHERE a.name = %s\n            ',
                (artist_name,),
            )
            row = cursor.fetchone()
            if row and row['cached_path'] and os.path.exists(row['cached_path']):
                return FileResponse(row['cached_path'])
            # No lookup is started here, and none ever was: a background task attached to
            # a request that ends in an exception is dropped by Starlette, so the
            # `add_task(trigger_fetch)` this line used to carry never ran once. Keep it
            # that way -- since !884 every uncovered track row asks for its artist's
            # portrait, and a lookup per miss would queue a MusicBrainz+Spotify round trip
            # for each of them. The bulk run (`/fetch-missing`, and start-up) is the path.
            raise HTTPException(status_code=404, detail='Artist image not found.')
    finally:
        conn.close()


@router.post('/fetch-missing')
@router.post('/fetch-images')
def fetch_missing_images(background_tasks: BackgroundTasks, _auth: dict = Depends(require_rules_manage)):
    """
    Triggers a background task to fetch missing artist images for all artists.
    """
    logger.info('fetch-missing images endpoint called')
    if fetch_progress['active']:
        logger.warning('Fetch already in progress')
        return {'status': 'error', 'message': 'Fetch already in progress'}
    background_tasks.add_task(run_fetch_missing)
    return {'status': 'ok', 'message': 'Fetching missing artist images started in background'}


@router.post('/{artist_id}/fetch-image')
def fetch_artist_image_manual(
    artist_id: int,
    background_tasks: BackgroundTasks,
    force: bool = False,
    _auth: dict = Depends(require_rules_manage),
):
    """Look up a new portrait for one artist in the background.

    An artist whose portrait was cleared by hand is skipped unless `force=true`.
    """
    background_tasks.add_task(trigger_fetch_by_id, artist_id, force)
    return {'status': 'ok', 'message': f'Fetching image for artist ID {artist_id} started'}


def run_fetch_missing():
    logger.info('Background task run_fetch_missing started')
    fetch_progress.update(
        {
            'active': True,
            'total': 0,
            'current': 0,
            'last_artist': None,
            'status': 'initializing',
            'message': 'Starting background fetch process...',
        }
    )
    try:
        logger.info('Importing ArtistImageFetcher...')
        from services.music_manager.artist_image_fetcher.fetcher import ArtistImageFetcher

        logger.info('Connecting to database...')
        conn = get_db_connection()
        if not conn:
            logger.error('Global background fetch failed: Database connection failed')
            fetch_progress.update({'active': False, 'status': 'failed', 'message': 'Database connection failed'})
            return
        try:
            fetcher = ArtistImageFetcher(db_conn=conn)
            if fetcher.blind:
                # Without a provider this loop would walk 45.000 names and learn nothing
                # -- which is what it did from 2026-08-22 to 2026-09-21, recording every
                # one of them as failed. Say so instead, where the Beheer page reads it.
                message = (
                    'Geen image provider geconfigureerd: zet de Spotify client id en secret '
                    '(Beheer > Config, of SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET) en start opnieuw.'
                )
                logger.error(message)
                fetch_progress.update({'active': False, 'status': 'failed', 'message': message})
                return
            with conn.cursor() as cursor:
                cursor.execute('SELECT COUNT(*) as count FROM library_artists')
                total_artists = cursor.fetchone()['count']
                logger.info(f'Database contains {total_artists} total artists in library_artists')
                # An artist we already looked for and could not find is retried, but not on
                # every boot. This runs at startup over every artist without an image, and
                # without the cooldown that meant re-asking each of tens of thousands of
                # hopeless names on each restart -- most of this library is festival rips and
                # bootleg aliases that no image provider has ever heard of. The names do not
                # become findable in the meantime, so the retry only cost a third-party API
                # several seconds per artist, forever.
                retry_after_days = int(os.getenv('ARTIST_IMAGE_RETRY_AFTER_DAYS', '30'))
                cursor.execute(
                    '''
                    SELECT id, name
                    FROM library_artists
                    WHERE primary_image_id IS NULL
                      AND (image_status IS NULL OR image_status <> 'cleared')
                      AND (image_status IS NULL
                           OR image_status <> 'failed'
                           OR image_updated_at IS NULL
                           OR image_updated_at < NOW() - INTERVAL %s DAY)
                    ORDER BY image_updated_at ASC, name ASC
                ''',
                    (retry_after_days,),
                )
                artists = cursor.fetchall()
                logger.info(
                    f'Query returned {len(artists)} artists needing images '
                    f'(no image, and no failed attempt in the last {retry_after_days} days)'
                )
                if not artists:
                    logger.info('No artists found with missing images.')
                    fetch_progress.update(
                        {'active': False, 'status': 'completed', 'message': 'No artists found with missing images.'}
                    )
                    return
                fetch_progress.update(
                    {
                        'active': True,
                        'total': len(artists),
                        'current': 0,
                        'last_artist': None,
                        'status': 'running',
                        'message': f'Processing {len(artists)} artists',
                    }
                )
                logger.info(f'Starting background fetch for {len(artists)} artists')
                fetcher.start_run()
                success_count = 0
                failed_count = 0
                for i, artist in enumerate(artists):
                    fetch_progress['current'] = i + 1
                    fetch_progress['last_artist'] = artist['name']
                    fetch_progress['message'] = f"Fetching for {artist['name']} ({i + 1}/{len(artists)})"
                    try:
                        if fetcher.fetch_for_artist(artist['id'], artist['name']):
                            success_count += 1
                        else:
                            failed_count += 1
                    except Exception as e:
                        logger.error(f"Failed to fetch for {artist['name']}: {e}")
                        failed_count += 1
                logger.info('Background fetch for missing artist images completed.')
                # One WARNING for the whole run when artists were deferred or the run
                # had to pause for a rate limit -- never one per artist.
                fetcher.log_run_summary()
                fetch_progress.update(
                    {
                        'active': False,
                        'status': 'completed',
                        'message': f'Completed: {success_count} succeeded, {failed_count} failed',
                    }
                )
                try:
                    from services.common.Helpers.EventService import event_service

                    event_service.emit(
                        level='INFO',
                        title='Artist Image Fetcher',
                        message=f'Background fetch completed.\nSucceeded: {success_count}\nFailed: {failed_count}',
                        source='music-manager',
                        context={'succeeded': success_count, 'failed': failed_count},
                        push=True,
                    )
                except Exception as e:
                    logger.warning(f'Failed to send completion notification: {e}')
        finally:
            conn.close()
    except Exception as e:
        logger.error(f'Global background fetch failed: {e}')
        fetch_progress.update({'active': False, 'status': 'failed', 'message': str(e)})


def trigger_fetch_by_id(artist_id: int, force: bool = False):
    """Background task behind `/fetch-image`; `force` also re-fetches a cleared portrait."""
    try:
        from services.music_manager.artist_image_fetcher.fetcher import ArtistImageFetcher

        conn = get_db_connection()
        if not conn:
            return
        try:
            fetcher = ArtistImageFetcher(db_conn=conn)
            with conn.cursor() as cursor:
                cursor.execute('SELECT name FROM library_artists WHERE id = %s', (artist_id,))
                row = cursor.fetchone()
                if row:
                    fetcher.fetch_for_artist(artist_id, row['name'], force_refresh=True, override_cleared=force)
        finally:
            conn.close()
    except Exception as e:
        print(f'Background fetch failed for artist ID {artist_id}: {e}')


def sync_artist_images_to_server(muma_conn, server_conn):
    """
    Syncs primary artist images from MuMa MariaDB to Music Management Server SQLite DB.

    Reads first and writes only what differs, one short transaction per artist that needs
    one. The first version wrote every artist's preferred_artwork_id unconditionally inside
    a single transaction: 11.762 UPDATEs, thirty seconds, and the server's write lock held
    the whole time. The server does not wait for that lock -- its transactions read before
    they write, and SQLite refuses a read-to-write upgrade at once while another connection
    holds the lock, busy timeout or not -- so the request that needed it, a rating or a
    scrobble, was aborted. After the first pass nearly every artist already points at the
    right artwork, so nearly nothing is written and the lock is barely taken.
    """
    print('Syncing artist images to Music Management Server...')
    try:
        with muma_conn.cursor() as muma_cursor:
            muma_cursor.execute(
                '\n                SELECT a.name as artist_name, i.cached_path, i.width, i.height, i.mime_type, i.file_size\n                FROM library_artists a\n                JOIN library_artist_images i ON a.primary_image_id = i.id\n                WHERE i.cached_path IS NOT NULL\n            '
            )
            images = muma_cursor.fetchall()
            server_cursor = server_conn.cursor()
            for img in images:
                artist_name = img['artist_name']
                abs_path = img['cached_path']
                server_cursor.execute('SELECT id, preferred_artwork_id FROM artist WHERE name = ?', (artist_name,))
                artist_row = server_cursor.fetchone()
                if not artist_row:
                    continue
                artist_id, current_artwork_id = artist_row[0], artist_row[1]
                server_cursor.execute('SELECT id FROM image WHERE absolute_file_path = ?', (abs_path,))
                image_row = server_cursor.fetchone()
                image_id = None
                if image_row:
                    image_id = image_row[0]
                else:
                    stem = os.path.splitext(os.path.basename(abs_path))[0]
                    server_cursor.execute(
                        '\n                        INSERT INTO image (version, absolute_file_path, stem, file_size, width, height, mime_type)\n                        VALUES (?, ?, ?, ?, ?, ?, ?)\n                    ',
                        (1, abs_path, stem, img['file_size'], img['width'], img['height'], img['mime_type']),
                    )
                    image_id = server_cursor.lastrowid
                server_cursor.execute('SELECT id FROM artwork WHERE image_id = ?', (image_id,))
                artwork_row = server_cursor.fetchone()
                artwork_id = None
                if artwork_row:
                    artwork_id = artwork_row[0]
                else:
                    server_cursor.execute('INSERT INTO artwork (version, image_id) VALUES (?, ?)', (1, image_id))
                    artwork_id = server_cursor.lastrowid
                if current_artwork_id != artwork_id:
                    server_cursor.execute(
                        'UPDATE artist SET preferred_artwork_id = ? WHERE id = ?', (artwork_id, artist_id)
                    )
                # Commit per artist, so a write transaction never spans more than the
                # three statements above. A no-op commit costs nothing.
                server_conn.commit()
            print(f'Synced {len(images)} artist images to Music Management Server')
    except Exception as e:
        print(f'Failed to sync artist images to Music Management Server: {e}')
