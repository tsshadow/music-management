from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
import os
import pymysql
from typing import List, Optional
from datetime import datetime
from dotenv import load_dotenv
from services.common.api.version_helper import get_version, get_release_notes, get_changelog

load_dotenv()

app = FastAPI(title="Muma Rating System")

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

class Rating(BaseModel):
    entity_type: str = "track"
    entity_id: str
    username: str
    rating: int

class RatingResponse(Rating):
    id: int
    created_at: datetime
    updated_at: datetime

@app.on_event("startup")
def startup_db():
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS muma_ratings (
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
            conn.commit()
        finally:
            conn.close()

class LMSEvent(BaseModel):
    event: str
    object_type: str
    object_id: str
    rating: int
    path: Optional[str] = None

@app.post("/api/lms-event")
def handle_lms_event(event: LMSEvent):
    """Handle events from LMS MusicManagementBackend."""
    print(f"Received LMS event: {event}")
    if event.event != "rating_changed":
        return {"status": "ignored", "reason": "unsupported event type"}
    
    entity_id = event.object_id
    
    # If it's a track and we have a path, try to find the muma track_uid
    if event.object_type == "track" and event.path:
        # Normalize path by stripping known prefixes
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
                    # Look up track_uid by trying various path combinations
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
                        print(f"Resolved path to track_uid {entity_id}")
                    else:
                        print(f"Could not resolve path {event.path} in database (tried {possible_paths})")
            finally:
                conn.close()

    # Reuse set_rating logic
    rating_data = Rating(
        entity_type=event.object_type,
        entity_id=entity_id,
        username="lms_user", # Default or extract from somewhere if possible
        rating=event.rating
    )
    return set_rating(rating_data)

@app.post("/ratings", response_model=RatingResponse)
def set_rating(rating: Rating):
    print(f"Setting rating: {rating.entity_type} {rating.entity_id} for user {rating.username} to {rating.rating}")
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor() as cursor:
            sql = """
                INSERT INTO muma_ratings (entity_type, entity_id, username, rating)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE rating = VALUES(rating)
            """
            cursor.execute(sql, (rating.entity_type, rating.entity_id, rating.username, rating.rating))
            conn.commit()
            
            cursor.execute("SELECT * FROM muma_ratings WHERE entity_type = %s AND entity_id = %s AND username = %s",
                           (rating.entity_type, rating.entity_id, rating.username))
            return cursor.fetchone()
    finally:
        conn.close()

@app.get("/ratings/{entity_type}/{entity_id}", response_model=List[RatingResponse])
def get_ratings(entity_type: str, entity_id: str):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM muma_ratings WHERE entity_type = %s AND entity_id = %s", (entity_type, entity_id))
            return cursor.fetchall()
    finally:
        conn.close()

@app.get("/ratings/user/{username}", response_model=List[RatingResponse])
def get_user_ratings(username: str, entity_type: Optional[str] = None):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor() as cursor:
            if entity_type:
                cursor.execute("SELECT * FROM muma_ratings WHERE username = %s AND entity_type = %s", (username, entity_type))
            else:
                cursor.execute("SELECT * FROM muma_ratings WHERE username = %s", (username,))
            return cursor.fetchall()
    finally:
        conn.close()

@app.get("/ratings/updates", response_model=List[RatingResponse])
def get_updates(since: datetime = Query(...), entity_type: Optional[str] = None):
    """Fetch ratings updated since a specific timestamp for synchronization."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor() as cursor:
            sql = "SELECT * FROM muma_ratings WHERE updated_at > %s"
            params = [since]
            if entity_type:
                sql += " AND entity_type = %s"
                params.append(entity_type)
            
            cursor.execute(sql, tuple(params))
            return cursor.fetchall()
    finally:
        conn.close()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/version")
async def version():
    """Return the current version of the service."""
    return {"version": get_version()}

@app.get("/release-notes")
async def release_notes():
    """Return the release notes for the service."""
    return {
        "release_notes": get_release_notes("rating-system"),
        "changelog": get_changelog()
    }
