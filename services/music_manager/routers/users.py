# pylint: disable=cyclic-import
import json
import os
import secrets
import sqlite3
from typing import Optional

import bcrypt
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Header
from pydantic import BaseModel

from services.music_manager.database import get_db_connection

router = APIRouter(prefix="/users", tags=["users"])

MUMA_API_KEY = os.getenv("MUMA_API_KEY") or "453ecd33-3cb2-4ca4-a531-1677330bbaee"
LMS_API_KEY = os.getenv("LMS_API_KEY") or MUMA_API_KEY
API_KEY = os.getenv("API_KEY") or LMS_API_KEY
LMS_SUBSONIC_API_KEY = os.getenv("LMS_SUBSONIC_API_KEY") or API_KEY

async def verify_api_key(x_api_key: str = Header(None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API Key")
    if API_KEY and x_api_key == API_KEY:
        return {"type": "system"}

    # Check users table for this API Key
    res = verify_token(x_api_key)
    if res.get("status") == "ok":
        return res

    raise HTTPException(status_code=401, detail="Invalid API Key")

class UserCreate(BaseModel):
    username: str
    display_name: Optional[str] = None
    is_admin: Optional[bool] = False
    lms_user_id: Optional[str] = None
    api_key: Optional[str] = None
    password: Optional[str] = None

class UserUpdate(BaseModel):
    username: Optional[str] = None
    display_name: Optional[str] = None
    is_admin: Optional[bool] = None
    lms_user_id: Optional[str] = None
    api_key: Optional[str] = None

class LBAccountUpdate(BaseModel):
    lb_username: str
    lb_token: str

class DynamicPlaylistCreate(BaseModel):
    name: str
    params: str

class DynamicPlaylistUpdate(BaseModel):
    name: Optional[str] = None
    params: Optional[str] = None

class DynamicPlaylistSync(BaseModel):
    remote_id: int
    lms_user_id: Optional[str] = None
    source: str
    name: str
    params: str

class PasswordUpdate(BaseModel):
    password: str

class AppSettingsUpdate(BaseModel):
    settings: str

class LoginRequest(BaseModel):
    username: str
    password: str

def init_db(cursor):
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            display_name VARCHAR(255),
            is_admin BOOLEAN DEFAULT FALSE,
            password_hash VARCHAR(255),
            api_key VARCHAR(255),
            lms_user_id VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("SHOW COLUMNS FROM users LIKE 'is_admin'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE AFTER display_name")
    cursor.execute("SHOW COLUMNS FROM users LIKE 'password_hash'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) AFTER display_name")
    cursor.execute("SHOW COLUMNS FROM users LIKE 'api_key'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE users ADD COLUMN api_key VARCHAR(255) AFTER password_hash")

    # ListenBrainz accounts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_listenbrainz_accounts (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            lb_username VARCHAR(255) NOT NULL,
            lb_token VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY (user_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # Dynamic Playlists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dynamic_playlists (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            remote_id INT,
            source VARCHAR(50),
            name VARCHAR(255) NOT NULL,
            params TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("SHOW COLUMNS FROM dynamic_playlists LIKE 'remote_id'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE dynamic_playlists ADD COLUMN remote_id INT AFTER user_id")
    cursor.execute("SHOW COLUMNS FROM dynamic_playlists LIKE 'source'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE dynamic_playlists ADD COLUMN source VARCHAR(50) AFTER remote_id")
    try:
        cursor.execute("ALTER TABLE dynamic_playlists ADD UNIQUE INDEX uq_source_remote_id (source, remote_id)")
    except Exception:
        pass

    # User App Settings
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_app_settings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            app_id VARCHAR(50) NOT NULL,
            settings_json LONGTEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY (user_id, app_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

@router.get("/auth/verify")
def verify_token(x_api_key: str = Header(None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API Key")
    if API_KEY and x_api_key == API_KEY:
        return {"status": "ok", "type": "system"}
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id, username, display_name, is_admin FROM users WHERE api_key = %s", (x_api_key,))
                user = cursor.fetchone()
                if user:
                    return {"status": "ok", "type": "user", "user": user}
        finally:
            conn.close()
    raise HTTPException(status_code=403, detail="Invalid API Key")

@router.post("/auth/login")
def login(req: LoginRequest):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE username = %s", (req.username,))
            user = cursor.fetchone()
            if not user or not user['password_hash']:
                raise HTTPException(status_code=401, detail="Invalid username or password")
            stored_hash = user['password_hash']
            if bcrypt.checkpw(req.password.encode('utf-8'), stored_hash.encode('utf-8')):
                if not user['is_admin']:
                    raise HTTPException(status_code=403, detail="Admin rechten vereist")
                api_key = user['api_key']
                if not api_key:
                    api_key = secrets.token_hex(32)
                    cursor.execute("UPDATE users SET api_key = %s WHERE id = %s", (api_key, user['id']))
                    conn.commit()
                return {"id": user['id'], "username": user['username'], "display_name": user['display_name'], "is_admin": bool(user['is_admin']), "api_key": api_key}
            raise HTTPException(status_code=401, detail="Invalid username or password")
    finally:
        conn.close()

@router.get("/{user_id}/dynamic-playlists")
def get_dynamic_playlists(user_id: int, auth: dict = Depends(verify_api_key)):
    if auth.get("type") == "user" and auth['user']['id'] != user_id and not auth['user'].get('is_admin'):
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="DB failed")
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM dynamic_playlists WHERE user_id = %s", (user_id,))
            return cursor.fetchall()
    finally:
        conn.close()

@router.get("/{user_id}/dynamic-playlists/{playlist_id}")
def get_dynamic_playlist(user_id: int, playlist_id: int, auth: dict = Depends(verify_api_key)):
    if auth.get("type") == "user" and auth['user']['id'] != user_id and not auth['user'].get('is_admin'):
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM dynamic_playlists WHERE id = %s AND user_id = %s", (playlist_id, user_id))
            res = cursor.fetchone()
            if not res:
                raise HTTPException(status_code=404)
            return res
    finally:
        conn.close()

@router.post("/{user_id}/dynamic-playlists")
def create_dynamic_playlist(user_id: int, playlist: DynamicPlaylistCreate, auth: dict = Depends(verify_api_key)):
    if auth.get("type") == "user" and auth['user']['id'] != user_id and not auth['user'].get('is_admin'):
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO dynamic_playlists (user_id, name, params) VALUES (%s, %s, %s)",
                          (user_id, playlist.name, playlist.params))
            conn.commit()
            return {"status": "ok", "id": cursor.lastrowid}
    finally:
        conn.close()

@router.put("/{user_id}/dynamic-playlists/{playlist_id}")
def update_dynamic_playlist(user_id: int, playlist_id: int, playlist: DynamicPlaylistUpdate, auth: dict = Depends(verify_api_key)):
    if auth.get("type") == "user" and auth['user']['id'] != user_id and not auth['user'].get('is_admin'):
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            if playlist.name and playlist.params:
                cursor.execute("UPDATE dynamic_playlists SET name = %s, params = %s WHERE id = %s AND user_id = %s",
                              (playlist.name, playlist.params, playlist_id, user_id))
            elif playlist.name:
                cursor.execute("UPDATE dynamic_playlists SET name = %s WHERE id = %s AND user_id = %s",
                              (playlist.name, playlist_id, user_id))
            elif playlist.params:
                cursor.execute("UPDATE dynamic_playlists SET params = %s WHERE id = %s AND user_id = %s",
                              (playlist.params, playlist_id, user_id))
            conn.commit()
            return {"status": "ok"}
    finally:
        conn.close()

@router.delete("/{user_id}/dynamic-playlists/{playlist_id}")
def delete_dynamic_playlist(user_id: int, playlist_id: int, auth: dict = Depends(verify_api_key)):
    if auth.get("type") == "user" and auth['user']['id'] != user_id and not auth['user'].get('is_admin'):
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM dynamic_playlists WHERE id = %s AND user_id = %s", (playlist_id, user_id))
            conn.commit()
            return {"status": "ok"}
    finally:
        conn.close()

@router.get("/{user_id}/dynamic-playlists/{playlist_id}/tracks")
def get_playlist_tracks(user_id: int, playlist_id: int, auth: dict = Depends(verify_api_key)):
    if auth.get("type") == "user" and auth['user']['id'] != user_id and not auth['user'].get('is_admin'):
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT params FROM dynamic_playlists WHERE id = %s AND user_id = %s", (playlist_id, user_id))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404)

            params_str = row['params']
            try:
                params = json.loads(params_str)
            except json.JSONDecodeError:
                params = {}

            rules = params.get('rules', [])

            query = """
                SELECT t.id, t.title, COALESCE(a.name, 'Unknown Artist') as artist, CAST(t.created_at AS CHAR) as created_at
                FROM library_tracks t
                LEFT JOIN library_artists a ON t.primary_artist_id = a.id
                WHERE 1=1
            """
            q_params = []

            for rule in rules:
                col = rule.get('column')
                val = rule.get('value')
                if not col or not val:
                    continue

                if col == 'genre':
                    query += """ AND (
                        EXISTS (SELECT 1 FROM library_track_genres tg JOIN rules_genres rg ON tg.genre_id = rg.id WHERE tg.track_id = t.id AND rg.name = %s)
                        OR EXISTS (SELECT 1 FROM library_track_ml_labels ml WHERE ml.track_id = t.track_uid AND ml.ml_genre = %s)
                    )"""
                    q_params.extend([val, val])
                elif col == 'artist':
                    query += " AND a.name LIKE %s"
                    q_params.append(f"%{val}%")

            query += " ORDER BY t.created_at DESC LIMIT 500"
            cursor.execute(query, tuple(q_params))
            return cursor.fetchall()
    finally:
        conn.close()

@router.post("/{user_id}/dynamic-playlists/seed-defaults")
def seed_defaults(user_id: int, auth: dict = Depends(verify_api_key)):
    if auth.get("type") == "user" and auth['user']['id'] != user_id and not auth['user'].get('is_admin'):
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            defaults = [
                ("Hardstyle", json.dumps({"rules":[{"column":"genre","operator":"is","value":"Hardstyle"}]})),
                ("Hardcore", json.dumps({"rules":[{"column":"genre","operator":"is","value":"Hardcore"}]})),
                ("Techno", json.dumps({"rules":[{"column":"genre","operator":"is","value":"Techno"}]})),
                ("Recently Added", json.dumps({"rules":[], "sort":"created_at", "order":"desc"}))
            ]
            for name, params in defaults:
                cursor.execute("""
                    INSERT INTO dynamic_playlists (user_id, name, params, source)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE params = VALUES(params)
                """, (user_id, name, params, "default"))
            conn.commit()
            return {"status": "ok"}
    finally:
        conn.close()

@router.post("/{user_id}/dynamic-playlists/sync")
def sync_dynamic_playlist(user_id: int, playlist: DynamicPlaylistSync, auth: dict = Depends(verify_api_key)):
    if auth.get("type") == "user" and auth['user']['id'] != user_id and not auth['user'].get('is_admin'):
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="DB failed")
    try:
        with conn.cursor() as cursor:
            target_user_id = user_id
            if playlist.lms_user_id:
                cursor.execute("SELECT id FROM users WHERE lms_user_id = %s", (str(playlist.lms_user_id),))
                user_row = cursor.fetchone()
                if user_row:
                    target_user_id = user_row['id']
            cursor.execute("""
                INSERT INTO dynamic_playlists (user_id, remote_id, source, name, params)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE name = VALUES(name), params = VALUES(params)
            """, (target_user_id, playlist.remote_id, playlist.source, playlist.name, playlist.params))
            conn.commit()
            return {"status": "synced"}
    finally:
        conn.close()

@router.get("/")
def get_users(auth: dict = Depends(verify_api_key)):
    if auth.get("type") == "user" and not auth['user'].get('is_admin'):
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="DB failed")
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, username, display_name, is_admin, lms_user_id, api_key FROM users")
            return cursor.fetchall()
    finally:
        conn.close()

@router.post("/")
def create_user(user: UserCreate, auth: dict = Depends(verify_api_key)):
    if auth.get("type") == "user" and not auth['user'].get('is_admin'):
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        password_hash = None
        if user.password:
            password_hash = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        token = user.api_key or secrets.token_hex(16)

        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO users (username, display_name, is_admin, password_hash, api_key, lms_user_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (user.username, user.display_name, user.is_admin, password_hash, token, user.lms_user_id))
            conn.commit()
            return {"status": "ok", "id": cursor.lastrowid}
    finally:
        conn.close()

@router.get("/{user_id}/lb-account")
def get_lb_account(user_id: int, auth: dict = Depends(verify_api_key)):
    if auth.get("type") == "user" and auth['user']['id'] != user_id and not auth['user'].get('is_admin'):
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="DB failed")
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT lb_username, lb_token FROM user_listenbrainz_accounts WHERE user_id = %s", (user_id,))
            res = cursor.fetchone()
            return res or {"lb_username": "", "lb_token": ""}
    finally:
        conn.close()

@router.put("/{user_id}/lb-account")
def update_lb_account(user_id: int, lb_data: LBAccountUpdate, auth: dict = Depends(verify_api_key)):
    if auth.get("type") == "user" and auth['user']['id'] != user_id and not auth['user'].get('is_admin'):
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="DB failed")
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO user_listenbrainz_accounts (user_id, lb_username, lb_token)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE lb_username = VALUES(lb_username), lb_token = VALUES(lb_token)
            """, (user_id, lb_data.lb_username, lb_data.lb_token))
            conn.commit()
            return {"status": "ok"}
    finally:
        conn.close()

@router.delete("/{user_id}")
def delete_user(user_id: int, auth: dict = Depends(verify_api_key)):
    if auth.get("type") == "user" and auth['user']['id'] != user_id and not auth['user'].get('is_admin'):
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()
            return {"status": "ok"}
    finally:
        conn.close()

@router.put("/{user_id}/password")
def update_password(user_id: int, req: PasswordUpdate, auth: dict = Depends(verify_api_key)):
    if auth.get("type") == "user" and auth['user']['id'] != user_id and not auth['user'].get('is_admin'):
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        password_hash = bcrypt.hashpw(req.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        with conn.cursor() as cursor:
            cursor.execute("UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, user_id))
            conn.commit()
            return {"status": "ok"}
    finally:
        conn.close()

@router.get("/{user_id}/settings/{app_id}")
def get_user_app_settings(user_id: int, app_id: str, auth: dict = Depends(verify_api_key)):
    if auth.get("type") == "user" and auth['user']['id'] != user_id and not auth['user'].get('is_admin'):
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT settings_json, CAST(updated_at AS CHAR) as updated_at FROM user_app_settings WHERE user_id = %s AND app_id = %s", (user_id, app_id))
            res = cursor.fetchone()
            if not res:
                return {"settings": None}
            return {"settings": res['settings_json'], "updated_at": res['updated_at']}
    finally:
        conn.close()

@router.post("/{user_id}/settings/{app_id}")
def update_user_app_settings(user_id: int, app_id: str, req: AppSettingsUpdate, auth: dict = Depends(verify_api_key)):
    if auth.get("type") == "user" and auth['user']['id'] != user_id and not auth['user'].get('is_admin'):
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO user_app_settings (user_id, app_id, settings_json)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE settings_json = VALUES(settings_json)
            """, (user_id, app_id, req.settings))
            conn.commit()
            return {"status": "ok"}
    finally:
        conn.close()

