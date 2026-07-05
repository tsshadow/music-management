from fastapi import FastAPI, HTTPException, Form, Header, Depends
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
import docker
from datetime import datetime
from services.common.api.version_helper import get_version, get_release_notes, get_changelog

load_dotenv()

SERVICES = {
    "scanner": "http://muma-scanner:8001",
    "tagger": "http://muma-tagger-worker:8001",
    "importer": "http://muma-importer-worker:8001",
    "youtube": "http://muma-youtube-worker:8001",
    "soundcloud": "http://muma-soundcloud-worker:8001",
    "telegram": "http://muma-telegram-worker:8001",
    "ml-analyzer": "http://muma-ml-analyzer:8001",
    "rating-system": "http://muma-rating-system:8000",
    "scrobble-service": "http://muma-scrobble-service:8000",
    "user-service": "http://muma-user-service:8001",
    "stats-service": "http://muma-stats-service:8000"
}

MUMA_API_KEY = os.getenv("MUMA_API_KEY") or "453ecd33-3cb2-4ca4-a531-1677330bbaee"
# LMS_API_KEY is an alias for MUMA_API_KEY when running in the same environment
LMS_API_KEY = os.getenv("LMS_API_KEY") or MUMA_API_KEY
API_KEY = os.getenv("API_KEY") or LMS_API_KEY
RATING_API_KEY = os.getenv("RATING_API_KEY") or LMS_API_KEY
SCROBBLE_API_KEY = os.getenv("SCROBBLE_API_KEY") or LMS_API_KEY
USER_API_KEY = os.getenv("USER_API_KEY") or LMS_API_KEY
STATS_API_KEY = os.getenv("STATS_API_KEY") or LMS_API_KEY

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://muma-user-service:8001")

class LoginRequest(BaseModel):
    username: str
    password: str

