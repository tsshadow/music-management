from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from services.music_manager.database import get_db_connection
from services.music_manager.identity import canonical_username, same_username

# The same file goes by two names depending on who is talking about it, and the version
# sync joins on the path just as this handler does -- so the translation lives in one
# module rather than in each of them.
from services.music_manager.library_paths import (
    LMS_MUSIC_ROOT,
    MUMA_MUSIC_ROOT,
    candidate_paths,
)
from services.music_manager.rbac import is_admin_auth
from services.music_manager.routers.users import verify_api_key

router = APIRouter(tags=['rating'])

__all__ = ['LMS_MUSIC_ROOT', 'MUMA_MUSIC_ROOT', 'candidate_paths', 'router']


def require_system_key(x_api_key: str | None = Header(None)):
    """Only the system key: the rating webhook writes whatever username its body names.

    LMS is the one caller (MusicManagementBackend.cpp, configured with
    `music-management-api-key`, which is the system key -- see SECURITY.md). A user
    key here would let any account write ratings under any other account's name.
    """
    auth = verify_api_key(x_api_key)
    if auth.get('type') != 'system':
        raise HTTPException(status_code=403, detail='System API key required')
    return auth


class Rating(BaseModel):
    entity_type: str = 'track'
    entity_id: str
    username: str
    rating: int


class MuMaServerEvent(BaseModel):
    """A rating event pushed by the music-management-server (LMS fork).

    ``event`` is ``rating_changed`` (upsert ``rating``) or ``rating_removed`` (the user
    cleared the rating; ``rating`` is 0). A ``rating_changed`` with a rating of 0 or less
    is treated as a removal as well, because no star count below 1 exists.
    """

    event: str
    object_type: str
    object_id: str
    username: str
    rating: int
    path: str | None = None


def init_db(cursor):
    cursor.execute(
        '\n        CREATE TABLE IF NOT EXISTS rating_tracks (\n            id INT AUTO_INCREMENT PRIMARY KEY,\n            entity_type VARCHAR(50) NOT NULL,\n            entity_id VARCHAR(255) NOT NULL,\n            username VARCHAR(255) NOT NULL,\n            rating INT NOT NULL,\n            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,\n            UNIQUE KEY (entity_type, entity_id, username)\n        )\n    '
    )


@router.post('/lms-event')
def handle_server_event(event: MuMaServerEvent, _auth: dict = Depends(require_system_key)):
    """Mirror one LMS rating event into ``rating_tracks``: upsert a rating, or delete the
    row when the rating was cleared on the server. System key only, see require_system_key."""
    if event.event not in ('rating_changed', 'rating_removed'):
        return {'status': 'ignored', 'reason': 'unsupported event type'}
    removed = event.event == 'rating_removed' or event.rating <= 0
    entity_id = event.object_id
    if event.object_type == 'track' and event.path:
        possible_paths = candidate_paths(event.path)
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cursor:
                    placeholders = ', '.join(['%s'] * len(possible_paths))
                    sql = f'\n                        SELECT t.track_uid\n                        FROM library_media_files f\n                        JOIN library_tracks t ON f.track_id = t.id\n                        WHERE f.file_path IN ({placeholders})\n                    '
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
            # The account's own spelling, whatever LMS relays: its local user may carry a
            # case variant of the name (docs/bug-reports/074-login-case-forks-user-identity.md).
            username = canonical_username(cursor, event.username) or event.username
            if removed:
                cursor.execute(
                    'DELETE FROM rating_tracks WHERE entity_type = %s AND entity_id = %s AND username = %s',
                    (event.object_type, entity_id, username),
                )
                conn.commit()
                return {'status': 'removed', 'entity_id': entity_id}
            cursor.execute(
                '\n                INSERT INTO rating_tracks (entity_type, entity_id, username, rating)\n                VALUES (%s, %s, %s, %s)\n                ON DUPLICATE KEY UPDATE rating = VALUES(rating)\n            ',
                (event.object_type, entity_id, username, event.rating),
            )
            conn.commit()
            return {'status': 'success', 'entity_id': entity_id}
    finally:
        conn.close()


@router.get('/ratings/{username}')
def get_user_ratings(username: str, _auth: dict = Depends(verify_api_key)):
    """One account's ratings: the caller's own, or anyone's for an admin or the system key."""
    own = same_username((_auth.get('user') or {}).get('username'), username)
    if not own and not is_admin_auth(_auth):
        raise HTTPException(status_code=403, detail='Forbidden')
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
