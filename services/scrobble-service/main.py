from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
import os
import pymysql
import requests
import time
from typing import List, Optional, Dict, Any
from datetime import datetime
from dotenv import load_dotenv
from services.common.api.version_helper import get_version, get_release_notes, get_changelog

load_dotenv()

app = FastAPI(title="Muma Scrobble Service")

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
def scrobble(event: ScrobbleEvent):
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
def version():
    return {"version": get_version()}

@app.get("/release-notes")
def release_notes():
    return {"notes": get_release_notes("services/scrobble-service/RELEASE_NOTES.md")}

# ListenBrainz Import Logic
@app.post("/api/import/listenbrainz")
def import_listenbrainz(username: str, lb_username: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(run_listenbrainz_import, username, lb_username)
    return {"message": "Import started in background"}

def run_listenbrainz_import(muma_username: str, lb_username: str):
    print(f"Starting ListenBrainz import for {lb_username} -> {muma_username}")
    url = f"https://api.listenbrainz.org/1/user/{lb_username}/listens"
    params = {"count": 100}
    
    # Simple loop for now
    response = requests.get(url, params=params)
    if response.status_code != 200:
        print(f"Failed to fetch listens from ListenBrainz: {response.status_code}")
        return
    
    data = response.json()
    listens = data.get("payload", {}).get("listens", [])
    
    conn = get_db_connection()
    if not conn:
        return
        
    try:
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
                          ts, muma_username, "listenbrainz_import", str(item)))
            conn.commit()
    finally:
        conn.close()
    print(f"ListenBrainz import finished for {lb_username}")
