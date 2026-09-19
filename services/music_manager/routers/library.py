import logging
import os

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query

from services.common.config_store import ConfigStore as Settings
from services.common.Helpers.ProcessedFilesHelper import ProcessedFilesHelper
from services.music_manager.api_key import is_system_api_key
from services.music_manager.database import get_db_connection
from services.music_manager.genre_tint import genre_tint
from services.music_manager.routers.analytics_filters import (
    FROM_CLAUSE,
    LibraryFilter,
    build_filter,
    parse_filter,
)

router = APIRouter(tags=['library'])
settings = Settings()

# Sort keys the track table offers, mapped to SQL. The value is interpolated into the query, so a
# caller's sort parameter may only ever select a key here, never contribute text.
#
# A NULL release date sorts last in both directions: "unknown" is not older than 1970, it is absent.
_SORTS = {
    'created': 't.created_at',
    'release': 'af.release_date IS NULL, af.release_date',
    'title': 't.title',
    'bpm': 'COALESCE(af.tempo, af.bpm_tag)',
}


def _order_by(sort: str, direction: str) -> str:
    """The ORDER BY body for a requested sort, falling back to the default for anything unknown."""
    column = _SORTS.get(sort, _SORTS['created'])
    return f'{column} {"ASC" if direction == "asc" else "DESC"}'


