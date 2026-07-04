from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Header
from pydantic import BaseModel
import os
import pymysql
import requests
import sqlite3
import bcrypt
from typing import List, Optional
from dotenv import load_dotenv
from services.common.api.version_helper import get_version, get_release_notes, get_changelog

load_dotenv()

app = FastAPI(title="Muma User Service")

API_KEY = os.getenv("API_KEY", "453ecd33-3cb2-4ca4-a531-1677330bbaee")

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
                        password_hash VARCHAR(255),
                        lms_user_id VARCHAR(255),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                # Add password_hash if it doesn't exist (for existing tables)
                cursor.execute("SHOW COLUMNS FROM users LIKE 'password_hash'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) AFTER display_name")
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
            conn.commit()
        finally:
            conn.close()

class UserCreate(BaseModel):
    username: str
    display_name: Optional[str] = None
    lms_user_id: Optional[str] = None

class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    lms_user_id: Optional[str] = None

class LBAccountUpdate(BaseModel):
    lb_username: str
    lb_token: str

class PasswordUpdate(BaseModel):
    password: str

@app.get("/version")
async def version(api_key: str = Depends(verify_api_key)):
    return {"version": get_version()}

@app.get("/release-notes")
async def release_notes(api_key: str = Depends(verify_api_key)):
    return {"notes": get_release_notes("services/user-service/RELEASE_NOTES.md")}

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
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (username, display_name, lms_user_id) VALUES (%s, %s, %s)",
                (user.username, user.display_name, user.lms_user_id)
            )
            conn.commit()
            return {"id": cursor.lastrowid, "username": user.username}
    except pymysql.err.IntegrityError:
        raise HTTPException(status_code=400, detail="Username already exists")
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
            return {"status": "password updated"}
    finally:
        conn.close()

def update_lms_password(lms_user_id, password_hash):
    db_path = os.getenv("LMS_DB_PATH", "/app/data/lms.db")
    if not os.path.exists(db_path):
        print(f"LMS DB not found at {db_path}, skipping LMS password update")
        return
    try:
        sqlite_conn = sqlite3.connect(db_path)
        sqlite_cursor = sqlite_conn.cursor()
        # Update password_hash in LMS user table
        sqlite_cursor.execute("UPDATE user SET password_hash = ? WHERE id = ?", (password_hash, lms_user_id))
        sqlite_conn.commit()
        sqlite_conn.close()
        print(f"Updated LMS password for user ID {lms_user_id}")
    except Exception as e:
        print(f"Failed to update LMS password: {e}")

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

            # 1. Try to trigger Lightweight Music Server sync (Subsonic API with X-API-Key)
            try:
                sync_url = f"{host}/rest/syncUsers?v=1.16.1&c=muma-user-service&f=json&apiKey={API_KEY}"
                headers = {"X-API-Key": API_KEY}
                sync_resp = requests.get(sync_url, headers=headers, timeout=2.0)
                if sync_resp.status_code == 200:
                    print(f"Successfully triggered user sync on LMS host: {host}")
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
            print("LMS DB sync completed")
        finally:
            conn.close()
            sqlite_conn.close()
    except Exception as e:
        print(f"LMS DB sync failed: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
