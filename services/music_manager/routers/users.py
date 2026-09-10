import contextlib
import json
import logging
import os
import secrets
import sqlite3
import time

import bcrypt
import requests
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from services.music_manager import rbac
from services.music_manager.api_key import is_system_api_key
from services.music_manager.database import get_db_connection
from services.music_manager.rate_limit import auth_attempt
from services.music_manager.rbac import has_permission, require_permission

router = APIRouter(tags=['users'])
# These four are the keys this service *presents* when it calls the muma server.
# What it *accepts* as the system key is api_key.is_system_api_key(), which reads
# API_KEY/MUMA_API_KEY and has no literal fallback -- see that module for why.
MUMA_API_KEY = os.getenv('MUMA_API_KEY')
MUMA_SERVER_API_KEY = os.getenv('MUMA_SERVER_API_KEY') or os.getenv('LMS_API_KEY') or MUMA_API_KEY
API_KEY = os.getenv('API_KEY') or MUMA_SERVER_API_KEY
MUMA_SERVER_SUBSONIC_API_KEY = os.getenv('MUMA_SERVER_SUBSONIC_API_KEY') or os.getenv('LMS_SUBSONIC_API_KEY') or API_KEY
MUMA_SERVER_HOSTS = os.getenv('MUMA_SERVER_HOSTS', 'music-management-server:5082')


async def verify_api_key(x_api_key: str = Header(None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail='Missing API Key')
    if is_system_api_key(x_api_key):
        return {'type': 'system'}
    res = verify_token(x_api_key)
    if res.get('status') == 'ok':
        return res
    raise HTTPException(status_code=401, detail='Invalid API Key')


class UserCreate(BaseModel):
    username: str
    display_name: str | None = None
    is_admin: bool | None = False
    server_user_id: str | None = None
    api_key: str | None = None
    password: str | None = None


class UserUpdate(BaseModel):
    username: str | None = None
    display_name: str | None = None
    is_admin: bool | None = None
    server_user_id: str | None = None
    api_key: str | None = None


class MergeUsersRequest(BaseModel):
    secondary_user_id: int


class RoleAssign(BaseModel):
    role: str


class EnabledUpdate(BaseModel):
    enabled: bool


class GoogleLoginRequest(BaseModel):
    id_token: str


class AccessRequestCreate(BaseModel):
    id_token: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LBAccountUpdate(BaseModel):
    lb_username: str
    lb_token: str


class DynamicPlaylistCreate(BaseModel):
    name: str
    params: str


class DynamicPlaylistUpdate(BaseModel):
    name: str | None = None
    params: str | None = None
    rating_range: list[int] | None = None
    genres: list[str] | None = None
    size: int | None = None
    sort_method: str | None = None
    song_type: str | None = None


class PasswordUpdate(BaseModel):
    password: str


class AppSettingsUpdate(BaseModel):
    settings: str


class LoginRequest(BaseModel):
    username: str
    password: str


def init_db(cursor):
    cursor.execute(
        '\n        CREATE TABLE IF NOT EXISTS users (\n            id INT AUTO_INCREMENT PRIMARY KEY,\n            username VARCHAR(255) UNIQUE NOT NULL,\n            display_name VARCHAR(255),\n            is_admin BOOLEAN DEFAULT FALSE,\n            password_hash VARCHAR(255),\n            api_key VARCHAR(255),\n            server_user_id VARCHAR(255),\n            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n        )\n    '
    )
    cursor.execute("SHOW COLUMNS FROM users LIKE 'server_user_id'")
    if not cursor.fetchone():
        cursor.execute("SHOW COLUMNS FROM users LIKE 'lms_user_id'")
        if cursor.fetchone():
            cursor.execute('ALTER TABLE users CHANGE lms_user_id server_user_id VARCHAR(255)')
        else:
            cursor.execute('ALTER TABLE users ADD COLUMN server_user_id VARCHAR(255) AFTER api_key')

    # Check for is_admin column
    cursor.execute("SHOW COLUMNS FROM users LIKE 'is_admin'")
    if not cursor.fetchone():
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE AFTER display_name')
        except Exception as e:
            if "Duplicate column name" not in str(e):
                raise e

    # Check for password_hash column
    cursor.execute("SHOW COLUMNS FROM users LIKE 'password_hash'")
    if not cursor.fetchone():
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) AFTER display_name')
        except Exception as e:
            if "Duplicate column name" not in str(e):
                raise e

    # Check for api_key column
    cursor.execute("SHOW COLUMNS FROM users LIKE 'api_key'")
    if not cursor.fetchone():
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN api_key VARCHAR(255) AFTER password_hash')
        except Exception as e:
            if "Duplicate column name" not in str(e):
                raise e
    cursor.execute(
        '\n        CREATE TABLE IF NOT EXISTS user_listenbrainz_accounts (\n            id INT AUTO_INCREMENT PRIMARY KEY,\n            user_id INT NOT NULL,\n            lb_username VARCHAR(255) NOT NULL,\n            lb_token VARCHAR(255) NOT NULL,\n            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n            UNIQUE KEY (user_id),\n            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE\n        )\n    '
    )
    cursor.execute(
        '\n        CREATE TABLE IF NOT EXISTS dynamic_playlists (\n            id INT AUTO_INCREMENT PRIMARY KEY,\n            user_id INT NOT NULL,\n            remote_id INT,\n            source VARCHAR(50),\n            name VARCHAR(255) NOT NULL,\n            params TEXT NOT NULL,\n            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,\n            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE\n        )\n    '
    )
    cursor.execute("SHOW COLUMNS FROM dynamic_playlists LIKE 'remote_id'")
    if not cursor.fetchone():
        cursor.execute('ALTER TABLE dynamic_playlists ADD COLUMN remote_id INT AFTER user_id')
    cursor.execute("SHOW COLUMNS FROM dynamic_playlists LIKE 'source'")
    if not cursor.fetchone():
        cursor.execute('ALTER TABLE dynamic_playlists ADD COLUMN source VARCHAR(50) AFTER remote_id')
    with contextlib.suppress(Exception):
        cursor.execute('ALTER TABLE dynamic_playlists ADD UNIQUE INDEX uq_source_remote_id (source, remote_id)')
    cursor.execute(
        '\n        CREATE TABLE IF NOT EXISTS user_app_settings (\n            id INT AUTO_INCREMENT PRIMARY KEY,\n            user_id INT NOT NULL,\n            app_id VARCHAR(50) NOT NULL,\n            settings_json LONGTEXT NOT NULL,\n            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,\n            UNIQUE KEY (user_id, app_id),\n            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE\n        )\n    '
    )

    # Roles/permissions, Google identities, access requests, refresh tokens, audit log.
    rbac.init_db(cursor)