def verify_api_key(x_api_key: str | None = Header(None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail='Missing API Key')
    if is_system_api_key(x_api_key):
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
def get_tracks(q: str = '', page: int = 1, limit: int = 50, _auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    offset = (page - 1) * limit
    try:
        with conn.cursor() as cursor:
            query = "\n                SELECT \n                    t.id, t.title, a.name as artist, t.display_artist,\n                    (SELECT l.name FROM library_labels l \n                     JOIN library_track_labels tl ON l.id = tl.label_id \n                     WHERE tl.track_id = t.id LIMIT 1) as label,\n                    (SELECT GROUP_CONCAT(g.name SEPARATOR ', ') FROM rules_genres g \n                     JOIN library_track_genres tg ON g.id = tg.genre_id \n                     WHERE tg.track_id = t.id) as genre,\n                    (SELECT mf.file_path FROM library_media_files mf WHERE mf.track_id = t.id LIMIT 1) as file_path,\n                    ml.ml_genre, \n                    COALESCE(af.tempo, af.bpm_tag) as bpm,\n                    CAST(t.created_at AS CHAR) as created_at,\n                    (SELECT url FROM downloads_soundcloud_archive \n                     WHERE filename LIKE CONCAT('%%', SUBSTRING_INDEX((SELECT mf2.file_path FROM library_media_files mf2 WHERE mf2.track_id = t.id LIMIT 1), '/', -1), '%%') \n                     LIMIT 1) as sc_url,\n                    (SELECT url FROM downloads_youtube_archive \n                     WHERE filename LIKE CONCAT('%%', SUBSTRING_INDEX((SELECT mf3.file_path FROM library_media_files mf3 WHERE mf3.track_id = t.id LIMIT 1), '/', -1), '%%') \n                     LIMIT 1) as yt_url\n                FROM library_tracks t\n                LEFT JOIN library_artists a ON t.primary_artist_id = a.id\n                LEFT JOIN library_track_ml_labels ml ON t.track_uid = ml.track_id\n                LEFT JOIN library_track_audio_features af ON af.internal_track_id = t.id\n                WHERE t.title LIKE %s OR a.name LIKE %s OR \n                      EXISTS (SELECT 1 FROM library_track_labels tl \n                              JOIN library_labels l ON tl.label_id = l.id \n                              WHERE tl.track_id = t.id AND l.name LIKE %s)\n                ORDER BY t.created_at DESC\n                LIMIT %s OFFSET %s\n            "
            search_pattern = f'%{q}%'
            cursor.execute(query, (search_pattern, search_pattern, search_pattern, limit, offset))
            tracks = cursor.fetchall()
            cursor.execute(
                '\n                SELECT COUNT(*) as total\n                FROM library_tracks t\n                LEFT JOIN library_artists a ON t.primary_artist_id = a.id\n                WHERE t.title LIKE %s OR a.name LIKE %s OR \n                      EXISTS (SELECT 1 FROM library_track_labels tl \n                              JOIN library_labels l ON tl.label_id = l.id \n                              WHERE tl.track_id = t.id AND l.name LIKE %s)\n            ',
                (search_pattern, search_pattern, search_pattern),
            )
            total = cursor.fetchone()['total']
            return {'tracks': tracks, 'total': total, 'page': page, 'limit': limit}
    finally:
        conn.close()


@router.get('/advanced')
def get_advanced_library(
    page: int = 1,
    limit: int = 100,
    sort: str = 'created',
    direction: str = 'desc',
    f: LibraryFilter = Depends(parse_filter),
    _auth: dict = Depends(verify_api_key),
):
    """Filtered track list for the library browser.

    The previous version selected musical_key, energy, danceability, valence and
    popularity. None of those columns exist in production -- db_init.py lists them
    in a CREATE TABLE IF NOT EXISTS that is a no-op against the existing table --
    so every request failed with "Unknown column 'af.musical_key'". They are gone
    rather than added, because nothing writes them.
    """
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')

    offset = max(page - 1, 0) * limit
    where, params = build_filter(f)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    t.id, t.title, a.name AS artist, t.display_artist, t.duration_secs,
                    (SELECT l.name FROM library_labels l
                     JOIN library_track_labels tl ON l.id = tl.label_id
                     WHERE tl.track_id = t.id LIMIT 1) AS label,
                    (SELECT GROUP_CONCAT(rg.name ORDER BY rg.name SEPARATOR ',')
                     FROM rules_genres rg
                     JOIN library_track_genres tg ON rg.id = tg.genre_id
                     WHERE tg.track_id = t.id AND rg.state <> 'black') AS genres,
                    (SELECT mf.file_path FROM library_media_files mf
                     WHERE mf.track_id = t.id LIMIT 1) AS file_path,
                    COALESCE(af.tempo, af.bpm_tag) AS bpm,
                    af.release_year,
                    af.release_date,
                    CAST(t.created_at AS CHAR) AS created_at
                {FROM_CLAUSE}
                WHERE {where}
                ORDER BY {_order_by(sort, direction)}
                LIMIT %s OFFSET %s
            """,
                (*params, limit, offset),
            )
            tracks = cursor.fetchall()

            for track in tracks:
                raw = track.get('genres')
                track['genres'] = [g for g in (raw or '').split(',') if g]

            cursor.execute(f'SELECT COUNT(DISTINCT t.id) AS total {FROM_CLAUSE} WHERE {where}', tuple(params))
            total = cursor.fetchone()['total']

            return {'tracks': tracks, 'total': total, 'page': page, 'limit': limit}
    finally:
        conn.close()


@router.get('/genres')
def get_library_genres(_auth: dict = Depends(verify_api_key)):
    """Genres tracks actually carry, with counts.

    This returned [] for as long as it existed: it joined rules_genres against
    library_track_genres, which had no rows until the scanner started writing it.
    Unknown genres are included so the sidebar can group them as awaiting
    curation rather than hide tracks that do have a genre in their tag.

    Each row carries the colour its tile is drawn in. Both the web UI and the
    mobile app render a genre as a coloured tile, and deriving that colour here
    is what keeps them from each owning a table that drifts.
    """
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT g.name AS genre, g.state AS state, COUNT(DISTINCT tg.track_id) AS count
                FROM rules_genres g
                JOIN library_track_genres tg ON g.id = tg.genre_id
                WHERE g.state <> 'black'
                GROUP BY g.id
                ORDER BY count DESC, g.name
            """)
            rows = cursor.fetchall()
            for row in rows:
                row['tint'] = genre_tint(row.get('genre'))
            return rows
    finally:
        conn.close()


@router.post('/tracks/{track_id}/rerun-parse')
def rerun_parse(track_id: int, _auth: dict = Depends(verify_api_key)):
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
            helper.mark_for_rescan(filepath, reason='rerun_parse')
            try:
                from services.music_manager.routers.scanner import scanner_manager
                from services.music_manager.routers.tagger import tagger_manager

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
def rerun_parse_path(path: str = Query(...), _auth: dict = Depends(verify_api_key)):
    """
    Triggers a re-tagging and re-scanning of a file based on its absolute path.
    Useful for external integrations like LMS.
    """
    filepath = path
    helper = ProcessedFilesHelper()
    helper.mark_for_rescan(filepath, reason='rerun_parse')
    try:
        from services.music_manager.routers.scanner import scanner_manager
        from services.music_manager.routers.tagger import tagger_manager

        tagger_manager.tag_single(filepath)
        logging.info(f'Successfully executed immediate tagger rescan for {filepath}')
        scanner_manager.scan_single(filepath)
        logging.info(f'Successfully executed immediate scanner for {filepath}')
    except Exception as e:
        logging.warning(f'Could not execute immediate rescan/scan for path {filepath}: {e}')
    return {'status': 'ok', 'message': f'Track at {filepath} marked for rescan and immediate trigger attempted'}


@router.post('/tracks/{track_id}/redownload')
def redownload_track(track_id: int, background_tasks: BackgroundTasks, _auth: dict = Depends(verify_api_key)):
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
            cursor.execute(
                'SELECT url FROM downloads_soundcloud_archive WHERE filename LIKE %s LIMIT 1', (f'%{filename}%',)
            )
            res = cursor.fetchone()
            if res:
                source_url = res['url']
                source_type = 'soundcloud'
            if not source_url:
                cursor.execute(
                    'SELECT url FROM downloads_youtube_archive WHERE filename LIKE %s LIMIT 1', (f'%{filename}%',)
                )
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
