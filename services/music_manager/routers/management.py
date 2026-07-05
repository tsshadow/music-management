from fastapi import APIRouter, HTTPException, Header, Depends, Body, BackgroundTasks
from fastapi.responses import HTMLResponse
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import os
import docker
import requests
import markdown
from datetime import datetime
from services.music_manager.database import get_db_connection
from services.common.api.version_helper import get_version, get_release_notes, get_changelog

router = APIRouter(prefix="/api", tags=["management"])

class ArtistGenreRule(BaseModel):
    artist_name: str
    genre_id: int

class LabelGenreRule(BaseModel):
    label_name: str
    genre_id: int

API_KEY = os.getenv("API_KEY") or os.getenv("MUMA_API_KEY") or "453ecd33-3cb2-4ca4-a531-1677330bbaee"

def verify_api_key(x_api_key: Optional[str] = Header(None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API Key")
    if API_KEY and x_api_key == API_KEY:
        return {"type": "system"}
    
    # Check users table for this API Key
    from services.music_manager.routers.users import verify_token
    try:
        res = verify_token(x_api_key)
        if res.get("status") == "ok":
            return res
    except:
        pass
        
    raise HTTPException(status_code=401, detail="Invalid API key")

def init_db(cursor):
    pass

@router.post("/auth/login")
def login_proxy(req: Dict[str, Any] = Body(...)):
    from services.music_manager.routers.users import login, LoginRequest
    return login(LoginRequest(**req))

@router.get("/auth/verify")
def verify_proxy(x_api_key: str = Header(None)):
    from services.music_manager.routers.users import verify_token
    return verify_token(x_api_key)

@router.get("/users")
def get_users_proxy(auth: dict = Depends(verify_api_key)):
    from services.music_manager.routers.users import get_users
    return get_users(auth)

@router.post("/users")
def create_user_proxy(user: Dict[str, Any] = Body(...), auth: dict = Depends(verify_api_key)):
    from services.music_manager.routers.users import create_user, UserCreate
    return create_user(UserCreate(**user), auth)

@router.get("/users/{user_id}/dynamic-playlists")
def get_playlists_proxy(user_id: int, auth: dict = Depends(verify_api_key)):
    from services.music_manager.routers.users import get_dynamic_playlists
    return get_dynamic_playlists(user_id, auth)

@router.get("/users/{user_id}/lb-account")
def get_lb_account_proxy(user_id: int, auth: dict = Depends(verify_api_key)):
    from services.music_manager.routers.users import get_lb_account
    return get_lb_account(user_id, auth)

@router.put("/users/{user_id}/lb-account")
def update_lb_account_proxy(user_id: int, lb_data: Dict[str, Any] = Body(...), auth: dict = Depends(verify_api_key)):
    from services.music_manager.routers.users import update_lb_account, LBAccountUpdate
    return update_lb_account(user_id, LBAccountUpdate(**lb_data), auth)

@router.delete("/users/{user_id}")
def delete_user_proxy(user_id: int, auth: dict = Depends(verify_api_key)):
    from services.music_manager.routers.users import delete_user
    return delete_user(user_id, auth)

@router.put("/users/{user_id}/password")
def update_password_proxy(user_id: int, req: Dict[str, Any] = Body(...), auth: dict = Depends(verify_api_key)):
    from services.music_manager.routers.users import update_password, PasswordUpdate
    return update_password(user_id, PasswordUpdate(**req), auth)

@router.get("/users/{user_id}/settings/{app_id}")
def get_user_settings_proxy(user_id: int, app_id: str, auth: dict = Depends(verify_api_key)):
    from services.music_manager.routers.users import get_user_app_settings
    return get_user_app_settings(user_id, app_id, auth)

@router.post("/users/{user_id}/settings/{app_id}")
def update_user_settings_proxy(user_id: int, app_id: str, req: Dict[str, Any] = Body(...), auth: dict = Depends(verify_api_key)):
    from services.music_manager.routers.users import update_user_app_settings, AppSettingsUpdate
    return update_user_app_settings(user_id, app_id, AppSettingsUpdate(**req), auth)

@router.get("/users/{user_id}/dynamic-playlists/{playlist_id}/tracks")
def get_playlist_tracks_proxy(user_id: int, playlist_id: int, auth: dict = Depends(verify_api_key)):
    from services.music_manager.routers.users import get_playlist_tracks
    return get_playlist_tracks(user_id, playlist_id, auth)

@router.post("/users/{user_id}/dynamic-playlists")
def create_playlist_proxy(user_id: int, playlist: Dict[str, Any] = Body(...), auth: dict = Depends(verify_api_key)):
    from services.music_manager.routers.users import create_dynamic_playlist, DynamicPlaylistCreate
    return create_dynamic_playlist(user_id, DynamicPlaylistCreate(**playlist), auth)

@router.put("/users/{user_id}/dynamic-playlists/{playlist_id}")
def update_playlist_proxy(user_id: int, playlist_id: int, playlist: Dict[str, Any] = Body(...), auth: dict = Depends(verify_api_key)):
    from services.music_manager.routers.users import update_dynamic_playlist, DynamicPlaylistUpdate
    return update_dynamic_playlist(user_id, playlist_id, DynamicPlaylistUpdate(**playlist), auth)

@router.delete("/users/{user_id}/dynamic-playlists/{playlist_id}")
def delete_playlist_proxy(user_id: int, playlist_id: int, auth: dict = Depends(verify_api_key)):
    from services.music_manager.routers.users import delete_dynamic_playlist
    return delete_dynamic_playlist(user_id, playlist_id, auth)

@router.post("/users/{user_id}/dynamic-playlists/seed-defaults")
def seed_defaults_proxy(user_id: int, auth: dict = Depends(verify_api_key)):
    from services.music_manager.routers.users import seed_defaults
    return seed_defaults(user_id, auth)

@router.post("/users/sync/lms-db")
def sync_lms_db_proxy(background_tasks: BackgroundTasks, auth: dict = Depends(verify_api_key)):
    from services.music_manager.routers.users import sync_lms_db
    return sync_lms_db(background_tasks, auth)

@router.post("/users/sync/lms")
def sync_lms_proxy(background_tasks: BackgroundTasks, auth: dict = Depends(verify_api_key)):
    from services.music_manager.routers.users import sync_lms_db
    return sync_lms_db(background_tasks, auth)

@router.get("/rules")
def get_genre_rules(auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn: raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name, corrected_genre FROM rules_genres ORDER BY name")
            genres = cursor.fetchall()
            cursor.execute("SHOW TABLES LIKE 'rules_ignored_genres'")
            ignored = []
            if cursor.fetchone():
                cursor.execute("SELECT name FROM rules_ignored_genres ORDER BY name")
                ignored = [{"name": r['name']} for r in cursor.fetchall()]
            return {"genres": genres, "ignored_genres": ignored}
    finally:
        conn.close()

@router.get("/artists")
def search_artists(q: str = "", auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn: raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name FROM library_artists WHERE name LIKE %s LIMIT 50", (f"%{q}%",))
            return cursor.fetchall()
    finally:
        conn.close()

@router.get("/labels")
def search_labels(q: str = "", auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn: raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name FROM library_labels WHERE name LIKE %s LIMIT 50", (f"%{q}%",))
            return cursor.fetchall()
    finally:
        conn.close()

@router.get("/config")
def get_config(auth: dict = Depends(verify_api_key)):
    version = "1.0.8"
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "VERSION"), "r") as f:
            version = f.read().strip()
    except:
        pass
        
    return {
        "DB_HOST": os.getenv("DB_HOST"),
        "DB_NAME": os.getenv("DB_DB"),
        "VERSION": version,
        "PHPMYADMIN_URL": os.getenv("PHPMYADMIN_URL", "http://muma.teunschriks.nl:8002")
    }

@router.get("/about", response_class=HTMLResponse)
def get_about(auth: dict = Depends(verify_api_key)):
    readme_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "README.md")
    content = "# Music Manager\nDocumentation not found."
    if os.path.exists(readme_path):
        with open(readme_path, "r") as f:
            content = f.read()
    
    html = markdown.markdown(content, extensions=['fenced_code', 'tables'])
    return html

@router.get("/stats")
def get_stats_proxy(auth: dict = Depends(verify_api_key)):
    # Internal call to stats router logic
    from services.music_manager.routers.stats import get_stats
    return get_stats(auth)

@router.get("/system/containers")
def get_containers(auth: dict = Depends(verify_api_key)):
    try:
        client = docker.from_env()
        containers = []
        for container in client.containers.list(all=True):
            if any(name in container.name for name in ["muma", "music-management", "music-manager", "db", "lms"]):
                containers.append({
                    "id": container.short_id,
                    "name": container.name,
                    "status": container.status,
                    "image": container.image.tags[0] if container.image.tags else "unknown"
                })
        return sorted(containers, key=lambda x: x["name"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/system/logs/{name}")
def get_logs(name: str, tail: int = 200, auth: dict = Depends(verify_api_key)):
    try:
        client = docker.from_env()
        container = client.containers.get(name)
        logs = container.logs(tail=tail).decode('utf-8')
        return {"logs": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/system/activity")
def get_activity(limit: int = 20, auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn: raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            # Recent added
            cursor.execute("""
                SELECT t.title, a.name as artist, CAST(t.created_at AS CHAR) as timestamp
                FROM library_tracks t
                JOIN library_artists a ON t.primary_artist_id = a.id
                ORDER BY t.created_at DESC
                LIMIT %s
            """, (limit,))
            recent_added = cursor.fetchall()

            # Recent tagged
            cursor.execute("""
                SELECT t.title, a.name as artist, CAST(ml.updated_at AS CHAR) as timestamp
                FROM library_track_ml_labels ml
                JOIN library_tracks t ON ml.track_id = t.track_uid
                LEFT JOIN library_artists a ON t.primary_artist_id = a.id
                WHERE ml.ml_genre IS NOT NULL
                ORDER BY ml.updated_at DESC
                LIMIT %s
            """, (limit,))
            recent_tagged = cursor.fetchall()

            return {"recent_added": recent_added, "recent_tagged": recent_tagged}
    finally:
        conn.close()

@router.get("/notes")
def get_notes(auth: dict = Depends(verify_api_key)):
    return {
        "release_notes": get_release_notes(),
        "changelog": get_changelog()
    }

@router.get("/all-notes")
def get_all_notes(auth: dict = Depends(verify_api_key)):
    return {
        "release_notes": get_release_notes(),
        "changelog": get_changelog()
    }

@router.get("/versions")
def get_versions(auth: dict = Depends(verify_api_key)):
    version = get_version()
    return {
        "music-manager": version,
        "muma-tagger": version,
        "muma-scanner": version,
        "muma-downloader": version,
        "muma-importer": version,
        "ultrasonic": "unknown"
    }

@router.get("/soundcloud")
def get_soundcloud_accounts(auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn: raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT name, soundcloud_id FROM downloads_soundcloud_accounts")
            return cursor.fetchall()
    finally:
        conn.close()

@router.post("/soundcloud")
def add_soundcloud_account(req: Dict[str, Any] = Body(...), auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn: raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO downloads_soundcloud_accounts (name, soundcloud_id) 
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE soundcloud_id = VALUES(soundcloud_id)
            """, (req.get('name'), req.get('soundcloud_id')))
            conn.commit()
            return {"status": "ok", "message": "SoundCloud account toegevoegd"}
    finally:
        conn.close()

@router.delete("/soundcloud/{name}")
def delete_soundcloud_account(name: str, auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn: raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM downloads_soundcloud_accounts WHERE name = %s", (name,))
            conn.commit()
            return {"status": "ok"}
    finally:
        conn.close()

@router.get("/youtube")
def get_youtube_accounts(auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn: raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT name, channel_id FROM downloads_youtube_accounts")
            return cursor.fetchall()
    finally:
        conn.close()

@router.post("/youtube")
def add_youtube_account(req: Dict[str, Any] = Body(...), auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn: raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO downloads_youtube_accounts (name, download_type) 
                VALUES (%s, 'audio')
                ON DUPLICATE KEY UPDATE name = name
            """, (req.get('name'),))
            conn.commit()
            return {"status": "ok", "message": "YouTube account toegevoegd"}
    finally:
        conn.close()

@router.delete("/youtube/{name}")
def delete_youtube_account(name: str, auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn: raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM downloads_youtube_accounts WHERE name = %s", (name,))
            conn.commit()
            return {"status": "ok"}
    finally:
        conn.close()


@router.get("/rules/artist-genres")
def get_artist_genre_rules(auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn: raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT r.id, r.artist_name, g.name as genre_name, r.genre_id
                FROM rules_artist_genres r
                JOIN rules_genres g ON r.genre_id = g.id
                ORDER BY r.artist_name
            """)
            return cursor.fetchall()
    finally:
        conn.close()

@router.post("/rules/artist-genres")
def add_artist_genre_rule(rule: ArtistGenreRule, auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn: raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO rules_artist_genres (artist_name, genre_id)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE genre_id = VALUES(genre_id)
            """, (rule.artist_name, rule.genre_id))
            conn.commit()
            return {"status": "ok"}
    finally:
        conn.close()

@router.delete("/rules/artist-genres/{rule_id}")
def delete_artist_genre_rule(rule_id: int, auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn: raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM rules_artist_genres WHERE id = %s", (rule_id,))
            conn.commit()
            return {"status": "ok"}
    finally:
        conn.close()

@router.get("/rules/label-genres")
def get_label_genre_rules(auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn: raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT r.id, r.label_name, g.name as genre_name, r.genre_id
                FROM rules_label_genres r
                JOIN rules_genres g ON r.genre_id = g.id
                ORDER BY r.label_name
            """)
            return cursor.fetchall()
    finally:
        conn.close()

@router.post("/rules/label-genres")
def add_label_genre_rule(rule: LabelGenreRule, auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn: raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO rules_label_genres (label_name, genre_id)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE genre_id = VALUES(genre_id)
            """, (rule.label_name, rule.genre_id))
            conn.commit()
            return {"status": "ok"}
    finally:
        conn.close()

@router.delete("/rules/label-genres/{rule_id}")
def delete_label_genre_rule(rule_id: int, auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn: raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM rules_label_genres WHERE id = %s", (rule_id,))
            conn.commit()
            return {"status": "ok"}
    finally:
        conn.close()


@router.get("/scrobble/import/latest")
def get_latest_scrobble_imports_proxy(auth: dict = Depends(verify_api_key)):
    from services.music_manager.routers.scrobbler import get_latest_imports
    return get_latest_imports()

@router.post("/scrobble/import/listenbrainz")
def trigger_lb_import_proxy(background_tasks: BackgroundTasks, req: Dict[str, Any] = Body(...), auth: dict = Depends(verify_api_key)):
    from services.music_manager.routers.scrobbler import trigger_lb_import, ImportRequest
    return trigger_lb_import(ImportRequest(**req), background_tasks)
