"""Google identity login and the resulting UserRequest access-request flow.

Flow (see AGENTS.md / issue for the full spec):
  1. POST /api/auth/google validates the Google ID token and resolves it to
     either an existing linked User (normal login) or an unknown identity.
  2. For an unknown identity the client shows an access-request screen; the
     user explicitly submits it via POST /api/auth/access-request, which
     creates a single UserRequest (pending) per Google `sub`.
  3. An admin (user-requests.read/approve/reject) reviews it via the
     /api/user-requests endpoints below. Approval creates a new User with the
     default 'user' role and a linked Google UserIdentity -- never 'admin'.
"""
import os
import secrets
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from services.music_manager.database import get_db_connection
from services.music_manager import rbac
from services.music_manager.rbac import require_permission

router = APIRouter(tags=['user-requests'])

GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')


def init_db(_cursor):
    # Tables are created by rbac.init_db (called from routers/users.py init_db).
    pass


class GoogleAuthRequest(BaseModel):
    id_token: str


class RequestReview(BaseModel):
    reason: Optional[str] = None


def _verify_google_id_token(id_token_str: str) -> dict:
    """Validate a Google ID token and return its claims (sub, email, name, picture)."""
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests
    except ImportError as exc:
        raise HTTPException(status_code=500, detail='Google auth support is not installed on the server') from exc

    try:
        request_adapter = google_requests.Request()
        claims = google_id_token.verify_oauth2_token(id_token_str, request_adapter, audience=GOOGLE_CLIENT_ID)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=f'Invalid Google token: {exc}') from exc

    if claims.get('iss') not in ('accounts.google.com', 'https://accounts.google.com'):
        raise HTTPException(status_code=401, detail='Invalid Google token issuer')
    return claims


def _request_to_dict(row):
    return {
        'id': row['id'],
        'google_subject': row['google_subject'],
        'email': row.get('email'),
        'display_name': row.get('display_name'),
        'avatar_url': row.get('avatar_url'),
        'status': row['status'],
        'requested_at': str(row.get('requested_at')) if row.get('requested_at') else None,
        'reviewed_at': str(row.get('reviewed_at')) if row.get('reviewed_at') else None,
        'reviewed_by_user_id': row.get('reviewed_by_user_id'),
        'created_user_id': row.get('created_user_id'),
    }


@router.post('/auth/google')
def google_login(req: GoogleAuthRequest):
    """Resolve a Google ID token to an internal session, or to request status."""
    claims = _verify_google_id_token(req.id_token)
    subject = claims['sub']
    email = claims.get('email')
    display_name = claims.get('name') or email
    avatar_url = claims.get('picture')

    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT * FROM user_identities WHERE provider = %s AND provider_subject = %s', ('google', subject))
            identity = cursor.fetchone()
            if identity:
                cursor.execute('SELECT * FROM users WHERE id = %s', (identity['user_id'],))
                user = cursor.fetchone()
                if not user:
                    raise HTTPException(status_code=404, detail='Linked user no longer exists')
                if not user.get('enabled', True):
                    raise HTTPException(status_code=403, detail='Account disabled')

                cursor.execute('UPDATE user_identities SET email_at_provider = %s WHERE id = %s', (email, identity['id']))
                api_key = user['api_key'] or secrets.token_hex(32)
                refresh_token = secrets.token_hex(32)
                cursor.execute('UPDATE users SET api_key = %s, last_login_at = NOW() WHERE id = %s', (api_key, user['id']))
                cursor.execute('INSERT INTO user_refresh_tokens (user_id, token) VALUES (%s, %s)', (user['id'], refresh_token))
                conn.commit()

                from services.music_manager.routers.users import build_auth_user
                auth_user = build_auth_user(cursor, user)
                return {'status': 'ok', **auth_user, 'api_key': api_key, 'access_token': api_key, 'refresh_token': refresh_token}

            # No linked identity yet: report any existing access request status.
            cursor.execute('SELECT * FROM user_requests WHERE google_subject = %s', (subject,))
            existing = cursor.fetchone()
            if existing:
                cursor.execute(
                    'UPDATE user_requests SET email = %s, display_name = %s, avatar_url = %s WHERE id = %s',
                    (email, display_name, avatar_url, existing['id'])
                )
                conn.commit()
                cursor.execute('SELECT * FROM user_requests WHERE id = %s', (existing['id'],))
                existing = cursor.fetchone()
                return {'status': f"request_{existing['status']}", 'request': _request_to_dict(existing)}

            return {
                'status': 'unknown',
                'google': {'subject': subject, 'email': email, 'display_name': display_name, 'avatar_url': avatar_url}
            }
    finally:
        conn.close()


