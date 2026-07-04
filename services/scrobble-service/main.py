from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Header, Depends
from pydantic import BaseModel
import os
import pymysql
import requests
import time
import json
from typing import List, Optional, Dict, Any
from datetime import datetime
from dotenv import load_dotenv
from services.common.api.version_helper import get_version, get_release_notes, get_changelog

load_dotenv()

app = FastAPI(title="Muma Scrobble Service")

API_KEY = os.getenv("API_KEY", "Tarnish-Trespass-Dorsal-Sanding-Epilepsy-Unsavory9")

async def verify_api_key(x_api_key: str = Header(None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return x_api_key

def get_db_connection():
    try:
        conn = pymysql.connect(
            host=os.getenv("DB_HOST", "db"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "music-management"),
            password=os.getenv("DB_PASS", ""),
            db=os.getenv("DB_DB", "music-management"),
            cursorclass=pymysql.cursors.DictCursor
        )
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

@app.on_event("startup")
def startup_db():
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                # Confirmed listens
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS scrobble_listens (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        track_id INT,
                        listened_at TIMESTAMP NOT NULL,
                        username VARCHAR(255) NOT NULL,
                        source VARCHAR(50),
                        mbid_track VARCHAR(36),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (track_id) REFERENCES library_tracks(id) ON DELETE CASCADE,
                        UNIQUE KEY (username, listened_at, track_id)
                    )
                """)
                # Unmatched listens
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
                # Import status tracking
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
            conn.commit()
        finally:
            conn.close()

class ScrobbleEvent(BaseModel):
    artist_name: str
    track_title: str
    album_name: Optional[str] = None
    mbid_track: Optional[str] = None
    mbid_artist: Optional[str] = None
    listened_at: Optional[int] = None # Unix timestamp
    username: str
    source: str = "manual"

def find_track_id(cursor, artist_name: str, track_title: str, mbid_track: Optional[str] = None) -> Optional[int]:
    # 1. Try MBID
    if mbid_track:
        # In current schema, we don't have MBID on library_tracks yet, but library_artists has it.
        # library_tracks has track_uid which might be a hash.
        # Let's check if there is an MBID column we missed or if we should look in library_tracks.
        pass
    
    # 2. Try Artist + Title match
    # We need to find the artist first
    cursor.execute("SELECT id FROM library_artists WHERE name = %s", (artist_name,))
    artist_row = cursor.fetchone()
    if artist_row:
        artist_id = artist_row['id']
        cursor.execute("""
            SELECT id FROM library_tracks 
            WHERE title = %s AND primary_artist_id = %s
        """, (track_title, artist_id))
        track_row = cursor.fetchone()
        if track_row:
            return track_row['id']
            
    # 3. Fallback: fuzzy search or alias? (Keep it simple for now)
    return None

@app.post("/api/scrobble")
def scrobble(event: ScrobbleEvent, _: str = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor() as cursor:
            track_id = find_track_id(cursor, event.artist_name, event.track_title, event.mbid_track)
            
            ts = datetime.fromtimestamp(event.listened_at) if event.listened_at else datetime.now()
            
            if track_id:
                cursor.execute("""
                    INSERT IGNORE INTO scrobble_listens (track_id, listened_at, username, source, mbid_track)
                    VALUES (%s, %s, %s, %s, %s)
                """, (track_id, ts, event.username, event.source, event.mbid_track))
                status = "matched"
            else:
                cursor.execute("""
                    INSERT IGNORE INTO scrobble_unmatched_listens 
                    (artist_name, track_title, album_name, mbid_track, mbid_artist, listened_at, username, source, data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (event.artist_name, event.track_title, event.album_name, event.mbid_track, event.mbid_artist, 
                      ts, event.username, event.source, event.json()))
                status = "unmatched"
            
            conn.commit()
            return {"status": "success", "match": status}
    finally:
        conn.close()

@app.get("/version")
def version(_: str = Depends(verify_api_key)):
    return {"version": get_version()}

@app.get("/release-notes")
def release_notes(_: str = Depends(verify_api_key)):
    return {"notes": get_release_notes("services/scrobble-service/RELEASE_NOTES.md")}

# ListenBrainz Import Logic
@app.post("/api/import/listenbrainz")
def import_listenbrainz(username: str, lb_username: str, background_tasks: BackgroundTasks, _: str = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO scrobble_imports (username, lb_username, status)
                VALUES (%s, %s, %s)
            """, (username, lb_username, "pending"))
            import_id = cursor.lastrowid
            conn.commit()
            
            background_tasks.add_task(run_listenbrainz_import, import_id, username, lb_username)
            return {"message": "Import started", "import_id": import_id}
    finally:
        conn.close()

@app.get("/api/import/status/{import_id}")
def get_import_status(import_id: int, _: str = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM scrobble_imports WHERE id = %s", (import_id,))
            result = cursor.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Import not found")
            return result
    finally:
        conn.close()

@app.get("/api/import/latest")
def get_latest_imports(limit: int = 5, _: str = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM scrobble_imports ORDER BY started_at DESC LIMIT %s", (limit,))
            return cursor.fetchall()
    finally:
        conn.close()

def run_listenbrainz_import(import_id: int, muma_username: str, lb_username: str):
    print(f"Starting ListenBrainz import #{import_id} for {lb_username} -> {muma_username}")
    
    def update_status(status=None, processed=None, total=None, error=None, finished=False):
        conn = get_db_connection()
        if not conn: return
        try:
            with conn.cursor() as cursor:
                updates = []
                params = []
                if status: updates.append("status = %s"); params.append(status)
                if processed is not None: updates.append("processed = %s"); params.append(processed)
                if total is not None: updates.append("total_found = %s"); params.append(total)
                if error: updates.append("last_error = %s"); params.append(error)
                if finished: updates.append("finished_at = CURRENT_TIMESTAMP")
                
                if updates:
                    sql = f"UPDATE scrobble_imports SET {', '.join(updates)} WHERE id = %s"
                    params.append(import_id)
                    cursor.execute(sql, params)
                    conn.commit()
        finally:
            conn.close()

    update_status(status="running")

    url = f"https://api.listenbrainz.org/1/user/{lb_username}/listens"
    params = {"count": 100}
    headers = {"User-Agent": "MumaScrobbler/2.1 ( contact@muma.local )"}
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        if response.status_code != 200:
            update_status(status="failed", error=f"ListenBrainz API error: {response.status_code}", finished=True)
            return
        
        data = response.json()
        listens = data.get("payload", {}).get("listens", [])
        total_count = len(listens)
        update_status(total=total_count)
        
        conn = get_db_connection()
        if not conn:
            update_status(status="failed", error="Database connection failed during import", finished=True)
            return
            
        try:
            processed_count = 0
            with conn.cursor() as cursor:
                for item in listens:
                    metadata = item.get("track_metadata", {})
                    artist_name = metadata.get("artist_name")
                    track_title = metadata.get("track_name")
                    album_name = metadata.get("release_name")
                    info = metadata.get("additional_info", {})
                    mbid_track = info.get("recording_mbid")
                    mbid_artist = info.get("artist_mbids", [None])[0]
                    listened_at = item.get("listened_at")
                    
                    track_id = find_track_id(cursor, artist_name, track_title, mbid_track)
                    ts = datetime.fromtimestamp(listened_at)
                    
                    if track_id:
                        cursor.execute("""
                            INSERT IGNORE INTO scrobble_listens (track_id, listened_at, username, source, mbid_track)
                            VALUES (%s, %s, %s, %s, %s)
                        """, (track_id, ts, muma_username, "listenbrainz_import", mbid_track))
                    else:
                        cursor.execute("""
                            INSERT IGNORE INTO scrobble_unmatched_listens 
                            (artist_name, track_title, album_name, mbid_track, mbid_artist, listened_at, username, source, data)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (artist_name, track_title, album_name, mbid_track, mbid_artist, 
                              ts, muma_username, "listenbrainz_import", json.dumps(item)))
                    
                    processed_count += 1
                    if processed_count % 10 == 0:
                        update_status(processed=processed_count)
                
                conn.commit()
                update_status(status="completed", processed=processed_count, finished=True)
        finally:
            conn.close()
    except Exception as e:
        update_status(status="failed", error=str(e), finished=True)
    
    print(f"ListenBrainz import #{import_id} finished")
