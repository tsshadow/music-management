import os
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Header, Depends, Body, BackgroundTasks
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import markdown
import docker
from services.common.version_helper import get_version, get_release_notes, get_changelog
from services.music_manager.database import get_db_connection
from services.common.Helpers.ProcessedFilesHelper import ProcessedFilesHelper
router = APIRouter(prefix='/api', tags=['management'])

class ArtistGenreRule(BaseModel):
    artist_name: str
    genre_id: int

class LabelGenreRule(BaseModel):
    label_name: str
    genre_id: int
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

@router.post('/auth/login')
def login_proxy(req: Dict[str, Any]=Body(...)):
    from services.music_manager.routers.users import login, LoginRequest
    return login(LoginRequest(**req))

@router.get('/auth/verify')
def verify_proxy(x_api_key: str=Header(None)):
    from services.music_manager.routers.users import verify_token
    return verify_token(x_api_key)

@router.get('/users')
def get_users_proxy(_auth: dict=Depends(verify_api_key)):
    from services.music_manager.routers.users import get_users
    return get_users(_auth)

@router.post('/users')
def create_user_proxy(user: Dict[str, Any]=Body(...), _auth: dict=Depends(verify_api_key)):
    from services.music_manager.routers.users import create_user, UserCreate
    return create_user(UserCreate(**user), _auth)

@router.get('/users/{user_id}/dynamic-playlists')
def get_playlists_proxy(user_id: int, _auth: dict=Depends(verify_api_key)):
    from services.music_manager.routers.users import get_dynamic_playlists
    return get_dynamic_playlists(user_id, _auth)

@router.get('/users/{user_id}/lb-account')
def get_lb_account_proxy(user_id: int, _auth: dict=Depends(verify_api_key)):
    from services.music_manager.routers.users import get_lb_account
    return get_lb_account(user_id, _auth)

@router.put('/users/{user_id}/lb-account')
def update_lb_account_proxy(user_id: int, lb_data: Dict[str, Any]=Body(...), _auth: dict=Depends(verify_api_key)):
    from services.music_manager.routers.users import update_lb_account, LBAccountUpdate
    return update_lb_account(user_id, LBAccountUpdate(**lb_data), _auth)

@router.delete('/users/{user_id}')
def delete_user_proxy(user_id: int, _auth: dict=Depends(verify_api_key)):
    from services.music_manager.routers.users import delete_user
    return delete_user(user_id, _auth)

@router.put('/users/{user_id}/password')
def update_password_proxy(user_id: int, req: Dict[str, Any]=Body(...), _auth: dict=Depends(verify_api_key)):
    from services.music_manager.routers.users import update_password, PasswordUpdate
    return update_password(user_id, PasswordUpdate(**req), _auth)

@router.get('/users/{user_id}/settings/{app_id}')
def get_user_settings_proxy(user_id: int, app_id: str, _auth: dict=Depends(verify_api_key)):
    from services.music_manager.routers.users import get_user_app_settings
    return get_user_app_settings(user_id, app_id, _auth)

@router.post('/users/{user_id}/settings/{app_id}')
def update_user_settings_proxy(user_id: int, app_id: str, req: Dict[str, Any]=Body(...), _auth: dict=Depends(verify_api_key)):
    from services.music_manager.routers.users import update_user_app_settings, AppSettingsUpdate
    return update_user_app_settings(user_id, app_id, AppSettingsUpdate(**req), _auth)

@router.get('/users/{user_id}/dynamic-playlists/{playlist_id}/tracks')
def get_playlist_tracks_proxy(user_id: int, playlist_id: int, _auth: dict=Depends(verify_api_key)):
    from services.music_manager.routers.users import get_playlist_tracks
    return get_playlist_tracks(user_id, playlist_id, _auth)

@router.post('/users/{user_id}/dynamic-playlists')
def create_playlist_proxy(user_id: int, playlist: Dict[str, Any]=Body(...), _auth: dict=Depends(verify_api_key)):
    from services.music_manager.routers.users import create_dynamic_playlist, DynamicPlaylistCreate
    return create_dynamic_playlist(user_id, DynamicPlaylistCreate(**playlist), _auth)

@router.put('/users/{user_id}/dynamic-playlists/{playlist_id}')
def update_playlist_proxy(user_id: int, playlist_id: int, playlist: Dict[str, Any]=Body(...), _auth: dict=Depends(verify_api_key)):
    from services.music_manager.routers.users import update_dynamic_playlist, DynamicPlaylistUpdate
    return update_dynamic_playlist(user_id, playlist_id, DynamicPlaylistUpdate(**playlist), _auth)

@router.delete('/users/{user_id}/dynamic-playlists/{playlist_id}')
def delete_playlist_proxy(user_id: int, playlist_id: int, _auth: dict=Depends(verify_api_key)):
    from services.music_manager.routers.users import delete_dynamic_playlist
    return delete_dynamic_playlist(user_id, playlist_id, _auth)

