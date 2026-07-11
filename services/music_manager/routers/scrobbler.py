import os
import time
from datetime import datetime
from typing import Optional
import requests
from fastapi import APIRouter, HTTPException, BackgroundTasks, Header, Depends
from pydantic import BaseModel
from services.music_manager.database import get_db_connection
router = APIRouter(tags=['scrobble'])
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

class ScrobbleEvent(BaseModel):
    artist_name: str
    track_title: str
    album_name: Optional[str] = None
    mbid_track: Optional[str] = None
    mbid_artist: Optional[str] = None
    listened_at: Optional[int] = None
    username: str
    source: str = 'manual'

def init_db(cursor):
    cursor.execute('\n        CREATE TABLE IF NOT EXISTS scrobble_listens (\n            id INT AUTO_INCREMENT PRIMARY KEY,\n            track_id INT,\n            listened_at TIMESTAMP NOT NULL,\n            username VARCHAR(255) NOT NULL,\n            source VARCHAR(50),\n            mbid_track VARCHAR(36),\n            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n            UNIQUE KEY (username, listened_at, track_id)\n        )\n    ')
    cursor.execute('\n        CREATE TABLE IF NOT EXISTS scrobble_unmatched_listens (\n            id INT AUTO_INCREMENT PRIMARY KEY,\n            artist_name VARCHAR(512),\n            track_title VARCHAR(512),\n            album_name VARCHAR(512),\n            mbid_track VARCHAR(36),\n            mbid_artist VARCHAR(36),\n            listened_at TIMESTAMP NOT NULL,\n            username VARCHAR(255) NOT NULL,\n            source VARCHAR(50),\n            data JSON,\n            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n            UNIQUE KEY (username, listened_at, artist_name, track_title)\n        )\n    ')
    cursor.execute('\n        CREATE TABLE IF NOT EXISTS scrobble_imports (\n            id INT AUTO_INCREMENT PRIMARY KEY,\n            username VARCHAR(255) NOT NULL,\n            lb_username VARCHAR(255) NOT NULL,\n            status VARCHAR(50) NOT NULL,\n            total_found INT DEFAULT 0,\n            processed INT DEFAULT 0,\n            last_error TEXT,\n            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n            finished_at TIMESTAMP NULL\n        )\n    ')

