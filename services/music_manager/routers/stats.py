import os
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Depends
from services.music_manager.database import get_db_connection
router = APIRouter(prefix='/stats', tags=['stats'])
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

def init_db(_cursor):
    pass

@router.get('/')
def get_stats(auth: dict=Depends(verify_api_key)):
    if auth.get('type') == 'user' and (not auth['user'].get('is_admin')):
        raise HTTPException(status_code=403, detail='Forbidden')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    stats = {'total_tracks': 0, 'total_artists': 0, 'total_albums': 0, 'top_artists': [], 'top_genres': [], 'total_scrobbles': 0, 'total_unmatched': 0, 'match_rate': 0, 'recently_added': [], 'avg_track_duration': 0}
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) as count FROM library_tracks')
            stats['total_tracks'] = cursor.fetchone()['count']
            cursor.execute('SELECT COUNT(*) as count FROM library_artists')
            stats['total_artists'] = cursor.fetchone()['count']
            stats['total_albums'] = 0
            cursor.execute('SELECT AVG(duration_secs) as avg_dur FROM library_tracks WHERE duration_secs > 0')
            stats['avg_track_duration'] = round(cursor.fetchone()['avg_dur'] or 0, 2)
            cursor.execute('\n                SELECT a.name, COUNT(t.id) as track_count\n                FROM library_artists a\n                JOIN library_tracks t ON a.id = t.primary_artist_id\n                GROUP BY a.id\n                ORDER BY track_count DESC\n                LIMIT 10\n            ')
            stats['top_artists'] = cursor.fetchall()
            cursor.execute('\n                SELECT genre, COUNT(*) as count\n                FROM (\n                    SELECT g.name as genre FROM library_track_genres tg JOIN rules_genres g ON tg.genre_id = g.id\n                    UNION ALL\n                    SELECT ml_genre as genre FROM library_track_ml_labels WHERE ml_genre IS NOT NULL\n                ) as combined\n                GROUP BY genre\n                ORDER BY count DESC\n                LIMIT 10\n            ')
            stats['top_genres'] = cursor.fetchall()
            cursor.execute('\n                SELECT COUNT(DISTINCT t.id) as count\n                FROM library_tracks t\n                LEFT JOIN library_track_genres tg ON t.id = tg.track_id\n                LEFT JOIN library_track_ml_labels ml ON t.track_uid = ml.track_id\n                WHERE tg.track_id IS NOT NULL OR ml.track_id IS NOT NULL\n            ')
            matched_count = cursor.fetchone()['count']
            if stats['total_tracks'] > 0:
                stats['match_rate'] = round(matched_count / stats['total_tracks'] * 100, 2)
            cursor.execute("SHOW TABLES LIKE 'scrobble_listens'")
            if cursor.fetchone():
                cursor.execute('SELECT COUNT(*) as count FROM scrobble_listens')
                stats['total_scrobbles'] = cursor.fetchone()['count']
            cursor.execute("SHOW TABLES LIKE 'scrobble_unmatched_listens'")
            if cursor.fetchone():
                cursor.execute('SELECT COUNT(*) as count FROM scrobble_unmatched_listens')
                stats['total_unmatched'] = cursor.fetchone()['count']
            cursor.execute('\n                SELECT t.title, a.name as artist, CAST(t.created_at AS CHAR) as created_at\n                FROM library_tracks t\n                JOIN library_artists a ON t.primary_artist_id = a.id\n                ORDER BY t.created_at DESC\n                LIMIT 5\n            ')
            stats['recently_added'] = cursor.fetchall()
    except Exception as e:
        print(f'Stats Query error: {e}')
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        conn.close()
    return stats