@router.post('/users/{user_id}/dynamic-playlists/seed-defaults')
def seed_defaults_proxy(user_id: int, _auth: dict=Depends(verify_api_key)):
    from services.music_manager.routers.users import seed_defaults
    return seed_defaults(user_id, _auth)

@router.post('/users/sync/lms-db')
def sync_lms_db_proxy(background_tasks: BackgroundTasks, _auth: dict=Depends(verify_api_key)):
    from services.music_manager.routers.users import sync_lms_db
    return sync_lms_db(background_tasks, _auth)

@router.post('/users/sync/lms')
def sync_lms_proxy(background_tasks: BackgroundTasks, _auth: dict=Depends(verify_api_key)):
    from services.music_manager.routers.users import sync_lms_db
    return sync_lms_db(background_tasks, _auth)

@router.get('/rules')
def get_genre_rules(_auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT id, name, corrected_genre FROM rules_genres ORDER BY name')
            genres = cursor.fetchall()
            cursor.execute("SHOW TABLES LIKE 'rules_ignored_genres'")
            ignored = []
            if cursor.fetchone():
                cursor.execute('SELECT name FROM rules_ignored_genres ORDER BY name')
                ignored = [{'name': r['name']} for r in cursor.fetchall()]
            return {'genres': genres, 'ignored_genres': ignored}
    finally:
        conn.close()

@router.get('/artists')
def search_artists(q: str='', _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT id, name FROM library_artists WHERE name LIKE %s LIMIT 50', (f'%{q}%',))
            return cursor.fetchall()
    finally:
        conn.close()

@router.get('/labels')
def search_labels(q: str='', _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT id, name FROM library_labels WHERE name LIKE %s LIMIT 50', (f'%{q}%',))
            return cursor.fetchall()
    finally:
        conn.close()

@router.get('/config')
def get_config(_auth: dict=Depends(verify_api_key)):
    version = '1.3.0'
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'VERSION'), 'r', encoding='utf-8') as f:
            version = f.read().strip()
    except Exception:
        pass
    return {'DB_HOST': os.getenv('DB_HOST'), 'DB_NAME': os.getenv('DB_DB'), 'VERSION': version, 'PHPMYADMIN_URL': os.getenv('PHPMYADMIN_URL', 'http://muma.teunschriks.nl:8002')}

@router.get('/about', response_class=HTMLResponse)
def get_about(_auth: dict=Depends(verify_api_key)):
    readme_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'README.md')
    content = '# Music Manager\nDocumentation not found.'
    if os.path.exists(readme_path):
        with open(readme_path, 'r', encoding='utf-8') as f:
            content = f.read()
    html = markdown.markdown(content, extensions=['fenced_code', 'tables'])
    return html

@router.get('/stats')
def get_stats_proxy(_auth: dict=Depends(verify_api_key)):
    from services.music_manager.routers.stats import get_stats
    return get_stats(_auth)

@router.get('/system/containers')
def get_containers(_auth: dict=Depends(verify_api_key)):
    try:
        client = docker.from_env()
        containers = []
        for container in client.containers.list(all=True):
            if any((name in container.name for name in ['muma', 'music-management', 'music-manager', 'db', 'lms'])):
                containers.append({'id': container.short_id, 'name': container.name, 'status': container.status, 'image': container.image.tags[0] if container.image.tags else 'unknown'})
        return sorted(containers, key=lambda x: x['name'])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.get('/system/logs/{name}')
