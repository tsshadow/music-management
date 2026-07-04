from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
import os
import pymysql
import requests
from typing import List, Optional
from dotenv import load_dotenv
from services.common.api.version_helper import get_version, get_release_notes, get_changelog

load_dotenv()

app = FastAPI(title="Muma User Service")

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
                        lms_user_id VARCHAR(255),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
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

@app.get("/version")
async def version():
    return {"version": get_version()}

@app.get("/release-notes")
async def release_notes():
    return {"notes": get_release_notes("services/user-service/RELEASE_NOTES.md")}

@app.get("/users")
async def get_users():
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
async def create_user(user: UserCreate):
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
async def get_lb_account(user_id: int):
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
async def update_lb_account(user_id: int, account: LBAccountUpdate):
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

@app.post("/sync/lms")
async def sync_lms_users(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_lms_sync)
    return {"message": "LMS sync started in background"}

def run_lms_sync():
    lms_host = os.getenv("LMS_HOST", "http://192.168.1.4:9000")
    print(f"Starting LMS user sync from {lms_host}")
    
    try:
        # LMS JSON-RPC call for players (can give us some hints about users/players)
        # However, for actual users we might need a different approach.
        # Let's try to get players as a proxy for 'users' if no better option exists.
        payload = {
            "method": "slim.request",
            "params": ["", ["serverstatus", "0", "100"]]
        }
        response = requests.post(f"{lms_host}/jsonrpc.js", json=payload, timeout=5.0)
        if response.status_code == 200:
            players = response.json().get("result", {}).get("players_loop", [])
            conn = get_db_connection()
            if not conn: return
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
    except Exception as e:
        print(f"LMS sync failed: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