@router.post('/auth/access-request')
def create_access_request(req: GoogleAuthRequest):
    """Explicitly submit an access request for an unknown Google identity."""
    claims = _verify_google_id_token(req.id_token)
    subject = claims['sub']
    email = claims.get('email')
    display_name = claims.get('name') or email
    avatar_url = claims.get('picture')

    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT id FROM user_identities WHERE provider = %s AND provider_subject = %s', ('google', subject))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail='This Google account is already linked to a user; log in instead')

            cursor.execute('SELECT * FROM user_requests WHERE google_subject = %s', (subject,))
            existing = cursor.fetchone()
            if existing:
                # Requesting access again must not create a duplicate; just report status.
                return {'status': 'ok', 'request': _request_to_dict(existing)}

            cursor.execute(
                'INSERT INTO user_requests (google_subject, email, display_name, avatar_url, status) VALUES (%s, %s, %s, %s, %s)',
                (subject, email, display_name, avatar_url, 'pending')
            )
            conn.commit()
            cursor.execute('SELECT * FROM user_requests WHERE google_subject = %s', (subject,))
            created = cursor.fetchone()
            return {'status': 'ok', 'request': _request_to_dict(created)}
    finally:
        conn.close()


@router.get('/user-requests')
def list_user_requests(status: Optional[str] = None, auth: dict = Depends(require_permission('user-requests.read'))):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            if status:
                cursor.execute('SELECT * FROM user_requests WHERE status = %s ORDER BY requested_at DESC', (status,))
            else:
                cursor.execute('SELECT * FROM user_requests ORDER BY requested_at DESC')
            return [_request_to_dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


@router.post('/user-requests/{request_id}/approve')
def approve_user_request(request_id: int, _body: RequestReview = RequestReview(), auth: dict = Depends(require_permission('user-requests.approve'))):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT * FROM user_requests WHERE id = %s', (request_id,))
            req = cursor.fetchone()
            if not req:
                raise HTTPException(status_code=404, detail='Request not found')
            if req['status'] != 'pending':
                raise HTTPException(status_code=400, detail=f"Request is already {req['status']}")

            default_role = rbac.get_role_by_name(cursor, rbac.DEFAULT_ROLE_NAME)
            username = req.get('email') or f"google-{req['google_subject'][:12]}"
            api_key = secrets.token_hex(32)
            cursor.execute(
                'INSERT INTO users (username, display_name, email, avatar_url, is_admin, role_id, enabled, api_key) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
                (username, req.get('display_name') or username, req.get('email'), req.get('avatar_url'), False, default_role['id'] if default_role else None, True, api_key)
            )
            new_user_id = cursor.lastrowid
            cursor.execute(
                'INSERT INTO user_identities (user_id, provider, provider_subject, email_at_provider) VALUES (%s, %s, %s, %s)',
                (new_user_id, 'google', req['google_subject'], req.get('email'))
            )
            actor_id = (auth.get('user') or {}).get('id')
            cursor.execute(
                'UPDATE user_requests SET status = %s, reviewed_at = NOW(), reviewed_by_user_id = %s, created_user_id = %s WHERE id = %s',
                ('approved', actor_id, new_user_id, request_id)
            )
            rbac.record_audit_event(cursor, 'user_request.approved', actor_user_id=actor_id, target_user_id=new_user_id, details=f"request_id={request_id}")
            conn.commit()
            cursor.execute('SELECT * FROM user_requests WHERE id = %s', (request_id,))
            return {'status': 'ok', 'request': _request_to_dict(cursor.fetchone())}
    finally:
        conn.close()


@router.post('/user-requests/{request_id}/reject')
def reject_user_request(request_id: int, body: RequestReview = RequestReview(), auth: dict = Depends(require_permission('user-requests.reject'))):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT * FROM user_requests WHERE id = %s', (request_id,))
            req = cursor.fetchone()
            if not req:
                raise HTTPException(status_code=404, detail='Request not found')
            if req['status'] != 'pending':
                raise HTTPException(status_code=400, detail=f"Request is already {req['status']}")

            actor_id = (auth.get('user') or {}).get('id')
            cursor.execute(
                'UPDATE user_requests SET status = %s, reviewed_at = NOW(), reviewed_by_user_id = %s WHERE id = %s',
                ('rejected', actor_id, request_id)
            )
            rbac.record_audit_event(cursor, 'user_request.rejected', actor_user_id=actor_id, target_user_id=None, details=f"request_id={request_id}, reason={body.reason}")
            conn.commit()
            cursor.execute('SELECT * FROM user_requests WHERE id = %s', (request_id,))
            return {'status': 'ok', 'request': _request_to_dict(cursor.fetchone())}
    finally:
        conn.close()