def get_logs(name: str, tail: int=200, _auth: dict=Depends(verify_api_key)):
    try:
        client = docker.from_env()
        container = client.containers.get(name)
        logs = container.logs(tail=tail).decode('utf-8')
        return {'logs': logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.get('/system/activity')
def get_activity(limit: int=20, _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('\n                SELECT t.title, a.name as artist, CAST(t.created_at AS CHAR) as timestamp\n                FROM library_tracks t\n                JOIN library_artists a ON t.primary_artist_id = a.id\n                ORDER BY t.created_at DESC\n                LIMIT %s\n            ', (limit,))
            recent_added = cursor.fetchall()
            cursor.execute('\n                SELECT t.title, a.name as artist, CAST(ml.updated_at AS CHAR) as timestamp\n                FROM library_track_ml_labels ml\n                JOIN library_tracks t ON ml.track_id = t.track_uid\n                LEFT JOIN library_artists a ON t.primary_artist_id = a.id\n                WHERE ml.ml_genre IS NOT NULL\n                ORDER BY ml.updated_at DESC\n                LIMIT %s\n            ', (limit,))
            recent_tagged = cursor.fetchall()
            return {'recent_added': recent_added, 'recent_tagged': recent_tagged}
    finally:
        conn.close()

@router.get('/notes')
def get_notes(_auth: dict=Depends(verify_api_key)):
    return {'release_notes': get_release_notes(), 'changelog': get_changelog()}

@router.get('/all-notes')
def get_all_notes(_auth: dict=Depends(verify_api_key)):
    return {'release_notes': get_release_notes(), 'changelog': get_changelog()}

@router.get('/versions')
def get_versions(_auth: dict=Depends(verify_api_key)):
    version = get_version()
    return {'music-manager': version, 'muma-tagger': version, 'muma-scanner': version, 'muma-downloader': version, 'muma-importer': version, 'ultrasonic': 'unknown'}

@router.get('/soundcloud')
def get_soundcloud_accounts(_auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT name, soundcloud_id FROM downloads_soundcloud_accounts')
            return cursor.fetchall()
    finally:
        conn.close()

@router.post('/soundcloud')
def add_soundcloud_account(req: Dict[str, Any]=Body(...), _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('\n                INSERT INTO downloads_soundcloud_accounts (name, soundcloud_id)\n                VALUES (%s, %s)\n                ON DUPLICATE KEY UPDATE soundcloud_id = VALUES(soundcloud_id)\n            ', (req.get('name'), req.get('soundcloud_id')))
            conn.commit()
            return {'status': 'ok', 'message': 'SoundCloud account toegevoegd'}
    finally:
        conn.close()

@router.delete('/soundcloud/{name}')
def delete_soundcloud_account(name: str, _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM downloads_soundcloud_accounts WHERE name = %s', (name,))
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()

@router.get('/youtube')
def get_youtube_accounts(_auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT name, channel_id FROM downloads_youtube_accounts')
            return cursor.fetchall()
    finally:
        conn.close()

@router.post('/youtube')
def add_youtube_account(req: Dict[str, Any]=Body(...), _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("\n                INSERT INTO downloads_youtube_accounts (name, download_type)\n                VALUES (%s, 'audio')\n                ON DUPLICATE KEY UPDATE name = name\n            ", (req.get('name'),))
            conn.commit()
            return {'status': 'ok', 'message': 'YouTube account toegevoegd'}
    finally:
        conn.close()

@router.delete('/youtube/{name}')
def delete_youtube_account(name: str, _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM downloads_youtube_accounts WHERE name = %s', (name,))
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()

@router.get('/rules/artist-genres')
def get_artist_genre_rules(_auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('\n                SELECT r.id, r.artist_name, g.name as genre_name, r.genre_id\n                FROM rules_artist_genres r\n                JOIN rules_genres g ON r.genre_id = g.id\n                ORDER BY r.artist_name\n            ')
            return cursor.fetchall()
    finally:
        conn.close()

@router.post('/rules/artist-genres')
def add_artist_genre_rule(rule: ArtistGenreRule, _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('\n                INSERT INTO rules_artist_genres (artist_name, genre_id)\n                VALUES (%s, %s)\n                ON DUPLICATE KEY UPDATE genre_id = VALUES(genre_id)\n            ', (rule.artist_name, rule.genre_id))
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()

@router.delete('/rules/artist-genres/{rule_id}')
def delete_artist_genre_rule(rule_id: int, _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM rules_artist_genres WHERE id = %s', (rule_id,))
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()

@router.get('/rules/label-genres')
def get_label_genre_rules(_auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('\n                SELECT r.id, r.label_name, g.name as genre_name, r.genre_id\n                FROM rules_label_genres r\n                JOIN rules_genres g ON r.genre_id = g.id\n                ORDER BY r.label_name\n            ')
            return cursor.fetchall()
    finally:
        conn.close()

@router.post('/rules/label-genres')
def add_label_genre_rule(rule: LabelGenreRule, _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('\n                INSERT INTO rules_label_genres (label_name, genre_id)\n                VALUES (%s, %s)\n                ON DUPLICATE KEY UPDATE genre_id = VALUES(genre_id)\n            ', (rule.label_name, rule.genre_id))
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()

@router.delete('/rules/label-genres/{rule_id}')
def delete_label_genre_rule(rule_id: int, _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM rules_label_genres WHERE id = %s', (rule_id,))
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()

@router.get('/scrobble/import/latest')
def get_latest_scrobble_imports_proxy(_auth: dict=Depends(verify_api_key)):
    from services.music_manager.routers.scrobbler import get_latest_imports
    return get_latest_imports()

@router.post('/scrobble/import/listenbrainz')
def trigger_lb_import_proxy(background_tasks: BackgroundTasks, req: Dict[str, Any]=Body(...), _auth: dict=Depends(verify_api_key)):
    from services.music_manager.routers.scrobbler import trigger_lb_import, ImportRequest
    return trigger_lb_import(ImportRequest(**req), background_tasks)

@router.post('/tagger/rescan')
def trigger_tagger_rescan(_auth: dict=Depends(verify_api_key)):
    helper = ProcessedFilesHelper()
    helper.mark_for_rescan()
    return {'status': 'ok', 'message': 'All files marked for rescan'}

@router.post('/tagger/rescan/file')
def trigger_file_rescan(filepath: str=Body(..., embed=True), _auth: dict=Depends(verify_api_key)):
    helper = ProcessedFilesHelper()
    helper.mark_for_rescan(filepath)
    return {'status': 'ok', 'message': f"File '{filepath}' marked for rescan"}