async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    if not x_api_key:
        if API_KEY:
            raise HTTPException(status_code=401, detail="Missing API key")
        return

    # 1. Check master key
    if API_KEY and x_api_key == API_KEY:
        return

    # 2. Check via auth service if available
    if AUTH_SERVICE_URL:
        try:
            resp = requests.get(f"{AUTH_SERVICE_URL}/auth/verify", headers={"X-API-Key": x_api_key}, timeout=2.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("type") == "system":
                    return
                if data.get("user") and data["user"].get("is_admin"):
                    return
                raise HTTPException(status_code=403, detail="Admin access required")
        except HTTPException:
            raise
        except Exception as e:
            print(f"Auth service error: {e}")
            pass

    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

def get_proxy_headers(service_name=None):
    headers = {}
    key = API_KEY
    if service_name == "rating-system":
        key = RATING_API_KEY
    elif service_name == "scrobble-service":
        key = SCROBBLE_API_KEY
    elif service_name == "user-service":
        key = USER_API_KEY
    elif service_name == "stats-service":
        key = STATS_API_KEY
    
    if key:
        headers["X-API-Key"] = key
    return headers

app = FastAPI(title="Music Management Control Center")

try:
    docker_client = docker.from_env()
except Exception as e:
    print(f"Docker client initialization error: {e}")
    docker_client = None

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

class YouTubeAccount(BaseModel):
    name: str

class ArtistGenreRule(BaseModel):
    artist_name: str
    genre_id: int

class LabelGenreRule(BaseModel):
    label_name: str
    genre_id: int

class ListenBrainzImport(BaseModel):
    username: str
    lb_username: Optional[str] = None

class UserCreate(BaseModel):
    username: str
    display_name: Optional[str] = None
    lms_user_id: Optional[str] = None
    password: Optional[str] = None

class LBAccountUpdate(BaseModel):
    lb_username: str
    lb_token: str

class PasswordUpdate(BaseModel):
    password: str

@app.post("/api/auth/login")
async def proxy_login(req: LoginRequest):
    if not AUTH_SERVICE_URL:
         raise HTTPException(status_code=503, detail="Auth service not configured")
    
    try:
        resp = requests.post(
            f"{AUTH_SERVICE_URL}/auth/login", 
            json={"username": req.username, "password": req.password},
            timeout=5.0
        )
        if resp.status_code != 200:
            try:
                detail = resp.json().get("detail", "Login failed")
            except:
                detail = "Login failed"
            raise HTTPException(status_code=resp.status_code, detail=detail)
        return resp.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Auth service communication error: {str(e)}")

@app.get("/api/config")
def get_config(_: None = Depends(verify_api_key)):
    return {
        "version": get_version(),
        "phpmyadmin_url": os.getenv("PHPMYADMIN_URL", "http://music-management-db.teunschriks.nl")
    }

@app.get("/api/notes")
def get_notes(_: None = Depends(verify_api_key)):
    return {
        "release_notes": get_release_notes("management-api"),
        "changelog": get_changelog()
    }

@app.get("/api/stats")
def get_stats_endpoint(_: None = Depends(verify_api_key)):
    try:
        url = f"{SERVICES['stats-service']}/stats"
        resp = requests.get(url, headers=get_proxy_headers("stats-service"), timeout=5.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Stats service error: {e}")
        # Fallback to empty stats if service is down
        return {
            "total_tracks": 0,
            "total_artists": 0,
            "total_albums": 0,
            "top_artists": [],
            "top_genres": [],
            "recently_added": [],
            "match_rate": 0
        }

@app.get("/api/versions")
def get_all_versions(_: None = Depends(verify_api_key)):
    """Aggregate versions from all running services."""
    versions = {
        "control-center": get_version()
    }
    
    for name, base_url in SERVICES.items():
        try:
            response = requests.get(f"{base_url}/version", headers=get_proxy_headers(name), timeout=1.0)
            if response.status_code == 200:
                versions[name] = response.json().get("version", "unknown")
            else:
                versions[name] = f"error ({response.status_code})"
        except Exception:
            versions[name] = "offline"
            
    # Add LMS and Ultrasonic references
    versions["lms"] = get_lms_version()
    versions["ultrasonic"] = get_latest_ultrasonic_version()
    
    return versions

@app.get("/api/all-notes")
def get_all_release_notes(_: None = Depends(verify_api_key)):
    """Aggregate release notes from all services."""
    all_notes = {
        "control-center": {
            "release_notes": get_release_notes("management-api"),
            "changelog": get_changelog()
        }
    }
    
    for name, base_url in SERVICES.items():
        try:
            response = requests.get(f"{base_url}/release-notes", headers=get_proxy_headers(name), timeout=2.0)
            if response.status_code == 200:
                all_notes[name] = response.json()
            else:
                all_notes[name] = {"release_notes": f"<p>Error fetching: {response.status_code}</p>", "changelog": ""}
        except Exception:
            all_notes[name] = {"release_notes": "<p>Service offline.</p>", "changelog": ""}
            
    return all_notes

def get_lms_version():
    """Try to get LMS version if possible, otherwise return a reference."""
    lms_host = os.getenv("LMS_HOST", "http://lms.teunschriks.nl")
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
    return "Reference: http://lms.teunschriks.nl"

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
def get_rules(_: None = Depends(verify_api_key)):
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
def get_soundcloud_accounts(_: None = Depends(verify_api_key)):
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

@app.get("/api/youtube")
def get_youtube_accounts(_: None = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT name FROM downloads_youtube_accounts ORDER BY name")
            accounts = cursor.fetchall()
            return accounts
    finally:
        conn.close()

@app.get("/api/artists")
def get_artists(q: Optional[str] = None, limit: int = 100, _: None = Depends(verify_api_key)):
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
def get_labels(q: Optional[str] = None, limit: int = 100, _: None = Depends(verify_api_key)):
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
def get_artist_genre_rules(_: None = Depends(verify_api_key)):
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
def add_artist_genre_rule(rule: ArtistGenreRule, _: None = Depends(verify_api_key)):
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
def delete_artist_genre_rule(rule_id: int, _: None = Depends(verify_api_key)):
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
def get_label_genre_rules(_: None = Depends(verify_api_key)):
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
def add_label_genre_rule(rule: LabelGenreRule, _: None = Depends(verify_api_key)):
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
def delete_label_genre_rule(rule_id: int, _: None = Depends(verify_api_key)):
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

# Scrobble Service Proxy Endpoints
@app.post("/api/scrobble/import/listenbrainz")
def proxy_import_listenbrainz(data: ListenBrainzImport, _: None = Depends(verify_api_key)):
    base_url = SERVICES["scrobble-service"]
    params = {"username": data.username}
    if data.lb_username:
        params["lb_username"] = data.lb_username
        
    try:
        response = requests.post(
            f"{base_url}/api/import/listenbrainz", 
            params=params,
            headers=get_proxy_headers("scrobble-service"),
            timeout=5.0
        )
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to contact Scrobble Service: {str(e)}")

@app.get("/api/scrobble/import/latest")
def proxy_latest_imports(_: None = Depends(verify_api_key)):
    base_url = SERVICES["scrobble-service"]
    try:
        response = requests.get(f"{base_url}/api/import/latest", headers=get_proxy_headers("scrobble-service"), timeout=5.0)
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to contact Scrobble Service: {str(e)}")

# User Service Proxy Endpoints
@app.get("/api/users")
def proxy_get_users(_: None = Depends(verify_api_key)):
    base_url = SERVICES["user-service"]
    try:
        response = requests.get(f"{base_url}/users", headers=get_proxy_headers("user-service"), timeout=5.0)
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to contact User Service: {str(e)}")

@app.post("/api/users")
def proxy_create_user(user: UserCreate, _: None = Depends(verify_api_key)):
    base_url = SERVICES["user-service"]
    try:
        response = requests.post(f"{base_url}/users", json=user.dict(), headers=get_proxy_headers("user-service"), timeout=5.0)
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to contact User Service: {str(e)}")

@app.delete("/api/users/{user_id}")
def proxy_delete_user(user_id: int, _: None = Depends(verify_api_key)):
    base_url = SERVICES["user-service"]
    try:
        response = requests.delete(f"{base_url}/users/{user_id}", headers=get_proxy_headers("user-service"), timeout=5.0)
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to contact User Service: {str(e)}")

@app.get("/api/users/{user_id}/lb-account")
def proxy_get_lb_account(user_id: int, _: None = Depends(verify_api_key)):
    base_url = SERVICES["user-service"]
    try:
        response = requests.get(f"{base_url}/users/{user_id}/lb-account", headers=get_proxy_headers("user-service"), timeout=5.0)
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to contact User Service: {str(e)}")

@app.put("/api/users/{user_id}/lb-account")
def proxy_update_lb_account(user_id: int, account: LBAccountUpdate, _: None = Depends(verify_api_key)):
    base_url = SERVICES["user-service"]
    try:
        response = requests.put(f"{base_url}/users/{user_id}/lb-account", json=account.dict(), headers=get_proxy_headers("user-service"), timeout=5.0)
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to contact User Service: {str(e)}")

@app.put("/api/users/{user_id}/password")
def proxy_update_user_password(user_id: int, pwd: PasswordUpdate, _: None = Depends(verify_api_key)):
    base_url = SERVICES["user-service"]
    try:
        response = requests.put(f"{base_url}/users/{user_id}/password", json=pwd.dict(), headers=get_proxy_headers("user-service"), timeout=5.0)
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to contact User Service: {str(e)}")

@app.post("/api/users/sync/lms")
def proxy_sync_lms_users(_: None = Depends(verify_api_key)):
    base_url = SERVICES["user-service"]
    try:
        response = requests.post(f"{base_url}/sync/lms", headers=get_proxy_headers("user-service"), timeout=5.0)
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to contact User Service: {str(e)}")

@app.post("/api/users/sync/lms-db")
def proxy_sync_lms_db_users(_: None = Depends(verify_api_key)):
    base_url = SERVICES["user-service"]
    try:
        response = requests.post(f"{base_url}/sync/lms-db", headers=get_proxy_headers("user-service"), timeout=5.0)
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to contact User Service: {str(e)}")

@app.post("/api/soundcloud")
def add_soundcloud_account(account: SoundCloudAccount, _: None = Depends(verify_api_key)):
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

@app.delete("/api/soundcloud/{name}")
def delete_soundcloud_account(name: str, _: None = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM downloads_soundcloud_accounts WHERE name = %s", (name,))
            conn.commit()
            return {"status": "success"}
    finally:
        conn.close()

@app.post("/api/youtube")
def add_youtube_account(account: YouTubeAccount, _: None = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT IGNORE INTO downloads_youtube_accounts (name) VALUES (%s)",
                (account.name,)
            )
            conn.commit()
            return {"status": "success", "message": f"Account {account.name} added"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.delete("/api/youtube/{name}")
def delete_youtube_account(name: str, _: None = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM downloads_youtube_accounts WHERE name = %s", (name,))
            conn.commit()
            return {"status": "success"}
    finally:
        conn.close()

# System Monitoring Endpoints
@app.get("/api/system/containers")
def get_containers(_: None = Depends(verify_api_key)):
    if not docker_client:
        return []
    try:
        containers = []
        for container in docker_client.containers.list(all=True):
            # Filter only muma related containers if possible, or show all
            if any(name in container.name for name in ["muma", "music-management", "db", "phpmyadmin", "firefox", "lms"]):
                containers.append({
                    "id": container.id,
                    "name": container.name,
                    "status": container.status,
                    "image": container.image.tags[0] if container.image.tags else "unknown",
                    "state": container.attrs.get("State", {})
                })
        return sorted(containers, key=lambda x: x["name"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Docker error: {str(e)}")

@app.get("/api/system/logs/{container_name}")
def get_container_logs(container_name: str, tail: int = 100, _: None = Depends(verify_api_key)):
    if not docker_client:
        raise HTTPException(status_code=500, detail="Docker not available")
    try:
        container = docker_client.containers.get(container_name)
        logs = container.logs(tail=tail).decode("utf-8")
        return {"logs": logs}
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/system/activity")
def get_recent_activity(limit: int = 20, _: None = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with conn.cursor() as cursor:
            # Recent added tracks
            cursor.execute("""
                SELECT mf.file_path, t.created_at as timestamp, t.title, a.name as artist
                FROM library_media_files mf
                LEFT JOIN library_tracks t ON mf.track_id = t.id
                LEFT JOIN library_artists a ON t.primary_artist_id = a.id
                WHERE t.created_at IS NOT NULL
                ORDER BY t.created_at DESC
                LIMIT %s
            """, (limit,))
            added = cursor.fetchall()
            
            # Recent tagged tracks (last_seen > created_at + some buffer)
            cursor.execute("""
                SELECT mf.file_path, mf.last_seen as timestamp, t.title, a.name as artist
                FROM library_media_files mf
                LEFT JOIN library_tracks t ON mf.track_id = t.id
                LEFT JOIN library_artists a ON t.primary_artist_id = a.id
                WHERE mf.last_seen > DATE_ADD(t.created_at, INTERVAL 10 SECOND)
                ORDER BY mf.last_seen DESC
                LIMIT %s
            """, (limit,))
            tagged = cursor.fetchall()
            
            # Categorize by source based on path
            def get_source(path):
                if not path: return "Unknown"
                if "/Youtube/" in path: return "YouTube"
                if "/Soundcloud/" in path: return "SoundCloud"
                if "/Telegram/" in path: return "Telegram"
                if "/EPs/" in path: return "Importer"
                return "Unknown"
            
            for item in added:
                item["source"] = get_source(item["file_path"])
                if item["timestamp"]:
                    if isinstance(item["timestamp"], datetime):
                        item["timestamp"] = item["timestamp"].isoformat()
                    else:
                        item["timestamp"] = str(item["timestamp"])
            
            for item in tagged:
                item["source"] = get_source(item["file_path"])
                if item["timestamp"]:
                    if isinstance(item["timestamp"], datetime):
                        item["timestamp"] = item["timestamp"].isoformat()
                    else:
                        item["timestamp"] = str(item["timestamp"])
            
            return {
                "recent_added": added,
                "recent_tagged": tagged
            }
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
