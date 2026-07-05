from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Header, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import os
import time
import json
from services.music_manager.database import get_db_connection

router = APIRouter(prefix="/scrobble", tags=["scrobble"])

API_KEY = os.getenv("API_KEY") or os.getenv("MUMA_API_KEY") or "453ecd33-3cb2-4ca4-a531-1677330bbaee"

def verify_api_key(x_api_key: str = Header(None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return x_api_key

class ScrobbleEvent(BaseModel):
    artist_name: str
    track_title: str
    album_name: Optional[str] = None
    mbid_track: Optional[str] = None
    mbid_artist: Optional[str] = None
    listened_at: Optional[int] = None
    username: str
    source: str = "manual"

def init_db(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scrobble_listens (
            id INT AUTO_INCREMENT PRIMARY KEY,
            track_id INT,
            listened_at TIMESTAMP NOT NULL,
            username VARCHAR(255) NOT NULL,
            source VARCHAR(50),
            mbid_track VARCHAR(36),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY (username, listened_at, track_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scrobble_unmatched_listens (
            id INT AUTO_INCREMENT PRIMARY KEY,
            artist_name VARCHAR(512),
            track_title VARCHAR(512),
            album_name VARCHAR(512),
            mbid_track VARCHAR(36),
            mbid_artist VARCHAR(36),
            listened_at TIMESTAMP NOT NULL,
            username VARCHAR(255) NOT NULL,
            source VARCHAR(50),
            data JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY (username, listened_at, artist_name, track_title)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scrobble_imports (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(255) NOT NULL,
            lb_username VARCHAR(255) NOT NULL,
            status VARCHAR(50) NOT NULL,
            total_found INT DEFAULT 0,
            processed INT DEFAULT 0,
            last_error TEXT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMP NULL
        )
    """)

@router.post("/api/event")
def handle_scrobble_event(event: ScrobbleEvent, api_key: str = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor() as cursor:
            # Simple matching for now
            cursor.execute("""
                SELECT t.id FROM library_tracks t
                JOIN library_artists a ON t.primary_artist_id = a.id
                WHERE a.name = %s AND t.title = %s
                LIMIT 1
            """, (event.artist_name, event.track_title))
            row = cursor.fetchone()
            
            listened_at = datetime.fromtimestamp(event.listened_at) if event.listened_at else datetime.now()
            
            if row:
                track_id = row['id']
                cursor.execute("""
                    INSERT INTO scrobble_listens (track_id, listened_at, username, source, mbid_track)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE mbid_track = VALUES(mbid_track)
                """, (track_id, listened_at, event.username, event.source, event.mbid_track))
            else:
                cursor.execute("""
                    INSERT INTO scrobble_unmatched_listens (artist_name, track_title, album_name, mbid_track, mbid_artist, listened_at, username, source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE artist_name = VALUES(artist_name)
                """, (event.artist_name, event.track_title, event.album_name, event.mbid_track, event.mbid_artist, listened_at, event.username, event.source))
            
            conn.commit()
            return {"status": "success", "matched": row is not None}
    finally:
        conn.close()

def run_listenbrainz_import(import_id: int, username: str, lb_username: str, token: Optional[str] = None):
    conn = get_db_connection()
    if not conn:
        print(f"Failed to connect to DB for import {import_id}")
        return
    
    try:
        # Update status to 'running'
        with conn.cursor() as cursor:
            cursor.execute("UPDATE scrobble_imports SET status = 'running' WHERE id = %s", (import_id,))
            conn.commit()
            
        import requests
        base_url = "https://api.listenbrainz.org/1"
        headers = {}
        if token:
            headers['Authorization'] = f"Token {token}"
            
        processed = 0
        total_found = 0
        max_ts = None
        pages_to_fetch = 100 # Fetch up to 10000 tracks
        
        for page in range(pages_to_fetch):
            params = {'count': 100}
            if max_ts:
                params['max_ts'] = max_ts
                
            print(f"Fetching listens for {lb_username} from ListenBrainz (page {page+1}, max_ts={max_ts})...")
            response = requests.get(f"{base_url}/user/{lb_username}/listens", params=params, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            listens = data.get('payload', {}).get('listens', [])
            
            if not listens:
                print("No more listens found.")
                break
                
            total_found += len(listens)
            
            with conn.cursor() as cursor:
                # Update total found
                cursor.execute("UPDATE scrobble_imports SET total_found = %s WHERE id = %s", (total_found, import_id))
                conn.commit()
                
                for listen in listens:
                    metadata = listen.get('track_metadata', {})
                    artist_name = metadata.get('artist_name')
                    track_title = metadata.get('track_name')
                    album_name = metadata.get('release_name')
                    listened_at_ts = listen.get('listened_at')
                    
                    # Update max_ts for next page
                    if max_ts is None or listened_at_ts < max_ts:
                        max_ts = listened_at_ts
                    
                    if not artist_name or not track_title or not listened_at_ts:
                        continue
                    
                    listened_at = datetime.fromtimestamp(listened_at_ts)
                    
                    # Match track
                    cursor.execute("""
                        SELECT t.id FROM library_tracks t
                        JOIN library_artists a ON t.primary_artist_id = a.id
                        WHERE a.name = %s AND t.title = %s
                        LIMIT 1
                    """, (artist_name, track_title))
                    row = cursor.fetchone()
                    
                    if row:
                        track_id = row['id']
                        cursor.execute("""
                            INSERT INTO scrobble_listens (track_id, listened_at, username, source)
                            VALUES (%s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE track_id = track_id
                        """, (track_id, listened_at, username, 'listenbrainz'))
                    else:
                        cursor.execute("""
                            INSERT INTO scrobble_unmatched_listens (artist_name, track_title, album_name, listened_at, username, source)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE artist_name = artist_name
                        """, (artist_name, track_title, album_name, listened_at, username, 'listenbrainz'))
                    
                    processed += 1
                    if processed % 10 == 0:
                        cursor.execute("UPDATE scrobble_imports SET processed = %s WHERE id = %s", (processed, import_id))
                        conn.commit()
            
            # Rate limiting
            time.sleep(1)
            
            # If we got less than requested, we reached the end
            if len(listens) < 100:
                break
            
            # Decrement max_ts slightly to avoid getting the same track twice if multiple tracks have the same timestamp
            # though ListenBrainz usually handles this with max_ts being exclusive or inclusive differently.
            # Actually ListenBrainz max_ts is inclusive for tracks <= max_ts.
            # So we should use the timestamp of the last track minus 1 if we want to be sure, 
            # but usually it's better to just use the last timestamp and handle duplicates (which we do with ON DUPLICATE KEY).
            max_ts = max_ts - 1

        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE scrobble_imports 
                SET status = 'completed', processed = %s, finished_at = CURRENT_TIMESTAMP 
                WHERE id = %s
            """, (processed, import_id))
            conn.commit()
            print(f"Import {import_id} completed. Processed {processed} listens.")
            
    except Exception as e:
        print(f"Error during import {import_id}: {str(e)}")
        try:
            with conn.cursor() as cursor:
                cursor.execute("UPDATE scrobble_imports SET status = 'failed', last_error = %s WHERE id = %s", (str(e), import_id))
                conn.commit()
        except:
            pass
    finally:
        conn.close()

class ImportRequest(BaseModel):
    username: str
    lb_username: Optional[str] = None
    token: Optional[str] = None

@router.get("/import/latest")
def get_latest_imports():
    conn = get_db_connection()
    if not conn: raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM scrobble_imports ORDER BY started_at DESC LIMIT 10")
            return cursor.fetchall()
    finally:
        conn.close()

@router.post("/import/listenbrainz")
def trigger_lb_import(req: ImportRequest, background_tasks: BackgroundTasks):
    conn = get_db_connection()
    if not conn: raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO scrobble_imports (username, lb_username, status)
                VALUES (%s, %s, %s)
            """, (req.username, req.lb_username or req.username, 'pending'))
            import_id = cursor.lastrowid
            conn.commit()
            
            # Trigger background task
            background_tasks.add_task(run_listenbrainz_import, import_id, req.username, req.lb_username or req.username, req.token)
            
            return {"status": "ok", "import_id": import_id, "lb_username": req.lb_username or req.username}
    finally:
        conn.close()
