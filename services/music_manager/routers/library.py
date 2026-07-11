import os
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Depends, Query, BackgroundTasks
from services.music_manager.database import get_db_connection
from services.common.Helpers.ProcessedFilesHelper import ProcessedFilesHelper
from services.common.settings import Settings

router = APIRouter(prefix="/api/library", tags=["library"])
settings = Settings()

API_KEY = os.getenv("API_KEY") or os.getenv("MUMA_API_KEY") or "453ecd33-3cb2-4ca4-a531-1677330bbaee"

def verify_api_key(x_api_key: Optional[str] = Header(None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API Key")
    if API_KEY and x_api_key == API_KEY:
        return {"type": "system"}

    from services.music_manager.routers.users import verify_token
    try:
        res = verify_token(x_api_key)
        if res.get("status") == "ok":
            return res
    except Exception:
        pass

    raise HTTPException(status_code=401, detail="Invalid API key")

@router.get("/tracks")
def get_tracks(
    q: str = "",
    page: int = 1,
    limit: int = 50,
    _auth: dict = Depends(verify_api_key)
):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    
    offset = (page - 1) * limit
    try:
        with conn.cursor() as cursor:
            # Base query
            query = """
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
                    CAST(t.created_at AS CHAR) as created_at,
                    (SELECT url FROM downloads_soundcloud_archive 
                     WHERE filename LIKE CONCAT('%%', SUBSTRING_INDEX((SELECT mf2.file_path FROM library_media_files mf2 WHERE mf2.track_id = t.id LIMIT 1), '/', -1), '%%') 
                     LIMIT 1) as sc_url,
                    (SELECT url FROM downloads_youtube_archive 
                     WHERE filename LIKE CONCAT('%%', SUBSTRING_INDEX((SELECT mf3.file_path FROM library_media_files mf3 WHERE mf3.track_id = t.id LIMIT 1), '/', -1), '%%') 
                     LIMIT 1) as yt_url
                FROM library_tracks t
                LEFT JOIN library_artists a ON t.primary_artist_id = a.id
                LEFT JOIN library_track_ml_labels ml ON t.track_uid = ml.track_id
                LEFT JOIN library_track_audio_features af ON t.track_uid = af.track_id
                WHERE t.title LIKE %s OR a.name LIKE %s OR 
                      EXISTS (SELECT 1 FROM library_track_labels tl 
                              JOIN library_labels l ON tl.label_id = l.id 
                              WHERE tl.track_id = t.id AND l.name LIKE %s)
                ORDER BY t.created_at DESC
                LIMIT %s OFFSET %s
            """
            search_pattern = f"%{q}%"
            cursor.execute(query, (search_pattern, search_pattern, search_pattern, limit, offset))
            tracks = cursor.fetchall()

            # Get total count for pagination
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM library_tracks t
                LEFT JOIN library_artists a ON t.primary_artist_id = a.id
                WHERE t.title LIKE %s OR a.name LIKE %s OR 
                      EXISTS (SELECT 1 FROM library_track_labels tl 
                              JOIN library_labels l ON tl.label_id = l.id 
                              WHERE tl.track_id = t.id AND l.name LIKE %s)
            """, (search_pattern, search_pattern, search_pattern))
            total = cursor.fetchone()['total']

            return {
                "tracks": tracks,
                "total": total,
                "page": page,
                "limit": limit
            }
    finally:
        conn.close()

@router.post("/tracks/{track_id}/rerun-parse")
def rerun_parse(track_id: int, _auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT file_path FROM library_media_files WHERE track_id = %s", (track_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Track file not found")
            
            filepath = row['file_path']
            helper = ProcessedFilesHelper()
            helper.mark_for_rescan(filepath)

            # Try to trigger the tagger and scanner managers immediately
            try:
                from services.music_manager.routers.tagger import tagger_manager
                from services.music_manager.routers.scanner import scanner_manager

                # 1. Trigger Tagger (Synchronous)
                tagger_manager.tag_single(filepath)
                logging.info(f"Successfully executed immediate tagger rescan for {filepath}")

                # 2. Trigger Scanner (Synchronous, ensuring Tagger is done)
                scanner_manager.scan_single(filepath)
                logging.info(f"Successfully executed immediate scanner for {filepath}")

            except Exception as e:
                logging.warning(f"Could not execute immediate rescan/scan: {e}")
            
            return {"status": "ok", "message": f"Track {track_id} marked for rescan and immediate trigger attempted"}
    finally:
        conn.close()

@router.post("/tracks/rerun-parse-path")
def rerun_parse_path(path: str = Query(...), _auth: dict = Depends(verify_api_key)):
    """
    Triggers a re-tagging and re-scanning of a file based on its absolute path.
    Useful for external integrations like LMS.
    """
    filepath = path
    helper = ProcessedFilesHelper()
    helper.mark_for_rescan(filepath)

    # Try to trigger the tagger and scanner managers immediately
    try:
        from services.music_manager.routers.tagger import tagger_manager
        from services.music_manager.routers.scanner import scanner_manager

        # 1. Trigger Tagger (Synchronous)
        tagger_manager.tag_single(filepath)
        logging.info(f"Successfully executed immediate tagger rescan for {filepath}")

        # 2. Trigger Scanner (Synchronous, ensuring Tagger is done)
        scanner_manager.scan_single(filepath)
        logging.info(f"Successfully executed immediate scanner for {filepath}")

    except Exception as e:
        logging.warning(f"Could not execute immediate rescan/scan for path {filepath}: {e}")
    
    return {"status": "ok", "message": f"Track at {filepath} marked for rescan and immediate trigger attempted"}

@router.post("/tracks/{track_id}/redownload")
def redownload_track(track_id: int, background_tasks: BackgroundTasks, _auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    
    try:
        with conn.cursor() as cursor:
            # 1. Get file path
            cursor.execute("SELECT file_path FROM library_media_files WHERE track_id = %s", (track_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Track file not found")
            
            filepath = row['file_path']
            filename = os.path.basename(filepath)
            
            # 2. Try to find source URL
            source_url = None
            source_type = None
            
            # Check Soundcloud
            cursor.execute("SELECT url FROM downloads_soundcloud_archive WHERE filename LIKE %s LIMIT 1", (f"%{filename}%",))
            res = cursor.fetchone()
            if res:
                source_url = res['url']
                source_type = "soundcloud"
            
            if not source_url:
                # Check Youtube
                cursor.execute("SELECT url FROM downloads_youtube_archive WHERE filename LIKE %s LIMIT 1", (f"%{filename}%",))
                res = cursor.fetchone()
                if res:
                    source_url = res['url']
                    source_type = "youtube"
            
            if not source_url:
                raise HTTPException(status_code=400, detail="Could not find source URL in archive for redownload")
            
            # 3. Trigger redownload in background
            background_tasks.add_task(run_redownload_task, source_url, source_type)
            
            return {"status": "ok", "message": f"Redownload started for {source_type} track: {source_url}"}
    finally:
        conn.close()

def run_redownload_task(url: str, source_type: str):
    logging.info(f"Starting redownload task for {source_type}: {url}")
    try:
        if source_type == "soundcloud":
            from services.downloader.soundcloud.soundcloud import SoundcloudDownloader
            downloader = SoundcloudDownloader(break_on_existing=False)
            downloader.redownload_mode = True
            # Use redownload=True to ignore existing archive entry
            ydl_opts = downloader._prepare_ydl_opts("", break_on_existing_arg=False, redownload=True)
            downloader.download_url(url, ydl_opts)
        elif source_type == "youtube":
            from services.downloader.youtube.youtube import YoutubeDownloader
            downloader = YoutubeDownloader(break_on_existing=False)
            downloader.download_link(url, breakOnExisting=False, redownload=True)
        logging.info(f"Redownload task completed for {url}")
    except Exception as e:
        logging.error(f"Redownload task failed for {url}: {e}", exc_info=True)