def _role_name(cursor, role_id):
    if not role_id:
        return None
    cursor.execute('SELECT name FROM roles WHERE id = %s', (role_id,))
    row = cursor.fetchone()
    return row['name'] if row else None


def build_auth_user(cursor, user_row):
    """Build the permission-bearing user payload used by verify_token/login/etc.

    ``is_admin`` is kept only as a derived, read-only convenience field for
    existing UI code; it must never be written back or trusted for
    authorization decisions -- that always goes through role/permissions.
    """
    role_name = _role_name(cursor, user_row.get('role_id'))
    permissions = sorted(rbac.get_permissions_for_role(cursor, user_row.get('role_id')))
    return {
        'id': user_row['id'],
        'username': user_row['username'],
        'display_name': user_row.get('display_name'),
        'email': user_row.get('email'),
        'avatar_url': user_row.get('avatar_url'),
        'server_user_id': user_row.get('server_user_id'),
        'role_id': user_row.get('role_id'),
        'role_name': role_name,
        'is_admin': role_name == rbac.ADMIN_ROLE_NAME,
        'enabled': bool(user_row.get('enabled', True)),
        'permissions': permissions,
    }


@router.get('/auth/verify')
def verify_token(x_api_key: str = Header(None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail='Missing API Key')
    if is_system_api_key(x_api_key):
        return {'status': 'ok', 'type': 'system'}
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute('SELECT * FROM users WHERE api_key = %s', (x_api_key,))
                user = cursor.fetchone()
                if user:
                    if not user.get('enabled', True):
                        raise HTTPException(status_code=403, detail='Account disabled')
                    return {'status': 'ok', 'type': 'user', 'user': build_auth_user(cursor, user)}
        finally:
            conn.close()
    raise HTTPException(status_code=403, detail='Invalid API Key')


@router.post('/auth/login')
def login(req: LoginRequest, request: Request):
    """Log in with username/password, used both by the login form and, indirectly, by
    Subsonic/LMS clients (LMS forwards its own username/password login attempts here, see
    MusicManagementPasswordService.cpp).

    A Google-only (or Google-linked) account has no known plaintext password on this side --
    see AuthOverlay.svelte's handleGoogleResponse, which never learns one -- so ``req.password``
    is also accepted if it matches the account's current ``api_key``. This grants no additional
    privilege: knowing the api_key already grants full API access via the X-API-Key header, and
    it's how the frontend authenticates Subsonic/LMS calls (genres, streaming, ...) after a
    Google sign-in, so both login methods end up with a fully working session for the same user.

    Because LMS calls this on every Subsonic request, the rate limit is keyed on the
    account and counts only rejections -- see services/music_manager/rate_limit.py.
    """
    with auth_attempt(request, req.username):
        conn = get_db_connection()
        if not conn:
            raise HTTPException(status_code=500, detail='Database connection failed')
        try:
            with conn.cursor() as cursor:
                cursor.execute('SELECT * FROM users WHERE username = %s', (req.username,))
                user = cursor.fetchone()
                if not user:
                    raise HTTPException(status_code=401, detail='Invalid username or password')
                if not user.get('enabled', True):
                    raise HTTPException(status_code=403, detail='Account disabled')

                password_valid = False
                if (
                    user.get('password_hash')
                    and bcrypt.checkpw(req.password.encode('utf-8'), user['password_hash'].encode('utf-8'))
                    or user.get('api_key')
                    and secrets.compare_digest(req.password, user['api_key'])
                ):
                    password_valid = True

                if not password_valid:
                    raise HTTPException(status_code=401, detail='Invalid username or password')

                api_key = user['api_key']
                if not api_key:
                    api_key = secrets.token_hex(32)
                    cursor.execute('UPDATE users SET api_key = %s WHERE id = %s', (api_key, user['id']))
                cursor.execute('UPDATE users SET last_login_at = NOW() WHERE id = %s', (user['id'],))
                refresh_token = secrets.token_hex(32)
                cursor.execute(
                    'INSERT INTO user_refresh_tokens (user_id, token) VALUES (%s, %s)', (user['id'], refresh_token)
                )
                conn.commit()
                auth_user = build_auth_user(cursor, user)
                return {
                    'status': 'ok',
                    'user': auth_user,
                    'api_key': api_key,
                    'access_token': api_key,
                    'refresh_token': refresh_token,
                }
        finally:
            conn.close()


@router.post('/auth/refresh')
def refresh_access_token(req: RefreshRequest, request: Request):
    """Exchange a refresh token for a fresh access token (api_key)."""
    with auth_attempt(request):
        conn = get_db_connection()
        if not conn:
            raise HTTPException(status_code=500, detail='Database connection failed')
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    'SELECT * FROM user_refresh_tokens WHERE token = %s AND revoked_at IS NULL', (req.refresh_token,)
                )
                token_row = cursor.fetchone()
                if not token_row:
                    raise HTTPException(status_code=401, detail='Invalid or revoked refresh token')
                cursor.execute('SELECT * FROM users WHERE id = %s', (token_row['user_id'],))
                user = cursor.fetchone()
                if not user or not user.get('enabled', True):
                    raise HTTPException(status_code=403, detail='Account disabled')
                cursor.execute('UPDATE user_refresh_tokens SET last_used_at = NOW() WHERE id = %s', (token_row['id'],))
                conn.commit()
                auth_user = build_auth_user(cursor, user)
                return {'status': 'ok', 'user': auth_user, 'api_key': user['api_key'], 'access_token': user['api_key']}
        finally:
            conn.close()


@router.get('/auth/setup-status')
def get_setup_status():
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) as count FROM users')
            res = cursor.fetchone()
            return {'setup_required': res['count'] == 0}
    finally:
        conn.close()


