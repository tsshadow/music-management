from fastapi import APIRouter, HTTPException, Header, Depends
from typing import List, Optional, Dict
from pydantic import BaseModel
import os
from services.music_manager.database import get_db_connection
from services.common.api.version_helper import get_version, get_release_notes

router = APIRouter(prefix="/stats", tags=["stats"])

API_KEY = os.getenv("API_KEY") or os.getenv("MUMA_API_KEY") or "453ecd33-3cb2-4ca4-a531-1677330bbaee"

def verify_api_key(x_api_key: Optional[str] = Header(None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key

def init_db(cursor):
    # Stats service usually just reads, but we can ensure tables exist if needed
    pass

@router.get("/")
def get_stats(api_key: str = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    stats = {}
    try:
        with conn.cursor() as cursor:
            # Basic counts
            cursor.execute("SELECT COUNT(*) as count FROM library_tracks")
            stats['total_tracks'] = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM library_artists")
            stats['total_artists'] = cursor.fetchone()['count']
            
            cursor.execute("SHOW TABLES LIKE 'library_albums'")
            if cursor.fetchone():
                cursor.execute("SELECT COUNT(*) as count FROM library_albums")
                stats['total_albums'] = cursor.fetchone()['count']
            else:
                stats['total_albums'] = 0
            
            # Top Artists
            cursor.execute("""
                SELECT a.name, COUNT(t.id) as track_count 
                FROM library_artists a
                JOIN library_tracks t ON a.id = t.primary_artist_id
                GROUP BY a.id
                ORDER BY track_count DESC
                LIMIT 10
            """)
            stats['top_artists'] = cursor.fetchall()
            
            # Scrobble stats
            cursor.execute("SHOW TABLES LIKE 'scrobble_listens'")
            if cursor.fetchone():
                cursor.execute("SELECT COUNT(*) as count FROM scrobble_listens")
                stats['total_scrobbles'] = cursor.fetchone()['count']
            
            # Recently added
            cursor.execute("""
                SELECT t.title, a.name as artist, CAST(t.created_at AS CHAR) as created_at
                FROM library_tracks t
                JOIN library_artists a ON t.primary_artist_id = a.id
                ORDER BY t.created_at DESC
                LIMIT 5
            """)
            stats['recently_added'] = cursor.fetchall()

    except Exception as e:
        print(f"Stats Query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
    
    return stats
