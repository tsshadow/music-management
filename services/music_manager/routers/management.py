from fastapi import APIRouter, HTTPException, Header, Depends, Body
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import os
import docker
import requests
import markdown
from datetime import datetime
from services.music_manager.database import get_db_connection
from services.common.api.version_helper import get_version, get_release_notes

router = APIRouter(prefix="/api", tags=["management"])

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
def login_proxy(req: Any = Body(...)):
    from services.music_manager.routers.users import login
    return login(req)

@router.get("/auth/verify")
def verify_proxy(x_api_key: str = Header(None)):
    from services.music_manager.routers.users import verify_token
    return verify_token(x_api_key)

@router.get("/users")
def get_users_proxy(api_key: str = Depends(verify_api_key)):
    from services.music_manager.routers.users import get_users
    return get_users(api_key)

@router.get("/users/{user_id}/dynamic-playlists")
def get_playlists_proxy(user_id: int, api_key: str = Depends(verify_api_key)):
    from services.music_manager.routers.users import get_dynamic_playlists
    return get_dynamic_playlists(user_id, api_key)

@router.get("/config")
def get_config(auth: dict = Depends(verify_api_key)):
    return {
        "DB_HOST": os.getenv("DB_HOST"),
        "DB_NAME": os.getenv("DB_DB"),
        "VERSION": get_version(),
        "PHPMYADMIN_URL": os.getenv("PHPMYADMIN_URL", "http://muma.teunschriks.nl:8002")
    }

@router.get("/stats")
def get_stats_proxy(auth: dict = Depends(verify_api_key)):
    # Internal call to stats router logic
    from services.music_manager.routers.stats import get_stats
    return get_stats(API_KEY)

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

@router.get("/system/activity")
def get_activity(limit: int = 20, auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn: raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT t.title, a.name as artist, CAST(t.created_at AS CHAR) as timestamp
                FROM library_tracks t
                JOIN library_artists a ON t.primary_artist_id = a.id
                ORDER BY t.created_at DESC
                LIMIT %s
            """, (limit,))
            return {"recent_added": cursor.fetchall(), "recent_tagged": []}
    finally:
        conn.close()