@router.post('/auth/setup')
def setup_admin(user: UserCreate, request: Request):
    # Every call counts here, not just the rejected ones: this endpoint is
    # unauthenticated until the first admin exists and is legitimately used
    # exactly once, so there is no successful traffic to protect.
    with auth_attempt(request, count_successes=True):
        conn = get_db_connection()
        if not conn:
            raise HTTPException(status_code=500, detail='Database connection failed')
        try:
            with conn.cursor() as cursor:
                cursor.execute('SELECT COUNT(*) as count FROM users')
                if cursor.fetchone()['count'] > 0:
                    raise HTTPException(status_code=400, detail='Setup already completed')

                if not user.password:
                    raise HTTPException(status_code=400, detail='Password is required for first-time setup')

                password_hash = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                token = user.api_key or secrets.token_hex(32)
                admin_role = rbac.get_role_by_name(cursor, rbac.ADMIN_ROLE_NAME)

                cursor.execute(
                    'INSERT INTO users (username, display_name, is_admin, role_id, enabled, password_hash, api_key, server_user_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
                    (
                        user.username,
                        user.display_name or user.username,
                        True,
                        admin_role['id'] if admin_role else None,
                        True,
                        password_hash,
                        token,
                        user.server_user_id,
                    ),
                )
                conn.commit()

                # Notify server to sync users
                notify_server_sync_users()

                return {
                    'status': 'ok',
                    'id': cursor.lastrowid,
                    'username': user.username,
                    'display_name': user.display_name or user.username,
                    'role_name': rbac.ADMIN_ROLE_NAME,
                    'is_admin': True,
                    'api_key': token,
                }
        finally:
            conn.close()


@router.get('/{user_id}/dynamic-playlists')
def get_dynamic_playlists(user_id: int, auth: dict = Depends(verify_api_key)):
    if auth.get('type') == 'user' and auth['user']['id'] != user_id and (not has_permission(auth, 'users.update')):
        raise HTTPException(status_code=403, detail='Forbidden')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='DB failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT * FROM dynamic_playlists WHERE user_id = %s', (user_id,))
            return cursor.fetchall()
    finally:
        conn.close()


@router.get('/{user_id}/dynamic-playlists/{playlist_id}')
def get_dynamic_playlist(user_id: int, playlist_id: int, auth: dict = Depends(verify_api_key)):
    if auth.get('type') == 'user' and auth['user']['id'] != user_id and (not has_permission(auth, 'users.update')):
        raise HTTPException(status_code=403, detail='Forbidden')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT * FROM dynamic_playlists WHERE id = %s AND user_id = %s', (playlist_id, user_id))
            res = cursor.fetchone()
            if not res:
                raise HTTPException(status_code=404)
            return res
    finally:
        conn.close()


@router.post('/{user_id}/dynamic-playlists')
def create_dynamic_playlist(user_id: int, playlist: DynamicPlaylistCreate, auth: dict = Depends(verify_api_key)):
    if auth.get('type') == 'user' and auth['user']['id'] != user_id and (not has_permission(auth, 'users.update')):
        raise HTTPException(status_code=403, detail='Forbidden')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                'INSERT INTO dynamic_playlists (user_id, name, params) VALUES (%s, %s, %s)',
                (user_id, playlist.name, playlist.params),
            )
            conn.commit()
            return {'status': 'ok', 'id': cursor.lastrowid}
    finally:
        conn.close()


@router.put('/{user_id}/dynamic-playlists/{playlist_id}')
def update_dynamic_playlist(
    user_id: int, playlist_id: int, playlist: DynamicPlaylistUpdate, auth: dict = Depends(verify_api_key)
):
    if auth.get('type') == 'user' and auth['user']['id'] != user_id and (not has_permission(auth, 'users.update')):
        raise HTTPException(status_code=403, detail='Forbidden')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            if playlist.name and playlist.params:
                cursor.execute(
                    'UPDATE dynamic_playlists SET name = %s, params = %s WHERE id = %s AND user_id = %s',
                    (playlist.name, playlist.params, playlist_id, user_id),
                )
            elif playlist.name:
                cursor.execute(
                    'UPDATE dynamic_playlists SET name = %s WHERE id = %s AND user_id = %s',
                    (playlist.name, playlist_id, user_id),
                )
            elif playlist.params:
                cursor.execute(
                    'UPDATE dynamic_playlists SET params = %s WHERE id = %s AND user_id = %s',
                    (playlist.params, playlist_id, user_id),
                )
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()


@router.delete('/{user_id}/dynamic-playlists/{playlist_id}')
def delete_dynamic_playlist(user_id: int, playlist_id: int, auth: dict = Depends(verify_api_key)):
    if auth.get('type') == 'user' and auth['user']['id'] != user_id and (not has_permission(auth, 'users.update')):
        raise HTTPException(status_code=403, detail='Forbidden')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM dynamic_playlists WHERE id = %s AND user_id = %s', (playlist_id, user_id))
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()