@router.post("/sync/lms-db")
def sync_lms_db(background_tasks: BackgroundTasks, _api_key: str = Depends(verify_api_key)):
    background_tasks.add_task(run_lms_db_sync)
    return {"message": "LMS DB sync started in background"}

def _sync_lms_users(cursor, sqlite_cursor):
    sqlite_cursor.execute("SELECT id, login_name, listenbrainz_token FROM user")
    lms_users = sqlite_cursor.fetchall()
    for lms_id, username, lb_token in lms_users:
        cursor.execute("""
            INSERT INTO users (username, display_name, lms_user_id)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE lms_user_id = VALUES(lms_user_id)
        """, (username, username, lms_id))

        if lb_token:
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            user_row = cursor.fetchone()
            if user_row:
                cursor.execute("""
                    INSERT INTO user_listenbrainz_accounts (user_id, lb_username, lb_token)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE lb_token = VALUES(lb_token)
                """, (user_row['id'], username, lb_token))

def _sync_lms_playlists(cursor, sqlite_cursor, source):
    try:
        sqlite_cursor.execute("PRAGMA table_info(tracklist)")
        columns = [col[1] for col in sqlite_cursor.fetchall()]
        if "smart_params" in columns:
            sqlite_cursor.execute("SELECT id, user_id, name, smart_params FROM tracklist WHERE type = 2")
            for lms_id, lms_user_ptr, name, params in sqlite_cursor.fetchall():
                cursor.execute("SELECT id FROM users WHERE lms_user_id = %s", (str(lms_user_ptr),))
                u_row = cursor.fetchone()
                if u_row:
                    cursor.execute("""
                        INSERT INTO dynamic_playlists (user_id, remote_id, source, name, params)
                        VALUES (%s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE name = VALUES(name), params = VALUES(params)
                    """, (u_row['id'], lms_id, source, name, params))
    except Exception as pe: # pylint: disable=broad-except
        print(f"Playlist sync failed for {source}: {pe}")

