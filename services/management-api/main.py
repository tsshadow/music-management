from fastapi import FastAPI, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import markdown
import os
import pymysql
from dotenv import load_dotenv
from typing import List, Optional
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="Music Management Control Center")

# Allow CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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

def get_file_content(filename):
    paths = [
        os.path.join(os.getcwd(), filename),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), filename),
        os.path.join("/app", filename)
    ]
    for path in paths:
        if os.path.exists(path):
            with open(path, "r") as f:
                return f.read()
    return f"File {filename} not found."

class SoundCloudAccount(BaseModel):
    name: str
    soundcloud_id: Optional[str] = None

@app.get("/api/config")
def get_config():
    return {
        "version": get_file_content("VERSION").strip(),
        "phpmyadmin_url": os.getenv("PHPMYADMIN_URL", "http://music-management-db.teunschriks.nl")
    }

@app.get("/api/notes")
def get_notes():
    release_notes_md = get_file_content("RELEASE_NOTES.md")
    changelog_md = get_file_content("CHANGELOG.md")
    
    return {
        "release_notes": markdown.markdown(release_notes_md, extensions=['extra', 'toc']),
        "changelog": markdown.markdown(changelog_md, extensions=['extra', 'toc'])
    }

@app.get("/api/rules")
def get_rules():
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name FROM rules_genres ORDER BY name")
            genres = cursor.fetchall()
            
            cursor.execute("SELECT name FROM rules_ignored_genres ORDER BY name")
            ignored = cursor.fetchall()
            
            return {
                "genres": genres,
                "ignored_genres": ignored
            }
    finally:
        conn.close()

@app.get("/api/soundcloud")
def get_soundcloud_accounts():
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT name, soundcloud_id FROM downloads_soundcloud_accounts ORDER BY name")
            accounts = cursor.fetchall()
            return accounts
    finally:
        conn.close()

@app.post("/api/soundcloud")
def add_soundcloud_account(account: SoundCloudAccount):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT IGNORE INTO downloads_soundcloud_accounts (name, soundcloud_id) VALUES (%s, %s)",
                (account.name, account.soundcloud_id)
            )
            conn.commit()
            return {"status": "success", "message": f"Account {account.name} added"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/health")
def health():
    return {"status": "healthy"}

# Serve Frontend
frontend_path = "/app/services/management-api/frontend/dist"
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
else:
    @app.get("/", response_class=HTMLResponse)
    def root_fallback():
        return """
        <html>
            <head><title>Music Management Control Center</title></head>
            <body style="font-family: sans-serif; padding: 50px; text-align: center;">
                <h1>Music Management Control Center</h1>
                <p>Frontend not built yet. API is active at /api/config, /api/notes, etc.</p>
                <p><a href="/api/config">Check API Configuration</a></p>
            </body>
        </html>
        """