@router.get('/{user_id}/dynamic-playlists/{playlist_id}/tracks')
def get_playlist_tracks(user_id: int, playlist_id: int, auth: dict = Depends(verify_api_key)):
    if auth.get('type') == 'user' and auth['user']['id'] != user_id and (not has_permission(auth, 'users.update')):
        raise HTTPException(status_code=403, detail='Forbidden')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT username FROM users WHERE id = %s', (user_id,))
            user_row = cursor.fetchone()
            username = user_row['username'] if user_row else 'unknown'
            cursor.execute(
                'SELECT params FROM dynamic_playlists WHERE id = %s AND user_id = %s', (playlist_id, user_id)
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404)
            params_str = row['params']
            try:
                params = json.loads(params_str)
            except json.JSONDecodeError:
                params = {}
                if '&' in params_str or '=' in params_str:
                    for part in params_str.split('&'):
                        if '=' in part:
                            k, v = part.split('=', 1)
                            params[k] = v
            genres = params.get('genres', [])
            rating_range = params.get('rating_range', [0, 100])
            size = int(params.get('size', 500))
            sort_method = params.get('sort_method', 'newest')
            song_type = params.get('song_type', 'both')
            rules = params.get('rules', [])
            query = "\n                SELECT DISTINCT t.id, t.title, COALESCE(a.name, 'Unknown Artist') as artist, \n                       CAST(t.created_at AS CHAR) as created_at, t.duration_secs,\n                       rt.rating\n                FROM library_tracks t\n                LEFT JOIN library_artists a ON t.primary_artist_id = a.id\n                LEFT JOIN rating_tracks rt ON rt.entity_id = t.track_uid AND rt.username = %s\n                WHERE 1=1\n            "
            q_params = [username]
            if genres:
                genre_placeholders = ', '.join(['%s'] * len(genres))
                query += f' AND (\n                    EXISTS (SELECT 1 FROM library_track_genres tg JOIN rules_genres rg ON tg.genre_id = rg.id \n                            WHERE tg.track_id = t.id AND rg.name IN ({genre_placeholders}))\n                    OR EXISTS (SELECT 1 FROM library_track_ml_labels ml \n                               WHERE ml.track_id = t.track_uid AND ml.ml_genre IN ({genre_placeholders}))\n                )'
                q_params.extend(genres)
                q_params.extend(genres)
            for rule in rules:
                col = rule.get('column')
                val = rule.get('value')
                if col == 'genre' and val not in genres:
                    query += ' AND (\n                        EXISTS (SELECT 1 FROM library_track_genres tg JOIN rules_genres rg ON tg.genre_id = rg.id WHERE tg.track_id = t.id AND rg.name = %s)\n                        OR EXISTS (SELECT 1 FROM library_track_ml_labels ml WHERE ml.track_id = t.track_uid AND ml.ml_genre = %s)\n                    )'
                    q_params.extend([val, val])
            # A range covering the whole scale is the UI's way of saying "no filter", and has to
            # build no clause at all: rating_tracks arrives by LEFT JOIN, so an unrated track has a
            # NULL rating and fails every comparison. Comparing against [0, 100] therefore dropped
            # every unrated track -- 301.340 of 302.561 of them -- and a seeded playlist came back
            # with a handful of rows instead of 500.
            if rating_range and not (rating_range[0] <= 0 and rating_range[1] >= 100):
                query += ' AND (rt.rating >= %s AND rt.rating <= %s)'
                q_params.extend([rating_range[0], rating_range[1]])
            if song_type == 'track':
                query += ' AND t.duration_secs < 600'
            elif song_type == 'set':
                query += ' AND t.duration_secs >= 600'
            if sort_method == 'random':
                query += ' ORDER BY RAND()'
            elif sort_method == 'highest_rated':
                query += ' ORDER BY rt.rating DESC, t.created_at DESC'
            elif sort_method == 'oldest':
                query += ' ORDER BY t.created_at ASC'
            else:
                query += ' ORDER BY t.created_at DESC'
            query += ' LIMIT %s'
            q_params.append(size)
            cursor.execute(query, tuple(q_params))
            return cursor.fetchall()
    finally:
        conn.close()


@router.post('/{user_id}/dynamic-playlists/seed-defaults')
def seed_defaults(user_id: int, auth: dict = Depends(verify_api_key)):
    if auth.get('type') == 'user' and auth['user']['id'] != user_id and (not has_permission(auth, 'users.update')):
        raise HTTPException(status_code=403, detail='Forbidden')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            defaults = [
                (
                    'Hardstyle',
                    json.dumps(
                        {
                            'genres': ['Hardstyle'],
                            'rating_range': [0, 100],
                            'size': 500,
                            'sort_method': 'newest',
                            'song_type': 'both',
                        }
                    ),
                ),
                (
                    'Hardcore',
                    json.dumps(
                        {
                            'genres': ['Hardcore'],
                            'rating_range': [0, 100],
                            'size': 500,
                            'sort_method': 'newest',
                            'song_type': 'both',
                        }
                    ),
                ),
                (
                    'Techno',
                    json.dumps(
                        {
                            'genres': ['Techno'],
                            'rating_range': [0, 100],
                            'size': 500,
                            'sort_method': 'newest',
                            'song_type': 'both',
                        }
                    ),
                ),
                (
                    'Recently Added',
                    json.dumps(
                        {
                            'genres': [],
                            'rating_range': [0, 100],
                            'size': 100,
                            'sort_method': 'newest',
                            'song_type': 'both',
                        }
                    ),
                ),
            ]
            for name, params in defaults:
                cursor.execute(
                    '\n                    INSERT INTO dynamic_playlists (user_id, name, params, source)\n                    VALUES (%s, %s, %s, %s)\n                    ON DUPLICATE KEY UPDATE params = VALUES(params)\n                ',
                    (user_id, name, params, 'default'),
                )
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()


@router.get('')
@router.get('/')
def get_users(auth: dict = Depends(verify_api_key)):
    if auth.get('type') == 'user' and (not has_permission(auth, 'users.read')):
        raise HTTPException(status_code=403, detail='Forbidden')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='DB failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT u.id, u.username, u.display_name, u.email, u.avatar_url, u.is_admin, u.role_id, r.name as role_name, u.enabled, u.server_user_id, u.api_key, CAST(u.created_at AS CHAR) as created_at, CAST(u.last_login_at AS CHAR) as last_login_at FROM users u LEFT JOIN roles r ON u.role_id = r.id'
            )
            return cursor.fetchall()
    finally:
        conn.close()


@router.post('')
@router.post('/')
def create_user(user: UserCreate, auth: dict = Depends(verify_api_key)):
    if auth.get('type') == 'user' and (not has_permission(auth, 'users.create')):
        raise HTTPException(status_code=403, detail='Forbidden')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        password_hash = None
        if user.password:
            password_hash = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        token = user.api_key or secrets.token_hex(16)
        with conn.cursor() as cursor:
            # New users are never given the admin role here: role assignment
            # (including admin) is a separate action gated by users.assign-role.
            default_role = rbac.get_role_by_name(cursor, rbac.DEFAULT_ROLE_NAME)
            cursor.execute(
                '\n                INSERT INTO users (username, display_name, is_admin, role_id, enabled, password_hash, api_key, server_user_id)\n                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)\n            ',
                (
                    user.username,
                    user.display_name,
                    False,
                    default_role['id'] if default_role else None,
                    True,
                    password_hash,
                    token,
                    user.server_user_id,
                ),
            )
            conn.commit()
            return {'status': 'ok', 'id': cursor.lastrowid}
    finally:
        conn.close()


