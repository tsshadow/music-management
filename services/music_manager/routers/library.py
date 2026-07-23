import os
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Depends, Query, BackgroundTasks
from services.music_manager.database import get_db_connection
from services.common.Helpers.ProcessedFilesHelper import ProcessedFilesHelper
from services.common.config_store import ConfigStore as Settings
router = APIRouter(tags=['library'])
settings = Settings()
API_KEY = os.getenv('API_KEY') or os.getenv('MUMA_API_KEY') or '00000000-0000-4000-8000-000000000000'

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

@router.get('/tracks')
def get_tracks(q: str='', page: int=1, limit: int=50, _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    offset = (page - 1) * limit
    try:
        with conn.cursor() as cursor:
            query = "\n                SELECT \n                    t.id, t.title, a.name as artist,\n                    (SELECT l.name FROM library_labels l \n                     JOIN library_track_labels tl ON l.id = tl.label_id \n                     WHERE tl.track_id = t.id LIMIT 1) as label,\n                    (SELECT GROUP_CONCAT(g.name SEPARATOR ', ') FROM rules_genres g \n                     JOIN library_track_genres tg ON g.id = tg.genre_id \n                     WHERE tg.track_id = t.id) as genre,\n                    (SELECT mf.file_path FROM library_media_files mf WHERE mf.track_id = t.id LIMIT 1) as file_path,\n                    ml.ml_genre, \n                    COALESCE(af.tempo, af.bpm_tag) as bpm,\n                    CAST(t.created_at AS CHAR) as created_at,\n                    (SELECT url FROM downloads_soundcloud_archive \n                     WHERE filename LIKE CONCAT('%%', SUBSTRING_INDEX((SELECT mf2.file_path FROM library_media_files mf2 WHERE mf2.track_id = t.id LIMIT 1), '/', -1), '%%') \n                     LIMIT 1) as sc_url,\n                    (SELECT url FROM downloads_youtube_archive \n                     WHERE filename LIKE CONCAT('%%', SUBSTRING_INDEX((SELECT mf3.file_path FROM library_media_files mf3 WHERE mf3.track_id = t.id LIMIT 1), '/', -1), '%%') \n                     LIMIT 1) as yt_url\n                FROM library_tracks t\n                LEFT JOIN library_artists a ON t.primary_artist_id = a.id\n                LEFT JOIN library_track_ml_labels ml ON t.track_uid = ml.track_id\n                LEFT JOIN library_track_audio_features af ON t.track_uid = af.track_id\n                WHERE t.title LIKE %s OR a.name LIKE %s OR \n                      EXISTS (SELECT 1 FROM library_track_labels tl \n                              JOIN library_labels l ON tl.label_id = l.id \n                              WHERE tl.track_id = t.id AND l.name LIKE %s)\n                ORDER BY t.created_at DESC\n                LIMIT %s OFFSET %s\n            "
            search_pattern = f'%{q}%'
            cursor.execute(query, (search_pattern, search_pattern, search_pattern, limit, offset))
            tracks = cursor.fetchall()
            cursor.execute('\n                SELECT COUNT(*) as total\n                FROM library_tracks t\n                LEFT JOIN library_artists a ON t.primary_artist_id = a.id\n                WHERE t.title LIKE %s OR a.name LIKE %s OR \n                      EXISTS (SELECT 1 FROM library_track_labels tl \n                              JOIN library_labels l ON tl.label_id = l.id \n                              WHERE tl.track_id = t.id AND l.name LIKE %s)\n            ', (search_pattern, search_pattern, search_pattern))
            total = cursor.fetchone()['total']
            return {'tracks': tracks, 'total': total, 'page': page, 'limit': limit}
    finally:
        conn.close()

@router.get('/advanced')
def get_advanced_library(
    q: str = '',
    genres: Optional[str] = None,
    bpm_min: Optional[float] = None,
    bpm_max: Optional[float] = None,
    page: int = 1,
    limit: int = 100,
    _auth: dict = Depends(verify_api_key)
):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    
    offset = (page - 1) * limit
    try:
        with conn.cursor() as cursor:
            # Build dynamic where clause
            where_clauses = []
            params = []
            
            # Advanced Query Parsing
            if q:
                terms = q.split(' ')
                for term in terms:
                    if not term: continue
                    # Check if term is a number (BPM)
                    try:
                        bpm_val = float(term)
                        if bpm_val > 50 and bpm_val < 300:
                            where_clauses.append("(COALESCE(af.tempo, af.bpm_tag) BETWEEN %s AND %s)")
                            params.extend([bpm_val - 2, bpm_val + 2])
                            continue
                    except ValueError:
                        pass
                    
                    # Otherwise search in title/artist/label/genre
                    where_clauses.append("(t.title LIKE %s OR a.name LIKE %s OR EXISTS (SELECT 1 FROM library_track_labels tl JOIN library_labels l ON tl.label_id = l.id WHERE tl.track_id = t.id AND l.name LIKE %s) OR EXISTS (SELECT 1 FROM library_track_genres tg JOIN rules_genres rg ON tg.genre_id = rg.id WHERE tg.track_id = t.id AND rg.name LIKE %s) OR ml.ml_genre LIKE %s)")
                    params.extend([f'%{term}%', f'%{term}%', f'%{term}%', f'%{term}%', f'%{term}%'])
            
            if not where_clauses:
                where_clauses.append("1=1")
            
            if genres:
                genre_list = [g.strip() for g in genres.split(',')]
                genre_placeholders = ', '.join(['%s'] * len(genre_list))
                where_clauses.append(f"EXISTS (SELECT 1 FROM library_track_genres tg JOIN rules_genres rg ON tg.genre_id = rg.id WHERE tg.track_id = t.id AND rg.name IN ({genre_placeholders}))")
                params.extend(genre_list)
            
            if bpm_min is not None:
                where_clauses.append("COALESCE(af.tempo, af.bpm_tag) >= %s")
                params.append(bpm_min)
            
            if bpm_max is not None:
                where_clauses.append("COALESCE(af.tempo, af.bpm_tag) <= %s")
                params.append(bpm_max)
                
            where_str = " AND ".join(where_clauses)
            
            query = f"""
                SELECT 
                    t.id, t.title, a.name as artist,
                    (SELECT l.name FROM library_labels l 
                     JOIN library_track_labels tl ON l.id = tl.label_id 
                     WHERE tl.track_id = t.id LIMIT 1) as label,
                    (SELECT GROUP_CONCAT(g.name SEPARATOR ', ') FROM rules_genres g 
                     JOIN library_track_genres tg ON g.id = tg.genre_id 
                     WHERE tg.track_id = t.id) as genre,
                    (SELECT mf.file_path FROM library_media_files mf WHERE mf.track_id = t.id LIMIT 1) as file_path,
                    ml.ml_genre, 
                    COALESCE(af.tempo, af.bpm_tag) as bpm,
                    COALESCE(af.musical_key, '') as musical_key,
                    COALESCE(af.energy, af.mean_rms * 100) as energy,
                    COALESCE(af.danceability, 0) as danceability,
                    COALESCE(af.valence, 0) as valence,
                    COALESCE(af.popularity, 0) as popularity,
                    CAST(t.created_at AS CHAR) as created_at
                FROM library_tracks t
                LEFT JOIN library_artists a ON t.primary_artist_id = a.id
                LEFT JOIN library_track_ml_labels ml ON t.track_uid = ml.track_id
                LEFT JOIN library_track_audio_features af ON t.track_uid = af.track_id
                WHERE {where_str}
                ORDER BY t.created_at DESC
                LIMIT %s OFFSET %s
            """
            cursor.execute(query, (*params, limit, offset))
            tracks = cursor.fetchall()
            
            # Get total
            count_query = f"""
                SELECT COUNT(*) as total
                FROM library_tracks t
                LEFT JOIN library_artists a ON t.primary_artist_id = a.id
                LEFT JOIN library_track_audio_features af ON t.track_uid = af.track_id
                WHERE {where_str}
            """
            cursor.execute(count_query, params)
            total = cursor.fetchone()['total']
            
            # Quick stats for this filter
            cursor.execute(f"""
                SELECT 
                    AVG(COALESCE(af.tempo, af.bpm_tag)) as avg_bpm,
                    COUNT(DISTINCT a.id) as artist_count
                FROM library_tracks t
                LEFT JOIN library_artists a ON t.primary_artist_id = a.id
                LEFT JOIN library_track_audio_features af ON t.track_uid = af.track_id
                WHERE {where_str}
            """, params)
            quick_stats = cursor.fetchone()
            
            return {
                'tracks': tracks, 
                'total': total, 
                'page': page, 
                'limit': limit,
                'stats': {
                    'avg_bpm': quick_stats['avg_bpm'],
                    'artist_count': quick_stats['artist_count']
                }
            }
    finally:
        conn.close()

@router.get('/genres')
def get_library_genres(_auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT g.name 
                FROM rules_genres g
                JOIN library_track_genres tg ON g.id = tg.genre_id
                ORDER BY g.name
            """)
            return [row['name'] for row in cursor.fetchall()]
    finally:
        conn.close()

@router.post('/tracks/{track_id}/rerun-parse')
def rerun_parse(track_id: int, _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT file_path FROM library_media_files WHERE track_id = %s', (track_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail='Track file not found')
            filepath = row['file_path']
            helper = ProcessedFilesHelper()
            helper.mark_for_rescan(filepath)
            try:
                from services.music_manager.routers.tagger import tagger_manager
                from services.music_manager.routers.scanner import scanner_manager
                tagger_manager.tag_single(filepath)
                logging.info(f'Successfully executed immediate tagger rescan for {filepath}')
                scanner_manager.scan_single(filepath)
                logging.info(f'Successfully executed immediate scanner for {filepath}')
            except Exception as e:
                logging.warning(f'Could not execute immediate rescan/scan: {e}')
            return {'status': 'ok', 'message': f'Track {track_id} marked for rescan and immediate trigger attempted'}
    finally:
        conn.close()

@router.post('/tracks/rerun-parse-path')
def rerun_parse_path(path: str=Query(...), _auth: dict=Depends(verify_api_key)):
    """
    Triggers a re-tagging and re-scanning of a file based on its absolute path.
    Useful for external integrations like LMS.
    """
    filepath = path
    helper = ProcessedFilesHelper()
    helper.mark_for_rescan(filepath)
    try:
        from services.music_manager.routers.tagger import tagger_manager
        from services.music_manager.routers.scanner import scanner_manager
        tagger_manager.tag_single(filepath)
        logging.info(f'Successfully executed immediate tagger rescan for {filepath}')
        scanner_manager.scan_single(filepath)
        logging.info(f'Successfully executed immediate scanner for {filepath}')
    except Exception as e:
        logging.warning(f'Could not execute immediate rescan/scan for path {filepath}: {e}')
    return {'status': 'ok', 'message': f'Track at {filepath} marked for rescan and immediate trigger attempted'}

@router.post('/tracks/{track_id}/redownload')
def redownload_track(track_id: int, background_tasks: BackgroundTasks, _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT file_path FROM library_media_files WHERE track_id = %s', (track_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail='Track file not found')
            filepath = row['file_path']
            filename = os.path.basename(filepath)
            source_url = None
            source_type = None
            cursor.execute('SELECT url FROM downloads_soundcloud_archive WHERE filename LIKE %s LIMIT 1', (f'%{filename}%',))
            res = cursor.fetchone()
            if res:
                source_url = res['url']
                source_type = 'soundcloud'
            if not source_url:
                cursor.execute('SELECT url FROM downloads_youtube_archive WHERE filename LIKE %s LIMIT 1', (f'%{filename}%',))
                res = cursor.fetchone()
                if res:
                    source_url = res['url']
                    source_type = 'youtube'
            if not source_url:
                raise HTTPException(status_code=400, detail='Could not find source URL in archive for redownload')
            background_tasks.add_task(run_redownload_task, source_url, source_type)
            return {'status': 'ok', 'message': f'Redownload started for {source_type} track: {source_url}'}
    finally:
        conn.close()

def run_redownload_task(url: str, source_type: str):
    logging.info(f'Starting redownload task for {source_type}: {url}')
    try:
        if source_type == 'soundcloud':
            from services.downloader.soundcloud.soundcloud import SoundcloudDownloader
            downloader = SoundcloudDownloader(break_on_existing=False)
            downloader.redownload_mode = True
            ydl_opts = downloader._prepare_ydl_opts('', break_on_existing_arg=False, redownload=True)
            downloader.download_url(url, ydl_opts)
        elif source_type == 'youtube':
            from services.downloader.youtube.youtube import YoutubeDownloader
            downloader = YoutubeDownloader(break_on_existing=False)
            downloader.download_link(url, breakOnExisting=False, redownload=True)
        logging.info(f'Redownload task completed for {url}')
    except Exception as e:
        logging.error(f'Redownload task failed for {url}: {e}', exc_info=True)