import os
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Header, Depends
from fastapi.responses import FileResponse
from services.music_manager.database import get_db_connection
router = APIRouter(tags=['artists'])
logger = logging.getLogger(__name__)
fetch_progress = {'active': False, 'total': 0, 'current': 0, 'last_artist': None, 'status': 'idle', 'message': None}
API_KEY = os.getenv('API_KEY') or os.getenv('MUMA_API_KEY') or '453ecd33-3cb2-4ca4-a531-1677330bbaee'

def verify_api_key(x_api_key: Optional[str]=Header(None)):
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
                cursor.execute('\n                    SELECT id, name\n                    FROM library_artists\n                    WHERE primary_image_id IS NULL\n                ')
                all_missing = cursor.fetchall()
                logger.info(f'Total artists with primary_image_id IS NULL: {len(all_missing)}')
                cursor.execute("\n                    SELECT id, name\n                    FROM library_artists\n                    WHERE primary_image_id IS NULL\n                    AND (image_status IS NULL OR image_status = 'failed')\n                    ORDER BY image_updated_at ASC, name ASC\n                ")
                artists = cursor.fetchall()
                logger.info(f'Query (filtered by status) returned {len(artists)} artists needing images')
                if not artists:
                    logger.info('No artists found with missing images.')
                    if all_missing:
                        cursor.execute('\n                            SELECT image_status, COUNT(*) as count \n                            FROM library_artists \n                            WHERE primary_image_id IS NULL \n                            GROUP BY image_status\n                        ')
                        stats = cursor.fetchall()
                        logger.info(f'Stats for NULL primary_image_id: {stats}')
                        logger.info("Tip: If many are 'active' but primary_image_id is NULL, there might be a database inconsistency.")
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
                    from services.common.Helpers.NotificationService import notification_service
                    notification_service.send_notification(title='Artist Image Fetcher', message=f'Background fetch completed.\nSucceeded: {success_count}\nFailed: {failed_count}', topic='artist-images')
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

def sync_artist_images_to_lms(muma_conn, lms_conn):
    """
    Syncs primary artist images from MuMa MariaDB to LMS SQLite DB.
    """
    print('Syncing artist images to LMS...')
    try:
        with muma_conn.cursor() as muma_cursor:
            muma_cursor.execute('\n                SELECT a.name as artist_name, i.cached_path, i.width, i.height, i.mime_type, i.file_size\n                FROM library_artists a\n                JOIN library_artist_images i ON a.primary_image_id = i.id\n                WHERE i.cached_path IS NOT NULL\n            ')
            images = muma_cursor.fetchall()
            lms_cursor = lms_conn.cursor()
            for img in images:
                artist_name = img['artist_name']
                abs_path = img['cached_path']
                lms_cursor.execute('SELECT id FROM artist WHERE name = ?', (artist_name,))
                artist_row = lms_cursor.fetchone()
                if not artist_row:
                    continue
                artist_id = artist_row[0]
                lms_cursor.execute('SELECT id FROM image WHERE absolute_file_path = ?', (abs_path,))
                image_row = lms_cursor.fetchone()
                image_id = None
                if image_row:
                    image_id = image_row[0]
                else:
                    stem = os.path.splitext(os.path.basename(abs_path))[0]
                    lms_cursor.execute('\n                        INSERT INTO image (version, absolute_file_path, stem, file_size, width, height, mime_type)\n                        VALUES (?, ?, ?, ?, ?, ?, ?)\n                    ', (1, abs_path, stem, img['file_size'], img['width'], img['height'], img['mime_type']))
                    image_id = lms_cursor.lastrowid
                lms_cursor.execute('SELECT id FROM artwork WHERE image_id = ?', (image_id,))
                artwork_row = lms_cursor.fetchone()
                artwork_id = None
                if artwork_row:
                    artwork_id = artwork_row[0]
                else:
                    lms_cursor.execute('INSERT INTO artwork (version, image_id) VALUES (?, ?)', (1, image_id))
                    artwork_id = lms_cursor.lastrowid
                lms_cursor.execute('UPDATE artist SET preferred_artwork_id = ? WHERE id = ?', (artwork_id, artist_id))
            lms_conn.commit()
            print(f'Synced {len(images)} artist images to LMS')
    except Exception as e:
        print(f'Failed to sync artist images to LMS: {e}')