@router.get('/roles')
def list_roles(auth: dict = Depends(require_permission('roles.read'))):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='DB failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT id, name, description FROM roles ORDER BY id')
            return cursor.fetchall()
    finally:
        conn.close()


@router.get('/permissions')
def list_permissions(auth: dict = Depends(require_permission('permissions.read'))):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='DB failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT id, name, description FROM permissions ORDER BY name')
            return cursor.fetchall()
    finally:
        conn.close()


@router.put('/{user_id}/role')
def assign_role(user_id: int, req: RoleAssign, auth: dict = Depends(require_permission('users.assign-role'))):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='DB failed')
    try:
        with conn.cursor() as cursor:
            role = rbac.get_role_by_name(cursor, req.role)
            if not role:
                raise HTTPException(status_code=404, detail=f"Unknown role: {req.role}")
            cursor.execute(
                'UPDATE users SET role_id = %s, is_admin = %s WHERE id = %s',
                (role['id'], req.role == rbac.ADMIN_ROLE_NAME, user_id),
            )
            actor_id = (auth.get('user') or {}).get('id')
            rbac.record_audit_event(
                cursor, 'user.role_assigned', actor_user_id=actor_id, target_user_id=user_id, details=f"role={req.role}"
            )
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()


@router.post('/{user_id}/enable')
def enable_user(user_id: int, auth: dict = Depends(require_permission('users.disable'))):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='DB failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute('UPDATE users SET enabled = TRUE WHERE id = %s', (user_id,))
            actor_id = (auth.get('user') or {}).get('id')
            rbac.record_audit_event(cursor, 'user.enabled', actor_user_id=actor_id, target_user_id=user_id)
            conn.commit()
            # LMS trusts a password it has accepted for five minutes without asking again. The
            # sync poke is what makes it forget that now rather than when its timer says so.
            notify_server_sync_users()
            return {'status': 'ok'}
    finally:
        conn.close()


@router.post('/{user_id}/disable')
def disable_user(user_id: int, auth: dict = Depends(require_permission('users.disable'))):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='DB failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute('UPDATE users SET enabled = FALSE WHERE id = %s', (user_id,))
            actor_id = (auth.get('user') or {}).get('id')
            rbac.record_audit_event(cursor, 'user.disabled', actor_user_id=actor_id, target_user_id=user_id)
            conn.commit()
            # LMS trusts a password it has accepted for five minutes without asking again. The
            # sync poke is what makes it forget that now rather than when its timer says so.
            notify_server_sync_users()
            return {'status': 'ok'}
    finally:
        conn.close()


@router.post('/{user_id}/sessions/revoke')
def revoke_sessions(user_id: int, auth: dict = Depends(verify_api_key)):
    """Revoke all active sessions for a user (their api_key + refresh tokens).

    Allowed for the user themselves (sessions.manage-own) or an admin acting
    on someone else's account (users.revoke-sessions).
    """
    is_self = auth.get('type') == 'user' and auth['user']['id'] == user_id
    if not is_self and not has_permission(auth, 'users.revoke-sessions'):
        raise HTTPException(status_code=403, detail='Forbidden')
    if (
        is_self
        and not has_permission(auth, 'sessions.manage-own')
        and not has_permission(auth, 'users.revoke-sessions')
    ):
        raise HTTPException(status_code=403, detail='Forbidden')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='DB failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute('UPDATE users SET api_key = NULL WHERE id = %s', (user_id,))
            cursor.execute(
                'UPDATE user_refresh_tokens SET revoked_at = NOW() WHERE user_id = %s AND revoked_at IS NULL',
                (user_id,),
            )
            actor_id = (auth.get('user') or {}).get('id')
            rbac.record_audit_event(cursor, 'user.sessions_revoked', actor_user_id=actor_id, target_user_id=user_id)
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()


@router.get('/{user_id}/identities')
def list_identities(user_id: int, auth: dict = Depends(verify_api_key)):
    if auth.get('type') == 'user' and auth['user']['id'] != user_id and (not has_permission(auth, 'users.read')):
        raise HTTPException(status_code=403, detail='Forbidden')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='DB failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT id, provider, provider_subject, email_at_provider, CAST(created_at AS CHAR) as created_at, CAST(last_used_at AS CHAR) as last_used_at FROM user_identities WHERE user_id = %s',
                (user_id,),
            )
            return cursor.fetchall()
    finally:
        conn.close()


@router.get('/{user_id}/listenbrainz')
@router.get('/{user_id}/lb-account')
def get_lb_account(user_id: int, auth: dict = Depends(verify_api_key)):
    if auth.get('type') == 'user' and auth['user']['id'] != user_id and (not has_permission(auth, 'users.update')):
        raise HTTPException(status_code=403, detail='Forbidden')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='DB failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT lb_username, lb_token FROM user_listenbrainz_accounts WHERE user_id = %s', (user_id,)
            )
            res = cursor.fetchone()
            return res or {'lb_username': '', 'lb_token': ''}
    finally:
        conn.close()


@router.post('/{user_id}/listenbrainz')
@router.put('/{user_id}/listenbrainz')
@router.put('/{user_id}/lb-account')
def update_lb_account(user_id: int, lb_data: LBAccountUpdate, auth: dict = Depends(verify_api_key)):
    if auth.get('type') == 'user' and auth['user']['id'] != user_id and (not has_permission(auth, 'users.update')):
        raise HTTPException(status_code=403, detail='Forbidden')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='DB failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                '\n                INSERT INTO user_listenbrainz_accounts (user_id, lb_username, lb_token)\n                VALUES (%s, %s, %s)\n                ON DUPLICATE KEY UPDATE lb_username = VALUES(lb_username), lb_token = VALUES(lb_token)\n            ',
                (user_id, lb_data.lb_username, lb_data.lb_token),
            )
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()


