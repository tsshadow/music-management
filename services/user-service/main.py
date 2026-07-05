from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Header
from pydantic import BaseModel
import os
import pymysql
import requests
import sqlite3
import bcrypt
import secrets
import string
from typing import List, Optional
from dotenv import load_dotenv
from services.common.api.version_helper import get_version, get_release_notes, get_changelog

load_dotenv()

app = FastAPI(title="Muma User Service")

MUMA_API_KEY = os.getenv("MUMA_API_KEY") or "453ecd33-3cb2-4ca4-a531-1677330bbaee"
LMS_API_KEY = os.getenv("LMS_API_KEY") or MUMA_API_KEY
API_KEY = os.getenv("API_KEY") or LMS_API_KEY
LMS_SUBSONIC_API_KEY = os.getenv("LMS_SUBSONIC_API_KEY") or API_KEY

async def verify_api_key(x_api_key: str = Header(None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")
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

@app.on_event("startup")
def startup_db():
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
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
                # Add is_admin if it doesn't exist
                cursor.execute("SHOW COLUMNS FROM users LIKE 'is_admin'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE AFTER display_name")

                # Add password_hash if it doesn't exist (for existing tables)
                cursor.execute("SHOW COLUMNS FROM users LIKE 'password_hash'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) AFTER display_name")
                
                # Add api_key if it doesn't exist
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

                # Add remote_id and source to dynamic_playlists if they don't exist
                cursor.execute("SHOW COLUMNS FROM dynamic_playlists LIKE 'remote_id'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE dynamic_playlists ADD COLUMN remote_id INT AFTER user_id")
                
                cursor.execute("SHOW COLUMNS FROM dynamic_playlists LIKE 'source'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE dynamic_playlists ADD COLUMN source VARCHAR(50) AFTER remote_id")

                # Add unique index if it doesn't exist
                try:
                    cursor.execute("ALTER TABLE dynamic_playlists ADD UNIQUE INDEX uq_source_remote_id (source, remote_id)")
                except Exception:
                    pass
            conn.commit()
        finally:
            conn.close()

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

class LoginRequest(BaseModel):
    username: str
    password: str

@app.get("/version")
async def version(api_key: str = Depends(verify_api_key)):
    return {"version": get_version()}

@app.get("/release-notes")
async def release_notes(api_key: str = Depends(verify_api_key)):
    return {"notes": get_release_notes("services/user-service/RELEASE_NOTES.md")}

@app.get("/auth/verify")
async def verify_token(x_api_key: str = Header(None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API Key")
    
    # 1. Check system-wide key
    if API_KEY and x_api_key == API_KEY:
        return {"status": "ok", "type": "system"}
    
    # 2. Check user-specific keys
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

@app.post("/auth/login")
async def login(req: LoginRequest):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE username = %s", (req.username,))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=401, detail="Invalid username or password")
            
            if not user['password_hash']:
                 raise HTTPException(status_code=401, detail="User has no password set")

            # Password check
            # Note: LMS uses $2y$ but bcrypt in python often expects $2b$. 
            # We stored it as $2b$ in MariaDB but converted to $2y$ for LMS.
            stored_hash = user['password_hash']
            if bcrypt.checkpw(req.password.encode('utf-8'), stored_hash.encode('utf-8')):
                if not user['is_admin']:
                    raise HTTPException(status_code=403, detail="Toegang geweigerd: Admin rechten vereist")
                
                # Ensure user has an API key
                api_key = user['api_key']
                if not api_key:
                    api_key = secrets.token_hex(32)
                    cursor.execute("UPDATE users SET api_key = %s WHERE id = %s", (api_key, user['id']))
                    conn.commit()
                
                return {
                    "id": user['id'],
                    "username": user['username'],
                    "display_name": user['display_name'],
                    "is_admin": bool(user['is_admin']),
                    "api_key": api_key
                }
            else:
                raise HTTPException(status_code=401, detail="Invalid username or password")
    finally:
        conn.close()

# --- Dynamic Playlists ---

@app.get("/users/{user_id}/dynamic-playlists")
async def get_dynamic_playlists(user_id: int, api_key: str = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM dynamic_playlists WHERE user_id = %s", (user_id,))
            return cursor.fetchall()
    finally:
        conn.close()

@app.post("/users/{user_id}/dynamic-playlists")
async def create_dynamic_playlist(user_id: int, playlist: DynamicPlaylistCreate, api_key: str = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO dynamic_playlists (user_id, name, params) VALUES (%s, %s, %s)",
                (user_id, playlist.name, playlist.params)
            )
            playlist_id = cursor.lastrowid
            conn.commit()
            return {"id": playlist_id, "status": "created"}
    finally:
        conn.close()

@app.put("/users/{user_id}/dynamic-playlists/{playlist_id}")
async def update_dynamic_playlist(user_id: int, playlist_id: int, playlist: DynamicPlaylistUpdate, api_key: str = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    try:
        with conn.cursor() as cursor:
            updates = []
            values = []
            if playlist.name is not None:
                updates.append("name = %s")
                values.append(playlist.name)
            if playlist.params is not None:
                updates.append("params = %s")
                values.append(playlist.params)
            
            if not updates:
                return {"status": "no changes"}
            
            values.extend([playlist_id, user_id])
            query = f"UPDATE dynamic_playlists SET {', '.join(updates)} WHERE id = %s AND user_id = %s"
            cursor.execute(query, tuple(values))
            conn.commit()
            return {"status": "updated"}
    finally:
        conn.close()

@app.delete("/users/{user_id}/dynamic-playlists/{playlist_id}")
async def delete_dynamic_playlist(user_id: int, playlist_id: int, api_key: str = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM dynamic_playlists WHERE id = %s AND user_id = %s", (playlist_id, user_id))
            conn.commit()
            return {"status": "deleted"}
    finally:
        conn.close()

@app.post("/users/{user_id}/dynamic-playlists/sync")
async def sync_dynamic_playlist(user_id: int, playlist: DynamicPlaylistSync, api_key: str = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    try:
        with conn.cursor() as cursor:
            target_user_id = user_id
            
            # Try to resolve user_id via lms_user_id if provided
            if playlist.lms_user_id:
                cursor.execute("SELECT id FROM users WHERE lms_user_id = %s", (str(playlist.lms_user_id),))
                user_row = cursor.fetchone()
                if user_row:
                    target_user_id = user_row['id']

            if target_user_id == 0:
                raise HTTPException(status_code=400, detail="Valid user_id or lms_user_id required")

            cursor.execute("""
                INSERT INTO dynamic_playlists (user_id, remote_id, source, name, params)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE name = VALUES(name), params = VALUES(params)
            """, (target_user_id, playlist.remote_id, playlist.source, playlist.name, playlist.params))
            conn.commit()
            return {"status": "synced"}
    finally:
        conn.close()

@app.get("/users/{user_id}/dynamic-playlists/{playlist_id}/tracks")
async def resolve_dynamic_playlist_tracks(user_id: int, playlist_id: int, api_key: str = Depends(verify_api_key)):
    """
    Preview tracks for a dynamic playlist based on its parameters.
    MuMa acts as a central registry for playlist definitions (parameters),
    while tracks are resolved on-the-fly from the current library.
    """
    import json
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    try:
        with conn.cursor() as cursor:
            # 1. Get playlist params
            cursor.execute("SELECT params FROM dynamic_playlists WHERE id = %s AND user_id = %s", (playlist_id, user_id))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Playlist not found")
            
            try:
                params = json.loads(row['params'])
            except:
                raise HTTPException(status_code=400, detail="Invalid playlist parameters")
            
            # 2. Build query for library_tracks
            # Joining with artists and ML labels to get readable info
            query = """
                SELECT t.id, t.title, a.name as artist, 
                       COALESCE(ml.ml_genre, GROUP_CONCAT(DISTINCT g.name SEPARATOR ', ')) as genre, 
                       t.created_at
                FROM library_tracks t
                LEFT JOIN library_artists a ON t.primary_artist_id = a.id
                LEFT JOIN library_track_ml_labels ml ON t.track_uid = ml.track_id
                LEFT JOIN library_track_genres tg ON t.id = tg.track_id
                LEFT JOIN rules_genres g ON tg.genre_id = g.id
                WHERE 1=1
            """
            args = []
            
            if 'genre' in params and params['genre']:
                genres = params['genre'] if isinstance(params['genre'], list) else [params['genre']]
                
                genre_regex_filters = []
                regex_args = []
                for g_name in genres:
                    # Escape for regex: replace special chars
                    safe_g = g_name.replace('(', '\\(').replace(')', '\\)')
                    genre_regex_filters.append(f"ml.ml_genre REGEXP %s")
                    regex_args.append(f"(^|;){safe_g}(;|$)")
                
                query += f"""
                    AND (
                        {' OR '.join(genre_regex_filters)}
                        OR t.id IN (
                            SELECT track_id FROM library_track_genres tg2
                            JOIN rules_genres g2 ON tg2.genre_id = g2.id
                            WHERE g2.name IN ({', '.join(['%s'] * len(genres))})
                        )
                    )
                """
                args.extend(regex_args)
                args.extend(genres)
            
            query += " GROUP BY t.id"

            sort_method = params.get('sortMethod', 'DateDescAndRelease')
            if sort_method == 'DateDescAndRelease':
                query += " ORDER BY t.created_at DESC"
            elif sort_method == 'Random':
                query += " ORDER BY RAND()"
            
            limit = int(params.get('size', 50))
            query += " LIMIT %s"
            args.append(limit)
            
            cursor.execute(query, args)
            return cursor.fetchall()
    finally:
        conn.close()

@app.get("/users")
async def get_users(api_key: str = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users")
            return cursor.fetchall()
    finally:
        conn.close()

@app.post("/users")
async def create_user(user: UserCreate, api_key: str = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    password_hash = None
    lms_password_hash = None
    if user.password:
        salt = bcrypt.gensalt(rounds=12)
        password_hash = bcrypt.hashpw(user.password.encode('utf-8'), salt).decode('utf-8')
        lms_password_hash = password_hash.replace('$2b$', '$2y$')

    try:
        # Create in LMS first if possible to get lms_user_id
        lms_user_id = user.lms_user_id
        if not lms_user_id and lms_password_hash:
            lms_user_id = create_lms_user(user.username, lms_password_hash, user.is_admin)

        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (username, display_name, is_admin, lms_user_id, api_key, password_hash) VALUES (%s, %s, %s, %s, %s, %s)",
                (user.username, user.display_name, user.is_admin, lms_user_id, user.api_key, password_hash)
            )
            conn.commit()
            return {"id": cursor.lastrowid, "username": user.username, "lms_user_id": lms_user_id}
    except pymysql.err.IntegrityError:
        raise HTTPException(status_code=400, detail="Username already exists")
    finally:
        conn.close()

@app.delete("/users/{user_id}")
async def delete_user(user_id: int, api_key: str = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    try:
        with conn.cursor() as cursor:
            # Get LMS ID before deleting
            cursor.execute("SELECT lms_user_id FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Delete from MariaDB
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            
            # Delete from LMS DB if exists
            if user['lms_user_id']:
                delete_lms_user(user['lms_user_id'])
                
            conn.commit()
            # Trigger delete on all LMS hosts via Subsonic API
            lms_hosts_raw = os.getenv("LMS_HOSTS", "http://192.168.1.27")
            lms_hosts = [h.strip() for h in lms_hosts_raw.split(",")]
            lms_api_key = LMS_SUBSONIC_API_KEY
            for host in lms_hosts:
                try:
                    if not host.startswith("http"): host = f"http://{host}"
                    host = host.rstrip("/")
                    del_url = f"{host}/rest/deleteUser.view?v=1.16.1&c=muma-user-service&f=json&apiKey={lms_api_key}&username={user['username']}"
                    requests.get(del_url, headers={"X-API-Key": lms_api_key}, timeout=2.0)
                except:
                    pass

            # Trigger sync on all LMS hosts (to be sure)
            run_lms_sync()
            
            return {"status": "user deleted"}
    finally:
        conn.close()

@app.put("/users/{user_id}")
async def update_user(user_id: int, user_data: UserUpdate, api_key: str = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    try:
        with conn.cursor() as cursor:
            fields = []
            values = []
            if user_data.username is not None:
                fields.append("username = %s")
                values.append(user_data.username)
            if user_data.display_name is not None:
                fields.append("display_name = %s")
                values.append(user_data.display_name)
            if user_data.is_admin is not None:
                fields.append("is_admin = %s")
                values.append(user_data.is_admin)
            if user_data.lms_user_id is not None:
                fields.append("lms_user_id = %s")
                values.append(user_data.lms_user_id)
            if user_data.api_key is not None:
                fields.append("api_key = %s")
                values.append(user_data.api_key)
            
            if not fields:
                return {"status": "no changes"}
            
            query = f"UPDATE users SET {', '.join(fields)} WHERE id = %s"
            values.append(user_id)
            cursor.execute(query, tuple(values))

            # Forward to LMS if lms_user_id exists
            cursor.execute("SELECT username, is_admin, lms_user_id FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if user and user['lms_user_id']:
                update_lms_user_info(user['lms_user_id'], user['username'], user['is_admin'])

            conn.commit()
            
            # Trigger sync on all LMS hosts
            run_lms_sync()
            
            return {"status": "updated"}
    finally:
        conn.close()

@app.get("/users/{user_id}/lb-account")
async def get_lb_account(user_id: int, api_key: str = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM user_listenbrainz_accounts WHERE user_id = %s", (user_id,))
            return cursor.fetchone()
    finally:
        conn.close()

@app.put("/users/{user_id}/lb-account")
async def update_lb_account(user_id: int, account: LBAccountUpdate, api_key: str = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO user_listenbrainz_accounts (user_id, lb_username, lb_token)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE lb_username = VALUES(lb_username), lb_token = VALUES(lb_token)
            """, (user_id, account.lb_username, account.lb_token))
            conn.commit()
            return {"status": "updated"}
    finally:
        conn.close()

@app.put("/users/{user_id}/password")
async def update_password(user_id: int, pwd: PasswordUpdate, api_key: str = Depends(verify_api_key)):
    # Hash password with bcrypt (using 2b prefix, which is generally compatible)
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(pwd.password.encode('utf-8'), salt).decode('utf-8')
    
    # LMS often expects $2y$ prefix for bcrypt
    lms_hashed = hashed.replace('$2b$', '$2y$')
    
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    try:
        with conn.cursor() as cursor:
            # Check if user exists and get lms_user_id
            cursor.execute("SELECT lms_user_id FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Update MariaDB
            cursor.execute("UPDATE users SET password_hash = %s WHERE id = %s", (hashed, user_id))
            
            # Update LMS DB if exists
            if user['lms_user_id']:
                update_lms_password(user['lms_user_id'], lms_hashed)
                
            conn.commit()
            
            # Trigger sync on all LMS hosts
            run_lms_sync()
            
            return {"status": "password updated"}
    finally:
        conn.close()

def update_lms_user_info(lms_user_id, username, is_admin):
    db_path = os.getenv("LMS_DB_PATH", "/app/data/lms.db")
    if not os.path.exists(db_path):
        print(f"LMS DB not found at {db_path}, skipping LMS user info update")
        return
    
    # Check if directory is writable
    db_dir = os.path.dirname(db_path)
    if not os.access(db_dir, os.W_OK):
        print(f"WARNING: LMS DB directory {db_dir} is not writable. SQLite updates might fail.")

    try:
        sqlite_conn = sqlite3.connect(db_path)
        sqlite_cursor = sqlite_conn.cursor()
        
        user_type = 1 if is_admin else 0
        
        # Update login_name and type in LMS user table
        sqlite_cursor.execute("UPDATE user SET login_name = ?, type = ? WHERE id = ?", (username, user_type, lms_user_id))
        sqlite_conn.commit()
        sqlite_conn.close()
        print(f"Updated LMS user info for user ID {lms_user_id}")
    except Exception as e:
        print(f"Failed to update LMS user info for ID {lms_user_id}: {e}")

def update_lms_password(lms_user_id, password_hash):
    db_path = os.getenv("LMS_DB_PATH", "/app/data/lms.db")
    if not os.path.exists(db_path):
        print(f"LMS DB not found at {db_path}, skipping LMS password update")
        return
    
    # Check if directory is writable (needed for SQLite journals)
    db_dir = os.path.dirname(db_path)
    if not os.access(db_dir, os.W_OK):
        print(f"WARNING: LMS DB directory {db_dir} is not writable. SQLite updates might fail.")

    try:
        sqlite_conn = sqlite3.connect(db_path)
        sqlite_cursor = sqlite_conn.cursor()
        # Update password_hash in LMS user table
        sqlite_cursor.execute("UPDATE user SET password_hash = ? WHERE id = ?", (password_hash, lms_user_id))
        sqlite_conn.commit()
        sqlite_conn.close()
        print(f"Updated LMS password for user ID {lms_user_id}")
    except Exception as e:
        print(f"Failed to update LMS password for ID {lms_user_id}: {e}")

def delete_lms_user(lms_user_id):
    db_path = os.getenv("LMS_DB_PATH", "/app/data/lms.db")
    if not os.path.exists(db_path):
        print(f"LMS DB not found at {db_path}, skipping LMS user deletion")
        return
    
    # Check if directory is writable
    db_dir = os.path.dirname(db_path)
    if not os.access(db_dir, os.W_OK):
        print(f"WARNING: LMS DB directory {db_dir} is not writable. SQLite deletion might fail.")

    try:
        sqlite_conn = sqlite3.connect(db_path)
        sqlite_cursor = sqlite_conn.cursor()
        # Delete user from LMS user table
        sqlite_cursor.execute("DELETE FROM user WHERE id = ?", (lms_user_id,))
        sqlite_conn.commit()
        sqlite_conn.close()
        print(f"Deleted LMS user with ID {lms_user_id}")
    except Exception as e:
        print(f"Failed to delete LMS user with ID {lms_user_id}: {e}")

def create_lms_user(username, password_hash, is_admin=False):
    db_path = os.getenv("LMS_DB_PATH", "/app/data/lms.db")
    if not os.path.exists(db_path):
        print(f"LMS DB not found at {db_path}, skipping LMS user creation")
        return None
    
    # Check if directory is writable
    db_dir = os.path.dirname(db_path)
    if not os.access(db_dir, os.W_OK):
        print(f"WARNING: LMS DB directory {db_dir} is not writable. SQLite creation might fail.")

    try:
        sqlite_conn = sqlite3.connect(db_path)
        sqlite_cursor = sqlite_conn.cursor()
        
        # Generate a dummy salt since it's NOT NULL (32 chars)
        dummy_salt = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))

        user_type = 1 if is_admin else 0

        # Insert user into LMS user table with all required fields found in schema
        # We use values inspired by existing users for other mandatory fields
        sqlite_cursor.execute(
            """INSERT INTO user (
                version, type, login_name, password_salt, password_hash, 
                subsonic_enable_transcoding_by_default, subsonic_default_transcode_format, 
                subsonic_default_transcode_bitrate, subsonic_artist_list_mode, 
                ui_theme, feedback_backend, scrobbling_backend, listenbrainz_token
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (0, user_type, username, dummy_salt, password_hash, 
             0, 2, 128000, 0, 1, 0, 0, "")
        )
        lms_id = sqlite_cursor.lastrowid
        sqlite_conn.commit()
        sqlite_conn.close()
        print(f"Created LMS user {username} with ID {lms_id}")
        return lms_id
    except Exception as e:
        print(f"Failed to create LMS user {username}: {e}")
        return None

@app.post("/sync/lms")
async def sync_lms_users(background_tasks: BackgroundTasks, api_key: str = Depends(verify_api_key)):
    background_tasks.add_task(run_lms_sync)
    return {"message": "LMS sync started in background"}

def run_lms_sync():
    lms_hosts_raw = os.getenv("LMS_HOSTS", "http://192.168.1.27")
    lms_hosts = [h.strip() for h in lms_hosts_raw.split(",")]
    print(f"Starting LMS user sync from {lms_hosts}")

    for host in lms_hosts:
        try:
            # Ensure host has protocol
            if not host.startswith("http"):
                host = f"http://{host}"
            host = host.rstrip("/")

            # 1. Try to trigger Lightweight Music Server sync (Subsonic API)
            try:
                # Use dedicated LMS API key if available, fallback to internal API_KEY
                lms_api_key = LMS_SUBSONIC_API_KEY
                sync_url = f"{host}/rest/syncUsers.view?v=1.16.1&c=muma-user-service&f=json&apiKey={lms_api_key}"
                headers = {"X-API-Key": lms_api_key}
                sync_resp = requests.get(sync_url, headers=headers, timeout=5.0)
                if sync_resp.status_code == 200:
                    try:
                        data = sync_resp.json()
                        if data.get("subsonic-response", {}).get("status") == "ok":
                            print(f"Successfully triggered user sync on LMS host: {host}")
                        else:
                            error = data.get("subsonic-response", {}).get("error", {})
                            print(f"LMS host {host} returned error: {error.get('message', 'Unknown error')} (code {error.get('code')})")
                    except Exception as e:
                        print(f"Successfully triggered user sync on LMS host: {host} (non-json response). Body start: {sync_resp.text[:100]}")
                else:
                    print(f"LMS host {host} did not respond to Subsonic sync (status {sync_resp.status_code})")
            except Exception as e:
                print(f"LMS host {host} not a Lightweight Music Server or unreachable: {e}")

            # 2. Try Logitech Media Server JSON-RPC call for players
            payload = {
                "method": "slim.request",
                "params": ["", ["serverstatus", "0", "100"]]
            }
            try:
                response = requests.post(f"{host}/jsonrpc.js", json=payload, timeout=2.0)
                if response.status_code == 200:
                    try:
                        data = response.json()
                        players = data.get("result", {}).get("players_loop", [])
                        conn = get_db_connection()
                        if conn:
                            try:
                                with conn.cursor() as cursor:
                                    for player in players:
                                        name = player.get("name")
                                        pid = player.get("playerid")
                                        if name:
                                            # Use player name as username/display_name
                                            cursor.execute("""
                                                INSERT IGNORE INTO users (username, display_name, lms_user_id)
                                                VALUES (%s, %s, %s)
                                            """, (name.lower().replace(" ", "_"), name, pid))
                                    conn.commit()
                            finally:
                                conn.close()
                    except (ValueError, requests.exceptions.JSONDecodeError):
                        # Not a Logitech Media Server response, ignore
                        pass
            except Exception:
                # Host doesn't support JSON-RPC, ignore
                pass

        except Exception as e:
            print(f"LMS sync general failure for {host}: {e}")

@app.post("/sync/lms-db")
async def sync_lms_db(background_tasks: BackgroundTasks, api_key: str = Depends(verify_api_key)):
    background_tasks.add_task(run_lms_db_sync)
    return {"message": "LMS DB sync started in background"}

def run_lms_db_sync():
    db_path = os.getenv("LMS_DB_PATH", "/app/data/lms.db")
    if not os.path.exists(db_path):
        print(f"LMS DB not found at {db_path}")
        return
    
    print(f"Starting LMS DB sync from {db_path}")
    try:
        sqlite_conn = sqlite3.connect(db_path)
        sqlite_cursor = sqlite_conn.cursor()
        
        # Get users from LMS
        sqlite_cursor.execute("SELECT id, login_name, listenbrainz_token FROM user")
        lms_users = sqlite_cursor.fetchall()
        
        conn = get_db_connection()
        if not conn: return
        
        try:
            with conn.cursor() as cursor:
                for lms_id, username, lb_token in lms_users:
                    # Insert user
                    cursor.execute("""
                        INSERT INTO users (username, display_name, lms_user_id)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE lms_user_id = VALUES(lms_user_id)
                    """, (username, username, lms_id))
                    
                    # Get user_id
                    cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
                    user_row = cursor.fetchone()
                    
                    if user_row and lb_token:
                        user_id = user_row['id']
                        cursor.execute("""
                            INSERT INTO user_listenbrainz_accounts (user_id, lb_username, lb_token)
                            VALUES (%s, %s, %s)
                            ON DUPLICATE KEY UPDATE lb_token = VALUES(lb_token)
                        """, (user_id, username, lb_token))
                conn.commit()
                
                # Get smart playlists from LMS
                try:
                    # Check if smart_params column exists
                    sqlite_cursor.execute("PRAGMA table_info(tracklist)")
                    columns = [col[1] for col in sqlite_cursor.fetchall()]
                    
                    if "smart_params" in columns:
                        sqlite_cursor.execute("SELECT id, user_id, name, smart_params FROM tracklist WHERE type = 2")
                        lms_playlists = sqlite_cursor.fetchall()
                        for lms_id, lms_user_ptr_id, name, smart_params in lms_playlists:
                            # Find corresponding MuMa user
                            cursor.execute("SELECT id FROM users WHERE lms_user_id = %s", (str(lms_user_ptr_id),))
                            user_row = cursor.fetchone()
                            if user_row:
                                muma_user_id = user_row['id']
                                cursor.execute("""
                                    INSERT INTO dynamic_playlists (user_id, remote_id, source, name, params)
                                    VALUES (%s, %s, %s, %s, %s)
                                    ON DUPLICATE KEY UPDATE name = VALUES(name), params = VALUES(params)
                                """, (muma_user_id, lms_id, 'lms-stable', name, smart_params))
                    else:
                        print("LMS DB tracklist table missing smart_params column, skipping smart playlist sync.")
                    conn.commit()
                except Exception as e:
                    print(f"Failed to sync LMS playlists: {e}")
                    
            print("LMS DB sync completed")
            
            # Now sync artist images back to LMS
            sync_artist_images_to_lms(conn, sqlite_conn)
            
        finally:
            conn.close()
            sqlite_conn.close()
    except Exception as e:
        print(f"LMS DB sync failed: {e}")

def sync_artist_images_to_lms(muma_conn, lms_conn):
    """
    Syncs primary artist images from MuMa MariaDB to LMS SQLite DB.
    """
    print("Syncing artist images to LMS...")
    try:
        muma_cursor = muma_conn.cursor()
        lms_cursor = lms_conn.cursor()
        
        # 1. Get all primary artist images from MuMa
        muma_cursor.execute("""
            SELECT a.name as artist_name, i.cached_path, i.width, i.height, i.mime_type, i.file_size
            FROM library_artists a
            JOIN library_artist_images i ON a.primary_image_id = i.id
            WHERE i.cached_path IS NOT NULL
        """)
        images = muma_cursor.fetchall()
        
        for img in images:
            artist_name = img['artist_name']
            abs_path = img['cached_path']
            
            # 2. Find artist in LMS
            lms_cursor.execute("SELECT id FROM artist WHERE name = ?", (artist_name,))
            artist_row = lms_cursor.fetchone()
            if not artist_row:
                continue
            
            artist_id = artist_row[0]
            
            # 3. Ensure Image exists in LMS
            lms_cursor.execute("SELECT id FROM image WHERE absolute_file_path = ?", (abs_path,))
            image_row = lms_cursor.fetchone()
            
            image_id = None
            if image_row:
                image_id = image_row[0]
            else:
                stem = os.path.splitext(os.path.basename(abs_path))[0]
                lms_cursor.execute("""
                    INSERT INTO image (absolute_file_path, stem, file_size, width, height, mime_type)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (abs_path, stem, img['file_size'], img['width'], img['height'], img['mime_type']))
                image_id = lms_cursor.lastrowid
            
            # 4. Ensure Artwork exists in LMS
            lms_cursor.execute("SELECT id FROM artwork WHERE image_id = ?", (image_id,))
            artwork_row = lms_cursor.fetchone()
            
            artwork_id = None
            if artwork_row:
                artwork_id = artwork_row[0]
            else:
                lms_cursor.execute("INSERT INTO artwork (image_id) VALUES (?)", (image_id,))
                artwork_id = lms_cursor.lastrowid
            
            # 5. Link Artwork to Artist in LMS
            lms_cursor.execute("UPDATE artist SET preferred_artwork_id = ? WHERE id = ?", (artwork_id, artist_id))
            
        lms_conn.commit()
        print(f"Synced {len(images)} artist images to LMS")
    except Exception as e:
        print(f"Failed to sync artist images to LMS: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