def sync_single_lms_db(muma_conn, db_path, source):
    print(f"Syncing LMS DB: {db_path} ({source})")
    try:
        sqlite_conn = sqlite3.connect(db_path)
        sqlite_cursor = sqlite_conn.cursor()

        with muma_conn.cursor() as cursor:
            # 1. Sync Users
            _sync_lms_users(cursor, sqlite_cursor)
            muma_conn.commit()

            # 2. Sync Dynamic Playlists (Smart Playlists)
            _sync_lms_playlists(cursor, sqlite_cursor, source)
            muma_conn.commit()

        # 3. Sync Artist Images back to LMS
        from services.music_manager.routers.artist_images import sync_artist_images_to_lms # pylint: disable=import-outside-toplevel
        sync_artist_images_to_lms(muma_conn, sqlite_conn)

        sqlite_conn.close()
    except Exception as e: # pylint: disable=broad-except
        print(f"Sync failed for {db_path}: {e}")

def run_lms_db_sync():
    db_root = os.getenv("LMS_DB_ROOT", "/app/data")
    targets = []
    if os.path.exists(db_root):
        for entry in os.listdir(db_root):
            full_path = os.path.join(db_root, entry)
            if os.path.isdir(full_path):
                db_file = os.path.join(full_path, "lms.db")
                if os.path.exists(db_file):
                    targets.append((db_file, f"lms-{entry}"))
    conn = get_db_connection()
    if not conn:
        return
    try:
        for db_path, source in targets:
            sync_single_lms_db(conn, db_path, source)
    finally:
        conn.close()