def delete_user_row(cursor, user_id: int, actor_id=None, protect_last_admin: bool = True):
    """Delete a user and all its dependent rows; shared by ``delete_user`` and
    the ``user-requests`` unapprove flow so both get the exact same, robust
    cleanup (and the same clear error on failure) instead of two diverging
    implementations of "verwijderen gaat niet altijd goed".

    Returns the deleted user's row (as fetched before deletion). Raises
    ``HTTPException`` on a not-found user or (when ``protect_last_admin``) on
    an attempt to delete the last remaining admin account.
    """
    cursor.execute('SELECT id, username, role_id FROM users WHERE id = %s', (user_id,))
    target = cursor.fetchone()
    if not target:
        raise HTTPException(status_code=404, detail='User not found')

    if protect_last_admin:
        # Refuse to delete the last remaining admin account -- otherwise
        # the whole system could be left without anyone able to manage
        # users/roles at all.
        admin_role = rbac.get_role_by_name(cursor, rbac.ADMIN_ROLE_NAME)
        if admin_role and target.get('role_id') == admin_role['id']:
            cursor.execute('SELECT COUNT(*) as cnt FROM users WHERE role_id = %s', (admin_role['id'],))
            if cursor.fetchone()['cnt'] <= 1:
                raise HTTPException(status_code=400, detail='Kan de laatste beheerder niet verwijderen')

    # Defensively remove dependent rows ourselves first, instead of
    # relying only on the FK ON DELETE CASCADE/SET NULL constraints:
    # those are declared on CREATE TABLE IF NOT EXISTS, which never
    # retrofits an already-existing table on older deployments, so a
    # stray leftover row there could otherwise turn this into an
    # unhandled 500 with no clear cause ("verwijderen gaat niet altijd
    # goed").
    for table in (
        'user_identities',
        'user_refresh_tokens',
        'dynamic_playlists',
        'user_app_settings',
        'user_listenbrainz_accounts',
    ):
        cursor.execute(f'DELETE FROM {table} WHERE user_id = %s', (user_id,))
    cursor.execute('UPDATE user_requests SET reviewed_by_user_id = NULL WHERE reviewed_by_user_id = %s', (user_id,))
    cursor.execute('UPDATE user_requests SET created_user_id = NULL WHERE created_user_id = %s', (user_id,))

    cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
    rbac.record_audit_event(
        cursor, 'user.deleted', actor_user_id=actor_id, target_user_id=user_id, details=f"username={target['username']}"
    )
    return target


@router.delete('/{user_id}')
def delete_user(user_id: int, auth: dict = Depends(verify_api_key)):
    if auth.get('type') == 'user' and auth['user']['id'] != user_id and (not has_permission(auth, 'users.update')):
        raise HTTPException(status_code=403, detail='Forbidden')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='DB failed')
    try:
        with conn.cursor() as cursor:
            actor_id = (auth.get('user') or {}).get('id')
            delete_user_row(cursor, user_id, actor_id=actor_id)
            conn.commit()
            return {'status': 'ok'}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Verwijderen mislukt: {e}') from e
    finally:
        conn.close()


