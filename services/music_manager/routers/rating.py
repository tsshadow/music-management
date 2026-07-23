import os
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel
from services.music_manager.database import get_db_connection
router = APIRouter(tags=['rating'])
API_KEY = os.getenv('API_KEY') or os.getenv('MUMA_API_KEY') or '00000000-0000-4000-8000-000000000000'

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

class Rating(BaseModel):
    entity_type: str = 'track'
    entity_id: str
    username: str
    rating: int

class MuMaServerEvent(BaseModel):
    event: str
    object_type: str
    object_id: str
    username: str
    rating: int
    path: Optional[str] = None

def init_db(cursor):
    cursor.execute('\n        CREATE TABLE IF NOT EXISTS rating_tracks (\n            id INT AUTO_INCREMENT PRIMARY KEY,\n            entity_type VARCHAR(50) NOT NULL,\n            entity_id VARCHAR(255) NOT NULL,\n            username VARCHAR(255) NOT NULL,\n            rating INT NOT NULL,\n            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,\n            UNIQUE KEY (entity_type, entity_id, username)\n        )\n    ')

@router.post('/server-event')
@router.post('/lms-event')
def handle_server_event(event: MuMaServerEvent, _auth: dict=Depends(verify_api_key)):
    if event.event != 'rating_changed':
        return {'status': 'ignored', 'reason': 'unsupported event type'}
    entity_id = event.object_id
    if event.object_type == 'track' and event.path:
        clean_path = event.path
        if clean_path.startswith('/mnt/music/'):
            clean_path = clean_path[len('/mnt/music/'):]
        possible_paths = [event.path, clean_path, f'/mnt/music/{clean_path}']
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cursor:
                    sql = '\n                        SELECT t.track_uid\n                        FROM library_media_files f\n                        JOIN library_tracks t ON f.track_id = t.id\n                        WHERE f.file_path IN (%s, %s, %s)\n                    '
                    cursor.execute(sql, tuple(possible_paths))
                    row = cursor.fetchone()
                    if row:
                        entity_id = row['track_uid']
            finally:
                conn.close()
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute('\n                INSERT INTO rating_tracks (entity_type, entity_id, username, rating)\n                VALUES (%s, %s, %s, %s)\n                ON DUPLICATE KEY UPDATE rating = VALUES(rating)\n            ', (event.object_type, entity_id, event.username, event.rating))
            conn.commit()
            return {'status': 'success', 'entity_id': entity_id}
    finally:
        conn.close()

@router.get('/ratings/{username}')
def get_user_ratings(username: str, _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            # Join with library_media_files to get paths for tracks
            sql = """
                SELECT r.entity_type, r.entity_id, r.rating, f.file_path
                FROM rating_tracks r
                LEFT JOIN library_tracks t ON r.entity_id = t.track_uid AND r.entity_type = 'track'
                LEFT JOIN library_media_files f ON t.id = f.track_id
                WHERE r.username = %s
            """
            cursor.execute(sql, (username,))
            return cursor.fetchall()
    finally:
        conn.close()