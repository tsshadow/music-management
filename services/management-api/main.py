from fastapi import FastAPI, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import markdown
import os
import pymysql
from dotenv import load_dotenv
from typing import List, Optional, Dict
from pydantic import BaseModel
import requests
from services.common.api.version_helper import get_version, get_release_notes, get_changelog

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

class ArtistGenreRule(BaseModel):
    artist_name: str
    genre_id: int

class LabelGenreRule(BaseModel):
    label_name: str
    genre_id: int

@app.get("/api/config")
def get_config():
    return {
        "version": get_version(),
        "phpmyadmin_url": os.getenv("PHPMYADMIN_URL", "http://music-management-db.teunschriks.nl")
    }

@app.get("/api/notes")
def get_notes():
    return {
        "release_notes": get_release_notes("management-api"),
        "changelog": get_changelog()
    }

@app.get("/api/versions")
def get_all_versions():
    """Aggregate versions from all running services."""
    services = {
        "scanner": "http://muma-scanner:8001/version",
        "tagger": "http://muma-tagger-worker:8001/version",
        "importer": "http://muma-importer-worker:8001/version",
        "downloader": "http://muma-youtube-worker:8001/version",
        "ml-analyzer": "http://muma-ml-analyzer:8001/version"
    }
    
    versions = {
        "control-center": get_version()
    }
    
    for name, url in services.items():
        try:
            response = requests.get(url, timeout=1.0)
            if response.status_code == 200:
                versions[name] = response.json().get("version", "unknown")
            else:
                versions[name] = f"error ({response.status_code})"
        except Exception:
            versions[name] = "offline"
            
    # Add LMS and Ultrasonic references as requested
    versions["lms"] = get_lms_version()
    versions["ultrasonic"] = get_latest_ultrasonic_version()
    
    return versions

def get_lms_version():
    """Try to get LMS version if possible, otherwise return a reference."""
    lms_host = os.getenv("LMS_HOST", "http://192.168.1.4:9000")
    try:
        # LMS JSON-RPC call for version
        payload = {
            "method": "slim.request",
            "params": ["", ["version", "?"]]
        }
        response = requests.post(f"{lms_host}/jsonrpc.js", json=payload, timeout=1.0)
        if response.status_code == 200:
            return response.json().get("result", {}).get("_version", "unknown")
    except Exception:
        pass
    return "Reference: http://192.168.1.4:9000"

def get_latest_ultrasonic_version():
    """Get latest version from apk-hoster or github."""
    try:
        # Example: checking ultrasonic repo or a specific host
        # For now, return a placeholder or try to fetch from GitHub API
        response = requests.get("https://api.github.com/repos/ultrasonic/ultrasonic/releases/latest", timeout=1.0)
        if response.status_code == 200:
            return response.json().get("tag_name", "unknown")
    except Exception:
        pass
    return "See https://github.com/ultrasonic/ultrasonic/releases"

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

@app.get("/api/artists")
def get_artists(q: Optional[str] = None, limit: int = 100):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor() as cursor:
            if q:
                cursor.execute("SELECT id, name FROM library_artists WHERE name LIKE %s ORDER BY name LIMIT %s", (f"%{q}%", limit))
            else:
                cursor.execute("SELECT id, name FROM library_artists ORDER BY name LIMIT %s", (limit,))
            return cursor.fetchall()
    finally:
        conn.close()

@app.get("/api/labels")
def get_labels(q: Optional[str] = None, limit: int = 100):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor() as cursor:
            if q:
                cursor.execute("SELECT id, name FROM library_labels WHERE name LIKE %s ORDER BY name LIMIT %s", (f"%{q}%", limit))
            else:
                cursor.execute("SELECT id, name FROM library_labels ORDER BY name LIMIT %s", (limit,))
            return cursor.fetchall()
    finally:
        conn.close()

@app.get("/api/rules/artist-genres")
def get_artist_genre_rules():
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT r.id, r.artist_name, r.genre_id, g.name as genre_name 
                FROM rules_artist_genres r
                JOIN rules_genres g ON r.genre_id = g.id
                ORDER BY r.artist_name
            """)
            return cursor.fetchall()
    finally:
        conn.close()

@app.post("/api/rules/artist-genres")
def add_artist_genre_rule(rule: ArtistGenreRule):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT IGNORE INTO rules_artist_genres (artist_name, genre_id) VALUES (%s, %s)",
                (rule.artist_name, rule.genre_id)
            )
            conn.commit()
            return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.delete("/api/rules/artist-genres/{rule_id}")
def delete_artist_genre_rule(rule_id: int):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM rules_artist_genres WHERE id = %s", (rule_id,))
            conn.commit()
            return {"status": "success"}
    finally:
        conn.close()

@app.get("/api/rules/label-genres")
def get_label_genre_rules():
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT r.id, r.label_name, r.genre_id, g.name as genre_name 
                FROM rules_label_genres r
                JOIN rules_genres g ON r.genre_id = g.id
                ORDER BY r.label_name
            """)
            return cursor.fetchall()
    finally:
        conn.close()

@app.post("/api/rules/label-genres")
def add_label_genre_rule(rule: LabelGenreRule):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT IGNORE INTO rules_label_genres (label_name, genre_id) VALUES (%s, %s)",
                (rule.label_name, rule.genre_id)
            )
            conn.commit()
            return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.delete("/api/rules/label-genres/{rule_id}")
def delete_label_genre_rule(rule_id: int):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM rules_label_genres WHERE id = %s", (rule_id,))
            conn.commit()
            return {"status": "success"}
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