@router.post('/{user_id}/merge')
def merge_users(user_id: int, req: MergeUsersRequest, auth: dict = Depends(require_permission('users.merge'))):
    """Merge ``req.secondary_user_id`` into ``user_id`` (the account that survives).

    This is the fix for ending up with two separate accounts for the same
    person -- e.g. one created via ``/api/auth/access-request`` approval for
    a Google identity, and a pre-existing local/Subsonic account -- because
    approving a request always creates a brand new user with no way to link
    it to an already-existing one.

    Every piece of data owned by the secondary account (login identities,
    sessions, dynamic playlists, per-app settings, ListenBrainz link, ratings
    and scrobble history) is moved onto the primary account, then the
    secondary account is deleted. Data the primary account already has for
    the same provider/app/track simply wins, so a conflict can never make the
    merge fail.
    """
    primary_id = user_id
    secondary_id = req.secondary_user_id
    if primary_id == secondary_id:
        raise HTTPException(status_code=400, detail='Kan een gebruiker niet met zichzelf samenvoegen')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='DB failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT * FROM users WHERE id = %s', (primary_id,))
            primary = cursor.fetchone()
            cursor.execute('SELECT * FROM users WHERE id = %s', (secondary_id,))
            secondary = cursor.fetchone()
            if not primary or not secondary:
                raise HTTPException(status_code=404, detail='Gebruiker niet gevonden')

            # 1) Login identities (e.g. Google): keep the primary's own link
            #    to a given provider if it already has one, otherwise adopt
            #    the secondary's.
            cursor.execute('SELECT provider FROM user_identities WHERE user_id = %s', (primary_id,))
            existing_providers = {row['provider'] for row in cursor.fetchall()}
            cursor.execute('SELECT id, provider FROM user_identities WHERE user_id = %s', (secondary_id,))
            for identity in cursor.fetchall():
                if identity['provider'] in existing_providers:
                    cursor.execute('DELETE FROM user_identities WHERE id = %s', (identity['id'],))
                else:
                    cursor.execute(
                        'UPDATE user_identities SET user_id = %s WHERE id = %s', (primary_id, identity['id'])
                    )

            # 2) Sessions: the secondary's refresh tokens/api_key are dropped;
            #    whoever was logged in on it needs to log in again, on the
            #    now-merged primary account.
            cursor.execute('DELETE FROM user_refresh_tokens WHERE user_id = %s', (secondary_id,))

            # 3) Dynamic playlists are unique on (source, remote_id), not on
            #    user_id, so re-pointing them is always safe.
            cursor.execute('UPDATE dynamic_playlists SET user_id = %s WHERE user_id = %s', (primary_id, secondary_id))

            # 4) Per-app settings (unique on user_id+app_id): keep the
            #    primary's if it already has settings for that app.
            cursor.execute('SELECT app_id FROM user_app_settings WHERE user_id = %s', (primary_id,))
            existing_apps = {row['app_id'] for row in cursor.fetchall()}
            cursor.execute('SELECT id, app_id FROM user_app_settings WHERE user_id = %s', (secondary_id,))
            for setting in cursor.fetchall():
                if setting['app_id'] in existing_apps:
                    cursor.execute('DELETE FROM user_app_settings WHERE id = %s', (setting['id'],))
                else:
                    cursor.execute(
                        'UPDATE user_app_settings SET user_id = %s WHERE id = %s', (primary_id, setting['id'])
                    )

            # 5) ListenBrainz link (unique on user_id): keep the primary's if set.
            cursor.execute('SELECT user_id FROM user_listenbrainz_accounts WHERE user_id = %s', (primary_id,))
            if cursor.fetchone():
                cursor.execute('DELETE FROM user_listenbrainz_accounts WHERE user_id = %s', (secondary_id,))
            else:
                cursor.execute(
                    'UPDATE user_listenbrainz_accounts SET user_id = %s WHERE user_id = %s', (primary_id, secondary_id)
                )

            # 6) Ratings & scrobble history are keyed by *username* (not
            #    user_id) -- repoint them to the primary's username. Wherever
            #    the primary already has a row for the same unique key, the
            #    primary's row simply wins and the secondary's leftover is
            #    dropped, so this can never fail on a duplicate-key conflict.
            for table, key_cols in (
                ('rating_tracks', ('entity_type', 'entity_id')),
                ('scrobble_listens', ('listened_at', 'track_id')),
                ('scrobble_unmatched_listens', ('listened_at', 'artist_name', 'track_title')),
            ):
                cols = ', '.join(key_cols)
                cursor.execute(f'SELECT id, {cols} FROM {table} WHERE username = %s', (secondary['username'],))
                for row in cursor.fetchall():
                    where_clause = ' AND '.join(f'{c} = %s' for c in key_cols)
                    cursor.execute(
                        f'SELECT id FROM {table} WHERE username = %s AND {where_clause}',
                        (primary['username'], *[row[c] for c in key_cols]),
                    )
                    if cursor.fetchone():
                        cursor.execute(f'DELETE FROM {table} WHERE id = %s', (row['id'],))
                    else:
                        cursor.execute(
                            f'UPDATE {table} SET username = %s WHERE id = %s', (primary['username'], row['id'])
                        )
            cursor.execute(
                'UPDATE scrobble_imports SET username = %s WHERE username = %s',
                (primary['username'], secondary['username']),
            )

            # 7) Historical references to the secondary account.
            cursor.execute(
                'UPDATE user_requests SET reviewed_by_user_id = %s WHERE reviewed_by_user_id = %s',
                (primary_id, secondary_id),
            )
            cursor.execute(
                'UPDATE user_requests SET created_user_id = %s WHERE created_user_id = %s', (primary_id, secondary_id)
            )

            cursor.execute('DELETE FROM users WHERE id = %s', (secondary_id,))

            actor_id = (auth.get('user') or {}).get('id')
            rbac.record_audit_event(
                cursor,
                'user.merged',
                actor_user_id=actor_id,
                target_user_id=primary_id,
                details=f"merged user_id={secondary_id} (username={secondary['username']}) into user_id={primary_id} (username={primary['username']})",
            )
            conn.commit()
            cursor.execute(
                'SELECT u.id, u.username, u.display_name, u.email, u.avatar_url, u.is_admin, u.role_id, r.name as role_name, u.enabled, u.server_user_id, u.api_key FROM users u LEFT JOIN roles r ON u.role_id = r.id WHERE u.id = %s',
                (primary_id,),
            )
            return {'status': 'ok', 'user': cursor.fetchone()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Samenvoegen mislukt: {e}') from e
    finally:
        conn.close()


@router.post('/{user_id}/password')
@router.put('/{user_id}/password')
def update_password(user_id: int, req: PasswordUpdate, auth: dict = Depends(verify_api_key)):
    if auth.get('type') == 'user' and auth['user']['id'] != user_id and (not has_permission(auth, 'users.update')):
        raise HTTPException(status_code=403, detail='Forbidden')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        password_hash = bcrypt.hashpw(req.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        with conn.cursor() as cursor:
            cursor.execute('UPDATE users SET password_hash = %s WHERE id = %s', (password_hash, user_id))
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()


@router.get('/{user_id}/settings/{app_id}')
def get_user_app_settings(user_id: int, app_id: str, auth: dict = Depends(verify_api_key)):
    if auth.get('type') == 'user' and auth['user']['id'] != user_id and (not has_permission(auth, 'users.update')):
        raise HTTPException(status_code=403, detail='Forbidden')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT settings_json, CAST(updated_at AS CHAR) as updated_at FROM user_app_settings WHERE user_id = %s AND app_id = %s',
                (user_id, app_id),
            )
            res = cursor.fetchone()
            if not res:
                return {'settings': None}
            return {'settings': res['settings_json'], 'updated_at': res['updated_at']}
    finally:
        conn.close()


@router.post('/{user_id}/settings/{app_id}')
def update_user_app_settings(user_id: int, app_id: str, req: AppSettingsUpdate, auth: dict = Depends(verify_api_key)):
    if auth.get('type') == 'user' and auth['user']['id'] != user_id and (not has_permission(auth, 'users.update')):
        raise HTTPException(status_code=403, detail='Forbidden')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            # Without this the insert fails on the foreign key and answers 500, which reads like the
            # server broke rather than like the caller naming a user that is not there. A client
            # that had lost track of its own account id spent a day producing exactly that.
            cursor.execute('SELECT id FROM users WHERE id = %s', (user_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail='User not found')
            cursor.execute(
                '\n                INSERT INTO user_app_settings (user_id, app_id, settings_json)\n                VALUES (%s, %s, %s)\n                ON DUPLICATE KEY UPDATE settings_json = VALUES(settings_json)\n            ',
                (user_id, app_id, req.settings),
            )
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()


@router.post('/sync/muma-server')
@router.post('/sync/lms')
@router.post('/sync/lms-db')
def sync_lms_db(background_tasks: BackgroundTasks, _api_key: str = Depends(verify_api_key)):
    # Run synchronously to return count to UI
    synced = run_lms_db_sync()
    return {'message': 'Music Management Server DB sync completed', 'synced': synced}


def notify_server_sync_users():
    if not MUMA_SERVER_HOSTS:
        return

    for host in MUMA_SERVER_HOSTS.split(','):
        host = host.strip()
        if not host:
            continue
        try:
            url = f"http://{host}/muma/users/sync"
            headers = {}
            if API_KEY:
                headers['X-API-Key'] = API_KEY

            requests.post(url, headers=headers, timeout=5)
            print(f"Notified server {host} to sync users")
        except Exception as e:
            print(f"Failed to notify server {host}: {e}")


def _sync_server_users(cursor, sqlite_cursor):
    # Users are now managed by Music Manager and fetched by the server
    # We no longer pull users from the server
    return 0


def _sync_server_playlists(cursor, sqlite_cursor, source):
    try:
        sqlite_cursor.execute('PRAGMA table_info(tracklist)')
        columns = [col[1] for col in sqlite_cursor.fetchall()]
        if 'smart_params' in columns:
            sqlite_cursor.execute('SELECT id, user_id, name, smart_params FROM tracklist WHERE type = 2')
            for lms_id, lms_user_ptr, name, params in sqlite_cursor.fetchall():
                cursor.execute('SELECT id FROM users WHERE server_user_id = %s', (str(lms_user_ptr),))
                u_row = cursor.fetchone()
                if u_row:
                    cursor.execute(
                        '\n                        INSERT INTO dynamic_playlists (user_id, remote_id, source, name, params)\n                        VALUES (%s, %s, %s, %s, %s)\n                        ON DUPLICATE KEY UPDATE name = VALUES(name), params = VALUES(params)\n                    ',
                        (u_row['id'], lms_id, source, name, params),
                    )
    except Exception as pe:
        print(f'Playlist sync failed for {source}: {pe}')


#: Servers whose schema was not ready during the last sync, by source name. Read by
#: run_lms_db_sync_with_retry to decide whether coming back is worth it.
_skipped_unmigrated_servers: set[str] = set()


def sync_single_server_db(muma_conn, db_path, source):
    print(f'Syncing Music Management Server DB: {db_path} ({source})')
    synced_users = 0
    try:
        sqlite_conn = sqlite3.connect(db_path)
        sqlite_cursor = sqlite_conn.cursor()

        # NOTE: this used to DROP TABLE the server's "user" table here on the theory that
        # it (along with auth_token/ui_state) was purely volatile/in-memory server-side state.
        # That is only true for auth_token/ui_state, which live in the server's private
        # `ATTACH DATABASE 'file::memory:...' AS volatile` schema and are therefore never
        # actually visible/droppable through this on-disk connection anyway (a harmless
        # no-op). "user" is a real, persistent, non-volatile table the running server reads
        # and writes directly -- dropping it here (while the server may have it open) caused
        # a production outage (see docs/bug-reports/005-lms-user-table-corruption.md). Users
        # are managed by Music Manager and delegated-auth-synced into that table by the
        # server itself (UserSynchronizer); this sync must never touch it.

        with muma_conn.cursor() as cursor:
            synced_users = _sync_server_users(cursor, sqlite_cursor)
            muma_conn.commit()
            _sync_server_playlists(cursor, sqlite_cursor, source)
            muma_conn.commit()
        from services.music_manager.routers.artist_images import sync_artist_images_to_server

        sync_artist_images_to_server(muma_conn, sqlite_conn)
        # After the images, and equally best-effort: what muma decided about song versions.
        # A server that has not migrated to 118 yet is skipped rather than failed, and a
        # locked database costs this pass and nothing more.
        from services.music_manager.song_version_sync import sync_song_versions_to_server

        versions = sync_song_versions_to_server(muma_conn, sqlite_conn, source)
        if versions.get('skipped_no_columns'):
            # The server is still migrating. Remembered so the caller can come back rather
            # than leaving the columns empty until the next restart.
            _skipped_unmigrated_servers.add(source)
        sqlite_conn.close()
    except Exception as e:
        print(f'Sync failed for {db_path}: {e}')
    return synced_users


def run_lms_db_sync_with_retry(attempts: int = 6, delay_seconds: int = 60) -> int:
    """Run the lms.db sync, and try again while a server has not migrated yet.

    A deploy restarts both services at once, and muma usually wins: it syncs before the
    server has applied its own schema migration, finds no version columns, and skips. That
    was correct -- writing to a schema that is mid-migration is the one thing not to do --
    but nothing came back afterwards, so the columns stayed empty until somebody restarted
    the container by hand. That happened on the 0.54.0 deploy, and without the restart the
    release would have shipped a feature that silently did nothing.

    Retries only while a database was skipped for that reason. Everything else -- a locked
    database, an unreachable server, no lms.db at all -- is already best-effort inside the
    sync itself and gets no second pass here.
    """
    for attempt in range(1, attempts + 1):
        synced = run_lms_db_sync()
        if not _skipped_unmigrated_servers:
            return synced
        if attempt == attempts:
            logging.warning(
                'lms.db sync: %s server database(s) still have no version columns after %s attempts; '
                'the song-version columns stay empty until the next restart',
                len(_skipped_unmigrated_servers),
                attempts,
            )
            return synced
        logging.info(
            'lms.db sync: %s server database(s) not migrated yet, trying again in %ss',
            len(_skipped_unmigrated_servers),
            delay_seconds,
        )
        time.sleep(delay_seconds)
    return 0


def run_lms_db_sync():
    _skipped_unmigrated_servers.clear()
    db_root = os.getenv('MUMA_SERVER_DB_ROOT') or os.getenv('LMS_DB_ROOT') or '/app/data'
    targets = []

    # Check for a direct database path first
    direct_db = os.getenv('MUMA_SERVER_DB_PATH') or os.getenv('LMS_DB_PATH')
    if direct_db and os.path.exists(direct_db):
        targets.append((direct_db, 'server-direct'))

    if os.path.exists(db_root):
        # Look for lms.db in subdirectories (legacy/multi-server support)
        for entry in os.listdir(db_root):
            full_path = os.path.join(db_root, entry)
            if os.path.isdir(full_path):
                db_file = os.path.join(full_path, 'lms.db')
                if os.path.exists(db_file):
                    targets.append((db_file, f'server-{entry}'))

        # Also look for lms.db directly in root (consolidated support)
        root_db = os.path.join(db_root, 'lms.db')
        if os.path.exists(root_db):
            targets.append((root_db, 'server-root'))

    conn = get_db_connection()
    if not conn:
        return 0
    total_synced = 0
    try:
        for db_path, source in targets:
            total_synced += sync_single_server_db(conn, db_path, source)
    finally:
        conn.close()
    return total_synced
