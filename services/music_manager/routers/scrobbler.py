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
