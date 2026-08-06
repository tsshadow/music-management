import base64
import binascii
import logging
import os

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from services.music_manager.database import get_db_connection

router = APIRouter(tags=['artists'])
logger = logging.getLogger(__name__)
fetch_progress = {'active': False, 'total': 0, 'current': 0, 'last_artist': None, 'status': 'idle', 'message': None}
API_KEY = os.getenv('API_KEY') or os.getenv('MUMA_API_KEY') or '00000000-0000-4000-8000-000000000000'

def verify_api_key(x_api_key: str | None=Header(None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail='Missing API Key')
    if API_KEY and x_api_key == API_KEY:
        return {'type': 'system'}
    from services.music_manager.routers.users import verify_token
    try:
        res = verify_token(x_api_key)
        if res.get('status') == 'ok':
            return res
    except Exception:
        pass
    raise HTTPException(status_code=401, detail='Invalid API key')
STORAGE_PATH = os.getenv('STORAGE_PATH', '/mnt/music/artists')

def init_db(cursor):
    cursor.execute('\n        CREATE TABLE IF NOT EXISTS library_artist_images (\n            id INT AUTO_INCREMENT PRIMARY KEY,\n            artist_id INT NOT NULL,\n            source VARCHAR(50),\n            source_id VARCHAR(255),\n            original_url TEXT,\n            cached_path TEXT,\n            public_path TEXT,\n            width INT,\n            height INT,\n            mime_type VARCHAR(50),\n            file_size INT,\n            confidence INT DEFAULT 0,\n            is_primary TINYINT(1) DEFAULT 0,\n            created_at DATETIME,\n            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,\n            INDEX (artist_id),\n            INDEX (is_primary)\n        )\n    ')
    cursor.execute('\n        CREATE TABLE IF NOT EXISTS artist_external_ids (\n            artist_id INT NOT NULL,\n            source VARCHAR(50) NOT NULL,\n            external_id VARCHAR(255) NOT NULL,\n            created_at DATETIME,\n            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,\n            PRIMARY KEY (artist_id, source)\n        )\n    ')
    columns_to_add = [('primary_image_id', 'INT NULL'), ('image_updated_at', 'DATETIME NULL'), ('image_status', 'VARCHAR(50) NULL'), ('mbid', 'VARCHAR(100) NULL')]
    for col_name, col_type in columns_to_add:
        cursor.execute(f"SHOW COLUMNS FROM library_artists LIKE '{col_name}'")
        if not cursor.fetchone():
            cursor.execute(f'ALTER TABLE library_artists ADD COLUMN {col_name} {col_type}')

@router.get('/search')
def search_artist_images(q: str='', _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            if q == '':
                cursor.execute('\n                    SELECT a.id, a.name, a.primary_image_id, i.width, i.height, i.mime_type, a.image_status\n                    FROM library_artists a\n                    JOIN library_artist_images i ON a.primary_image_id = i.id\n                    ORDER BY a.name\n                    LIMIT 100\n                ')
            else:
                cursor.execute('\n                    SELECT a.id, a.name, a.primary_image_id, i.width, i.height, i.mime_type, a.image_status\n                    FROM library_artists a\n                    JOIN library_artist_images i ON a.primary_image_id = i.id\n                    WHERE a.name LIKE %s\n                    ORDER BY a.name\n                    LIMIT 100\n                ', (f'%{q}%',))
            return cursor.fetchall()
    finally:
        conn.close()

@router.get('/search-all')
def search_all_artists(q: str='', _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            if q == '':
                cursor.execute('\n                    SELECT a.id, a.name, a.primary_image_id, a.image_status\n                    FROM library_artists a\n                    ORDER BY a.name\n                    LIMIT 100\n                ')
            else:
                cursor.execute('\n                    SELECT a.id, a.name, a.primary_image_id, a.image_status\n                    FROM library_artists a\n                    WHERE a.name LIKE %s\n                    ORDER BY a.name\n                    LIMIT 100\n                ', (f'%{q}%',))
            return cursor.fetchall()
    finally:
        conn.close()

@router.get('/images/stats')
def get_artist_image_stats(_auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) as total FROM library_artists')
            total = cursor.fetchone()['total']
            cursor.execute('SELECT COUNT(*) as with_image FROM library_artists WHERE primary_image_id IS NOT NULL')
            with_image = cursor.fetchone()['with_image']
            return {'total_artists': total, 'artists_with_images': with_image, 'artists_without_images': total - with_image}
    finally:
        conn.close()

@router.get('/fetch-progress')
def get_fetch_progress(_auth: dict=Depends(verify_api_key)):
    return fetch_progress

# --- Artist image manager -------------------------------------------------
#
# The manager UI talks to MuMa through LMS's `MumaResource` proxy (`/muma/api/...`),
# which imposes two constraints on the routes below:
#   * every path ending in exactly "/image" is intercepted by the proxy and turned
#     into a GET of the artist-image file, so mutations live on deeper sub-paths
#     ("/image/url", "/image/upload", "/image/clear", "/image/select/{id}");
#   * DELETE is forwarded to MuMa as a POST, so mutations are POST-only.

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
def manage_search_artists(q: str='', only: str='all', limit: int=60, offset: int=0, _auth: dict=Depends(verify_api_key)):
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
            cursor.execute(f'''
                SELECT a.id, a.name, a.primary_image_id, a.image_status, a.image_updated_at,
                       i.width, i.height, i.mime_type, i.file_size, i.source, i.original_url
                FROM library_artists a
                LEFT JOIN library_artist_images i ON a.primary_image_id = i.id
                {where_sql}
                ORDER BY a.name
                LIMIT %s OFFSET %s
            ''', tuple(params) + (limit, offset))
            items = []
            for artist in cursor.fetchall():
                updated_at = artist.get('image_updated_at')
                items.append({
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
                    'original_url': artist.get('original_url')
                })
            return {'items': items, 'total': total, 'limit': limit, 'offset': offset}
    finally:
        conn.close()

@router.get('/{artist_id}/images')
def list_artist_images(artist_id: int, _auth: dict=Depends(verify_api_key)):
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
            cursor.execute('''
                SELECT id, source, source_id, original_url, cached_path, public_path,
                       width, height, mime_type, file_size, confidence, is_primary
                FROM library_artist_images
                WHERE artist_id = %s
                ORDER BY is_primary DESC, confidence DESC, id DESC
            ''', (artist_id,))
            images = []
            for image in cursor.fetchall():
                image = dict(image)
                image['exists_on_disk'] = bool(image.get('cached_path')) and os.path.exists(image['cached_path'])
                images.append(image)
            return {'artist_id': artist['id'], 'artist_name': artist['name'], 'primary_image_id': artist['primary_image_id'], 'images': images}
    finally:
        conn.close()

def _set_primary_image(cursor, artist_id: int, image_id: int):
    cursor.execute('UPDATE library_artist_images SET is_primary = 0 WHERE artist_id = %s', (artist_id,))
    cursor.execute('UPDATE library_artist_images SET is_primary = 1 WHERE id = %s', (image_id,))
    cursor.execute("""
        UPDATE library_artists
        SET primary_image_id = %s, image_updated_at = NOW(), image_status = 'active'
        WHERE id = %s
    """, (image_id, artist_id))

def _store_manual_image(artist_id: int, image_data: bytes, original_url: str | None=None):
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
            cursor.execute('''
                INSERT INTO library_artist_images
                (artist_id, source, source_id, original_url, cached_path, public_path,
                 width, height, mime_type, file_size, confidence, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ''', (artist_id, 'manual', None, original_url, meta['cached_path'], meta['public_path'], meta['width'], meta['height'], meta['mime_type'], meta['file_size'], 100))
            image_id = cursor.lastrowid
            _set_primary_image(cursor, artist_id, image_id)
        conn.commit()
        return {'status': 'ok', 'artist_id': artist_id, 'artist_name': artist['name'], 'image_id': image_id, 'width': meta['width'], 'height': meta['height'], 'mime_type': meta['mime_type'], 'file_size': meta['file_size']}
    finally:
        conn.close()

@router.post('/{artist_id}/image/url')
def set_artist_image_from_url(artist_id: int, req: ArtistImageUrlRequest, _auth: dict=Depends(verify_api_key)):
    url = (req.url or '').strip()
    if not url.lower().startswith(('http://', 'https://')):
        raise HTTPException(status_code=400, detail='Only http(s) image URLs are supported')
    from services.music_manager.artist_image_fetcher.storage import ImageDownloader
    try:
        image_data = ImageDownloader().download(url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f'Could not download image: {e}') from e
    if not image_data:
        raise HTTPException(status_code=400, detail='Could not download image')
    return _store_manual_image(artist_id, image_data, original_url=url)

@router.post('/{artist_id}/image/upload')
def upload_artist_image(artist_id: int, req: ArtistImageUploadRequest, _auth: dict=Depends(verify_api_key)):
    payload = (req.data or '').strip()
    if ',' in payload and payload.lower().startswith('data:'):
        payload = payload.split(',', 1)[1]
    try:
        image_data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(status_code=400, detail='Image data is not valid base64') from e
    if not image_data:
        raise HTTPException(status_code=400, detail='Image data is empty')
    return _store_manual_image(artist_id, image_data)

@router.post('/{artist_id}/image/select/{image_id}')
def select_artist_primary_image(artist_id: int, image_id: int, _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT id FROM library_artist_images WHERE id = %s AND artist_id = %s', (image_id, artist_id))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail='Image not found for this artist')
            _set_primary_image(cursor, artist_id, image_id)
        conn.commit()
        return {'status': 'ok', 'artist_id': artist_id, 'image_id': image_id}
    finally:
        conn.close()

@router.post('/{artist_id}/image/clear')
def clear_artist_primary_image(artist_id: int, _auth: dict=Depends(verify_api_key)):
    """Unsets the artist's primary image.

    The stored image rows and files are kept so a previously fetched image can be
    re-selected from the manager; only the artist's pointer to it is removed.
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
            cursor.execute("""
                UPDATE library_artists
                SET primary_image_id = NULL, image_updated_at = NOW(), image_status = 'none'
                WHERE id = %s
            """, (artist_id,))
        conn.commit()
        return {'status': 'ok', 'artist_id': artist_id}
    finally:
        conn.close()

@router.get('/{artist_name}/image')
def get_artist_image(artist_name: str, background_tasks: BackgroundTasks):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute('\n                SELECT i.cached_path\n                FROM library_artists a\n                JOIN library_artist_images i ON a.primary_image_id = i.id\n                WHERE a.name = %s\n            ', (artist_name,))
            row = cursor.fetchone()
            if row and row['cached_path'] and os.path.exists(row['cached_path']):
                return FileResponse(row['cached_path'])
            background_tasks.add_task(trigger_fetch, artist_name)
            raise HTTPException(status_code=404, detail='Artist image not found. Fetching triggered.')
    finally:
        conn.close()

@router.post('/fetch-missing')
@router.post('/fetch-images')
def fetch_missing_images(background_tasks: BackgroundTasks, _auth: dict=Depends(verify_api_key)):
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
def fetch_artist_image_manual(artist_id: int, background_tasks: BackgroundTasks, _auth: dict=Depends(verify_api_key)):
    background_tasks.add_task(trigger_fetch_by_id, artist_id)
    return {'status': 'ok', 'message': f'Fetching image for artist ID {artist_id} started'}

def run_fetch_missing():
    logger.info('Background task run_fetch_missing started')
    fetch_progress.update({'active': True, 'total': 0, 'current': 0, 'last_artist': None, 'status': 'initializing', 'message': 'Starting background fetch process...'})
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
            with conn.cursor() as cursor:
                cursor.execute('SELECT COUNT(*) as count FROM library_artists')
                total_artists = cursor.fetchone()['count']
                logger.info(f'Database contains {total_artists} total artists in library_artists')
                cursor.execute('''
                    SELECT id, name
                    FROM library_artists
                    WHERE primary_image_id IS NULL
                    ORDER BY image_updated_at ASC, name ASC
                ''')
                artists = cursor.fetchall()
                logger.info(f'Query returned {len(artists)} artists needing images (primary_image_id IS NULL)')
                if not artists:
                    logger.info('No artists found with missing images.')
                    fetch_progress.update({'active': False, 'status': 'completed', 'message': 'No artists found with missing images.'})
                    return
                fetch_progress.update({'active': True, 'total': len(artists), 'current': 0, 'last_artist': None, 'status': 'running', 'message': f'Processing {len(artists)} artists'})
                logger.info(f'Starting background fetch for {len(artists)} artists')
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
                fetch_progress.update({'active': False, 'status': 'completed', 'message': f'Completed: {success_count} succeeded, {failed_count} failed'})
                try:
                    from services.common.Helpers.EventService import event_service
                    event_service.emit(
                        level='INFO', title='Artist Image Fetcher',
                        message=f'Background fetch completed.\nSucceeded: {success_count}\nFailed: {failed_count}',
                        source='music-manager', context={'succeeded': success_count, 'failed': failed_count},
                        push=True,
                    )
                except Exception as e:
                    logger.warning(f'Failed to send completion notification: {e}')
        finally:
            conn.close()
    except Exception as e:
        logger.error(f'Global background fetch failed: {e}')
        fetch_progress.update({'active': False, 'status': 'failed', 'message': str(e)})

def trigger_fetch_by_id(artist_id: int):
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
                    fetcher.fetch_for_artist(artist_id, row['name'], force_refresh=True)
        finally:
            conn.close()
    except Exception as e:
        print(f'Background fetch failed for artist ID {artist_id}: {e}')

def trigger_fetch(artist_name: str):
    try:
        from services.music_manager.artist_image_fetcher.fetcher import ArtistImageFetcher
        conn = get_db_connection()
        if not conn:
            return
        try:
            fetcher = ArtistImageFetcher(db_conn=conn)
            with conn.cursor() as cursor:
                cursor.execute('SELECT id FROM library_artists WHERE name = %s', (artist_name,))
                row = cursor.fetchone()
                if row:
                    fetcher.fetch_for_artist(row['id'], artist_name)
        finally:
            conn.close()
    except Exception as e:
        print(f'Background fetch failed for {artist_name}: {e}')

def sync_artist_images_to_server(muma_conn, server_conn):
    """
    Syncs primary artist images from MuMa MariaDB to Music Management Server SQLite DB.
    """
    print('Syncing artist images to Music Management Server...')
    try:
        with muma_conn.cursor() as muma_cursor:
            muma_cursor.execute('\n                SELECT a.name as artist_name, i.cached_path, i.width, i.height, i.mime_type, i.file_size\n                FROM library_artists a\n                JOIN library_artist_images i ON a.primary_image_id = i.id\n                WHERE i.cached_path IS NOT NULL\n            ')
            images = muma_cursor.fetchall()
            server_cursor = server_conn.cursor()
            for img in images:
                artist_name = img['artist_name']
                abs_path = img['cached_path']
                server_cursor.execute('SELECT id FROM artist WHERE name = ?', (artist_name,))
                artist_row = server_cursor.fetchone()
                if not artist_row:
                    continue
                artist_id = artist_row[0]
                server_cursor.execute('SELECT id FROM image WHERE absolute_file_path = ?', (abs_path,))
                image_row = server_cursor.fetchone()
                image_id = None
                if image_row:
                    image_id = image_row[0]
                else:
                    stem = os.path.splitext(os.path.basename(abs_path))[0]
                    server_cursor.execute('\n                        INSERT INTO image (version, absolute_file_path, stem, file_size, width, height, mime_type)\n                        VALUES (?, ?, ?, ?, ?, ?, ?)\n                    ', (1, abs_path, stem, img['file_size'], img['width'], img['height'], img['mime_type']))
                    image_id = server_cursor.lastrowid
                server_cursor.execute('SELECT id FROM artwork WHERE image_id = ?', (image_id,))
                artwork_row = server_cursor.fetchone()
                artwork_id = None
                if artwork_row:
                    artwork_id = artwork_row[0]
                else:
                    server_cursor.execute('INSERT INTO artwork (version, image_id) VALUES (?, ?)', (1, image_id))
                    artwork_id = server_cursor.lastrowid
                server_cursor.execute('UPDATE artist SET preferred_artwork_id = ? WHERE id = ?', (artwork_id, artist_id))
            server_conn.commit()
            print(f'Synced {len(images)} artist images to Music Management Server')
    except Exception as e:
        print(f'Failed to sync artist images to Music Management Server: {e}')
