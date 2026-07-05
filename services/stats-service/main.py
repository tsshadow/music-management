from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
import os
import pymysql
from dotenv import load_dotenv
from typing import List, Optional, Dict
from pydantic import BaseModel
from services.common.api.version_helper import get_version, get_release_notes

load_dotenv()

app = FastAPI(title="Muma Stats Service")

# Allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = os.getenv("API_KEY", os.getenv("MUMA_API_KEY", "453ecd33-3cb2-4ca4-a531-1677330bbaee"))

async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
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

@app.get("/version")
async def version(api_key: str = Depends(verify_api_key)):
    return {"version": get_version()}

@app.get("/release-notes")
async def release_notes(api_key: str = Depends(verify_api_key)):
    return {"notes": get_release_notes("stats-service")}

@app.get("/stats")
def get_stats(api_key: str = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    stats = {}
    try:
        with conn.cursor() as cursor:
            # 1. Basic counts
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
            
            # 2. Top Artists
            cursor.execute("""
                SELECT a.name, COUNT(t.id) as track_count 
                FROM library_artists a
                JOIN library_tracks t ON a.id = t.primary_artist_id
                GROUP BY a.id
                ORDER BY track_count DESC
                LIMIT 10
            """)
            stats['top_artists'] = cursor.fetchall()
            
            # 3. Top Genres
            cursor.execute("SHOW TABLES LIKE 'library_track_genres'")
            if cursor.fetchone():
                cursor.execute("""
                    SELECT rg.name as genre, COUNT(*) as count 
                    FROM library_track_genres ltg
                    JOIN rules_genres rg ON ltg.genre_id = rg.id
                    GROUP BY ltg.genre_id 
                    ORDER BY count DESC 
                    LIMIT 10
                """)
                stats['top_genres'] = cursor.fetchall()
            else:
                stats['top_genres'] = []

            # 4. Scrobble stats
            cursor.execute("SHOW TABLES LIKE 'scrobble_listens'")
            if cursor.fetchone():
                cursor.execute("SELECT COUNT(*) as count FROM scrobble_listens")
                stats['total_scrobbles'] = cursor.fetchone()['count']
                
                cursor.execute("""
                    SELECT source, COUNT(*) as count 
                    FROM scrobble_listens 
                    GROUP BY source
                """)
                stats['scrobbles_by_source'] = cursor.fetchall()
            else:
                stats['total_scrobbles'] = 0
                stats['scrobbles_by_source'] = []

            # 5. Match Rate
            cursor.execute("SHOW TABLES LIKE 'scrobble_unmatched_listens'")
            if cursor.fetchone():
                cursor.execute("SELECT COUNT(*) as count FROM scrobble_unmatched_listens")
                total_unmatched = cursor.fetchone()['count']
                stats['total_unmatched'] = total_unmatched
                
                total = stats.get('total_scrobbles', 0) + total_unmatched
                if total > 0:
                    stats['match_rate'] = round((stats.get('total_scrobbles', 0) / total) * 100, 2)
                else:
                    stats['match_rate'] = 0
            else:
                stats['total_unmatched'] = 0
                stats['match_rate'] = 0

            # 6. Recently added
            cursor.execute("""
                SELECT t.title, a.name as artist, t.created_at
                FROM library_tracks t
                JOIN library_artists a ON t.primary_artist_id = a.id
                ORDER BY t.created_at DESC
                LIMIT 5
            """)
            stats['recently_added'] = cursor.fetchall()

            # 7. Avg duration
            cursor.execute("SELECT AVG(duration_secs) as avg_duration FROM library_tracks WHERE duration_secs > 0")
            avg_res = cursor.fetchone()
            avg = avg_res['avg_duration'] if avg_res else 0
            stats['avg_track_duration'] = round(avg, 2) if avg else 0

    except Exception as e:
        print(f"Query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
    
    return stats

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
