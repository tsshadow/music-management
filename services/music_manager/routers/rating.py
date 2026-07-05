from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import os
from services.music_manager.database import get_db_connection

router = APIRouter(prefix="/rating", tags=["rating"])

API_KEY = os.getenv("API_KEY") or os.getenv("MUMA_API_KEY") or "453ecd33-3cb2-4ca4-a531-1677330bbaee"

def verify_api_key(x_api_key: str = Header(None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return x_api_key

class Rating(BaseModel):
    entity_type: str = "track"
    entity_id: str
    username: str
    rating: int

class LMSEvent(BaseModel):
    event: str
    object_type: str
    object_id: str
    username: str
    rating: int
    path: Optional[str] = None

def init_db(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rating_tracks (
            id INT AUTO_INCREMENT PRIMARY KEY,
            entity_type VARCHAR(50) NOT NULL,
            entity_id VARCHAR(255) NOT NULL,
            username VARCHAR(255) NOT NULL,
            rating INT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY (entity_type, entity_id, username)
        )
    """)

@router.post("/api/lms-event")
def handle_lms_event(event: LMSEvent, api_key: str = Depends(verify_api_key)):
    if event.event != "rating_changed":
        return {"status": "ignored", "reason": "unsupported event type"}
    
    entity_id = event.object_id
    
    if event.object_type == "track" and event.path:
        clean_path = event.path
        for p in ["/music/", "/mnt/music/"]:
            if clean_path.startswith(p):
                clean_path = clean_path[len(p):]
                break
        
        possible_paths = [event.path, clean_path, f"/music/{clean_path}", f"/mnt/music/{clean_path}"]
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cursor:
                    sql = """
                        SELECT t.track_uid 
                        FROM library_media_files f
                        JOIN library_tracks t ON f.track_id = t.id
                        WHERE f.file_path IN (%s, %s, %s, %s)
                    """
                    cursor.execute(sql, tuple(possible_paths))
                    row = cursor.fetchone()
                    if row:
                        entity_id = row['track_uid']
            finally:
                conn.close()

    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO rating_tracks (entity_type, entity_id, username, rating)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE rating = VALUES(rating)
            """, (event.object_type, entity_id, event.username, event.rating))
            conn.commit()
            return {"status": "success", "entity_id": entity_id}
    finally:
        conn.close()