@router.post('/event')
def handle_scrobble_event(event: ScrobbleEvent, _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute('\n                SELECT t.id FROM library_tracks t\n                JOIN library_artists a ON t.primary_artist_id = a.id\n                WHERE a.name = %s AND t.title = %s\n                LIMIT 1\n            ', (event.artist_name, event.track_title))
            row = cursor.fetchone()
            listened_at = datetime.fromtimestamp(event.listened_at) if event.listened_at else datetime.now()
            if row:
                track_id = row['id']
                cursor.execute('\n                    INSERT INTO scrobble_listens (track_id, listened_at, username, source, mbid_track)\n                    VALUES (%s, %s, %s, %s, %s)\n                    ON DUPLICATE KEY UPDATE mbid_track = VALUES(mbid_track)\n                ', (track_id, listened_at, event.username, event.source, event.mbid_track))
            else:
                cursor.execute('\n                    INSERT INTO scrobble_unmatched_listens (artist_name, track_title, album_name, mbid_track, mbid_artist, listened_at, username, source)\n                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)\n                    ON DUPLICATE KEY UPDATE artist_name = VALUES(artist_name)\n                ', (event.artist_name, event.track_title, event.album_name, event.mbid_track, event.mbid_artist, listened_at, event.username, event.source))
            conn.commit()
            return {'status': 'success', 'matched': row is not None}
    finally:
        conn.close()

def _process_listens_page(listens, conn, username, import_id, total_found):
    processed = 0
    max_ts = None
    with conn.cursor() as cursor:
        cursor.execute('UPDATE scrobble_imports SET total_found = %s WHERE id = %s', (total_found, import_id))
        conn.commit()
        for listen in listens:
            metadata = listen.get('track_metadata', {})
            artist_name = metadata.get('artist_name')
            track_title = metadata.get('track_name')
            album_name = metadata.get('release_name')
            listened_at_ts = listen.get('listened_at')
            if max_ts is None or listened_at_ts < max_ts:
                max_ts = listened_at_ts
            if not artist_name or not track_title or (not listened_at_ts):
                continue
            listened_at = datetime.fromtimestamp(listened_at_ts)
            cursor.execute('\n                SELECT t.id FROM library_tracks t\n                JOIN library_artists a ON t.primary_artist_id = a.id\n                WHERE a.name = %s AND t.title = %s\n                LIMIT 1\n            ', (artist_name, track_title))
            row = cursor.fetchone()
            if row:
                track_id = row['id']
                cursor.execute('\n                    INSERT INTO scrobble_listens (track_id, listened_at, username, source)\n                    VALUES (%s, %s, %s, %s)\n                    ON DUPLICATE KEY UPDATE track_id = track_id\n                ', (track_id, listened_at, username, 'listenbrainz'))
            else:
                cursor.execute('\n                    INSERT INTO scrobble_unmatched_listens (artist_name, track_title, album_name, listened_at, username, source)\n                    VALUES (%s, %s, %s, %s, %s, %s)\n                    ON DUPLICATE KEY UPDATE artist_name = artist_name\n                ', (artist_name, track_title, album_name, listened_at, username, 'listenbrainz'))
            processed += 1
            if processed % 10 == 0:
                cursor.execute('UPDATE scrobble_imports SET processed = %s WHERE id = %s', (processed, import_id))
                conn.commit()
    return (processed, max_ts)

def run_listenbrainz_import(import_id: int, username: str, lb_username: str, token: Optional[str]=None):
    conn = get_db_connection()
    if not conn:
        print(f'Failed to connect to DB for import {import_id}')
        return
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE scrobble_imports SET status = 'running' WHERE id = %s", (import_id,))
            conn.commit()
        base_url = 'https://api.listenbrainz.org/1'
        headers = {}
        if token:
            headers['Authorization'] = f'Token {token}'
        processed_total = 0
        total_found = 0
        max_ts = None
        pages_to_fetch = 100
        for page in range(pages_to_fetch):
            params = {'count': 100}
            if max_ts:
                params['max_ts'] = max_ts
            print(f'Fetching listens for {lb_username} from ListenBrainz (page {page + 1}, max_ts={max_ts})...')
            response = requests.get(f'{base_url}/user/{lb_username}/listens', params=params, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            listens = data.get('payload', {}).get('listens', [])
            if not listens:
                print('No more listens found.')
                break
            total_found += len(listens)
            processed_page, page_max_ts = _process_listens_page(listens, conn, username, import_id, total_found)
            processed_total += processed_page
            max_ts = page_max_ts
            time.sleep(1)
            if len(listens) < 100:
                break
            max_ts = max_ts - 1
        with conn.cursor() as cursor:
            cursor.execute("\n                UPDATE scrobble_imports\n                SET status = 'completed', processed = %s, finished_at = CURRENT_TIMESTAMP\n                WHERE id = %s\n            ", (processed_total, import_id))
            conn.commit()
            print(f'Import {import_id} completed. Processed {processed_total} listens.')
    except Exception as e:
        print(f'Error during import {import_id}: {str(e)}')
        try:
            with conn.cursor() as cursor:
                cursor.execute("UPDATE scrobble_imports SET status = 'failed', last_error = %s WHERE id = %s", (str(e), import_id))
                conn.commit()
        except Exception:
            pass
    finally:
        conn.close()

class ImportRequest(BaseModel):
    username: str
    lb_username: Optional[str] = None
    token: Optional[str] = None

@router.get('/import/latest')
def get_latest_imports():
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT * FROM scrobble_imports ORDER BY started_at DESC LIMIT 10')
            return cursor.fetchall()
    finally:
        conn.close()

@router.post('/import/listenbrainz')
def trigger_lb_import(req: ImportRequest, background_tasks: BackgroundTasks):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('\n                INSERT INTO scrobble_imports (username, lb_username, status)\n                VALUES (%s, %s, %s)\n            ', (req.username, req.lb_username or req.username, 'pending'))
            import_id = cursor.lastrowid
            conn.commit()
            background_tasks.add_task(run_listenbrainz_import, import_id, req.username, req.lb_username or req.username, req.token)
            return {'status': 'ok', 'import_id': import_id, 'lb_username': req.lb_username or req.username}
    finally:
        conn.close()