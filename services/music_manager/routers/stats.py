from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from services.music_manager.database import get_db_connection
from services.music_manager.rbac import has_permission
from services.music_manager.routers.users import verify_api_key

router = APIRouter(tags=['stats'])

# The non-music forms of services.common.track_form.NON_MUSIC_FORMS, as literals so the query
# stays a constant (as in feeds.queries.MUSIC_ONLY). The tests check the two agree.
NON_MUSIC_COUNT_SQL = (
    "SELECT COUNT(*) AS count, COALESCE(SUM(form IN ('interview', 'preview')), 0) AS non_music FROM library_tracks"
)


@router.get('/')
def get_stats(auth: dict = Depends(verify_api_key)):
    if auth.get('type') == 'user' and (not has_permission(auth, 'users.read')):
        raise HTTPException(status_code=403, detail='Forbidden')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    stats: dict[str, Any] = {
        'total_tracks': 0,
        'total_non_music': 0,
        'total_artists': 0,
        'total_albums': 0,
        'top_artists': [],
        'top_genres': [],
        'total_scrobbles': 0,
        'total_unmatched': 0,
        'match_rate': 0,
        'recently_added': [],
        'avg_track_duration': 0,
    }
    try:
        with conn.cursor() as cursor:
            # Tracks means music: an interview or a DVD preview is counted apart
            # (docs/designs/non-music-forms/). One scan of the table for both figures.
            cursor.execute(NON_MUSIC_COUNT_SQL)
            counts = cursor.fetchone()
            stats['total_non_music'] = int(counts['non_music'])
            stats['total_tracks'] = counts['count'] - stats['total_non_music']
            cursor.execute('SELECT COUNT(*) as count FROM library_artists')
            stats['total_artists'] = cursor.fetchone()['count']
            stats['total_albums'] = 0
            cursor.execute('SELECT AVG(duration_secs) as avg_dur FROM library_tracks WHERE duration_secs > 0')
            stats['avg_track_duration'] = round(cursor.fetchone()['avg_dur'] or 0, 2)
            cursor.execute(
                '\n                SELECT a.name, COUNT(t.id) as track_count\n                FROM library_artists a\n                JOIN library_tracks t ON a.id = t.primary_artist_id\n                GROUP BY a.id\n                ORDER BY track_count DESC\n                LIMIT 10\n            '
            )
            stats['top_artists'] = cursor.fetchall()
            # Counted from library_track_genres alone. The previous query unioned
            # this with library_track_ml_labels.ml_genre, which was harmless only
            # because library_track_genres was empty -- once it has rows a track
            # carrying the same genre in its tag and its ML prediction would be
            # counted twice. ML output is early-stage and stays out of curated
            # genre figures. Splitting on ';' in Python is no longer needed either:
            # library_track_genres holds one row per genre already.
            cursor.execute('''
                SELECT g.name AS genre, COUNT(DISTINCT tg.track_id) AS count
                FROM library_track_genres tg
                JOIN rules_genres g ON g.id = tg.genre_id
                WHERE g.state <> 'black'
                GROUP BY g.id
                ORDER BY count DESC
                LIMIT 10
            ''')
            stats['top_genres'] = cursor.fetchall()
            cursor.execute(
                '\n                SELECT COUNT(DISTINCT t.id) as count\n                FROM library_tracks t\n                LEFT JOIN library_track_genres tg ON t.id = tg.track_id\n                LEFT JOIN library_track_ml_labels ml ON t.track_uid = ml.track_id\n                WHERE tg.track_id IS NOT NULL OR ml.track_id IS NOT NULL\n            '
            )
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
            cursor.execute(
                '\n                SELECT t.title, a.name as artist, CAST(t.created_at AS CHAR) as created_at\n                FROM library_tracks t\n                JOIN library_artists a ON t.primary_artist_id = a.id\n                ORDER BY t.created_at DESC\n                LIMIT 5\n            '
            )
            stats['recently_added'] = cursor.fetchall()
    except Exception as e:
        print(f'Stats Query error: {e}')
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        conn.close()
    return stats
