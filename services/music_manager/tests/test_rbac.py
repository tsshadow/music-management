import unittest
from unittest.mock import MagicMock, patch
import os
import sys

# Only stub these when they aren't already provided by services/tests/mock_base.py
# (loaded once for the whole pytest session via services/conftest.py) or by the real
# installed packages -- blindly overwriting sys.modules here would clobber the
# properly-constructed mutagen mock classes with a plain MagicMock, breaking
# isinstance() checks in any importer/downloader test that runs afterward in the
# same pytest session.
for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.easyid3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())

import services.music_manager.ntfy_listener
services.music_manager.ntfy_listener.start_ntfy_listener = lambda: None
import services.music_manager.routers.users
services.music_manager.routers.users.run_lms_db_sync = lambda: None
import services.music_manager.database
services.music_manager.database.get_db_connection = MagicMock(return_value=None)

from fastapi.testclient import TestClient
from services.music_manager.main import app
from services.music_manager import rbac


class TestRbacHelpers(unittest.TestCase):
    """Pure permission-resolution logic: no DB, no hardcoded identity checks."""

    def test_system_auth_always_has_permission(self):
        self.assertTrue(rbac.has_permission({'type': 'system'}, 'roles.manage'))
        self.assertTrue(rbac.is_admin_auth({'type': 'system'}))

    def test_user_permission_lookup(self):
        auth = {'type': 'user', 'user': {'role_name': 'user', 'permissions': ['music.read', 'music.play']}}
        self.assertTrue(rbac.has_permission(auth, 'music.read'))
        self.assertFalse(rbac.has_permission(auth, 'users.assign-role'))

    def test_is_admin_auth_derived_from_role_name(self):
        admin_auth = {'type': 'user', 'user': {'role_name': 'admin', 'permissions': []}}
        user_auth = {'type': 'user', 'user': {'role_name': 'user', 'permissions': []}}
        self.assertTrue(rbac.is_admin_auth(admin_auth))
        self.assertFalse(rbac.is_admin_auth(user_auth))

    def test_admin_role_is_seeded_with_every_permission(self):
        all_names = {name for name, _ in rbac.PERMISSIONS}
        self.assertTrue(rbac.USER_ROLE_PERMISSIONS.issubset(all_names))


class TestPermissionGatedEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.api_key = os.getenv('API_KEY') or os.getenv('MUMA_API_KEY') or '00000000-0000-4000-8000-000000000000'

    @patch('services.music_manager.routers.users.get_db_connection')
    def test_system_key_can_list_roles(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [{'id': 1, 'name': 'admin', 'description': 'Full administrative access'}]

        response = self.client.get('/api/roles', headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]['name'], 'admin')

    @patch('services.music_manager.routers.users.get_db_connection')
    def test_user_without_permission_is_forbidden(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        # verify_token: user lookup, then role-name lookup; no permissions granted.
        mock_cursor.fetchone.side_effect = [
            {'id': 5, 'username': 'plain-user', 'display_name': 'Plain', 'is_admin': False, 'role_id': 2, 'enabled': True},
            {'name': 'user'},
        ]
        mock_cursor.fetchall.return_value = []  # no permissions for this role

        response = self.client.get('/api/roles', headers={'x-api-key': 'user-token'})
        self.assertEqual(response.status_code, 403)

    @patch('services.music_manager.routers.users.get_db_connection')
    def test_dynamic_playlist_owner_can_access_own_data(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [
            {'id': 5, 'username': 'plain-user', 'display_name': 'Plain', 'is_admin': False, 'role_id': 2, 'enabled': True},
            {'name': 'user'},
        ]
        mock_cursor.fetchall.return_value = []

        response = self.client.get('/api/users/5/dynamic-playlists', headers={'x-api-key': 'user-token'})
        self.assertEqual(response.status_code, 200)


class TestGoogleLoginAndUserRequests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.api_key = os.getenv('API_KEY') or os.getenv('MUMA_API_KEY') or '00000000-0000-4000-8000-000000000000'
        self.google_claims = {
            'sub': 'google-subject-123',
            'email': 'newperson@example.com',
            'name': 'New Person',
            'picture': 'https://example.com/avatar.png',
            'iss': 'https://accounts.google.com',
        }

    @patch('services.music_manager.routers.user_requests._verify_google_id_token')
    @patch('services.music_manager.routers.user_requests.get_db_connection')
    def test_unknown_google_identity_returns_unknown_status(self, mock_get_db, mock_verify):
        mock_verify.return_value = self.google_claims
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        # No linked identity, no existing request.
        mock_cursor.fetchone.side_effect = [None, None]

        response = self.client.post('/api/auth/google', json={'id_token': 'fake-token'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['status'], 'unknown')
        self.assertEqual(body['google']['subject'], 'google-subject-123')

    @patch('services.music_manager.routers.user_requests._verify_google_id_token')
    @patch('services.music_manager.routers.user_requests.get_db_connection')
    def test_access_request_is_idempotent_per_subject(self, mock_get_db, mock_verify):
        mock_verify.return_value = self.google_claims
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        existing_request = {
            'id': 1, 'google_subject': 'google-subject-123', 'email': 'newperson@example.com',
            'display_name': 'New Person', 'avatar_url': None, 'status': 'pending',
            'requested_at': None, 'reviewed_at': None, 'reviewed_by_user_id': None, 'created_user_id': None,
        }
        # No linked identity yet, but a request already exists for this subject.
        mock_cursor.fetchone.side_effect = [None, existing_request]

        response = self.client.post('/api/auth/access-request', json={'id_token': 'fake-token'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['request']['status'], 'pending')
        insert_calls = [c for c in mock_cursor.execute.call_args_list if 'INSERT INTO user_requests' in c[0][0]]
        self.assertEqual(len(insert_calls), 0, 'must not create a duplicate request for the same Google subject')

    @patch('services.music_manager.rbac.get_role_by_name')
    @patch('services.music_manager.routers.user_requests.get_db_connection')
    def test_approving_a_request_never_assigns_admin_role(self, mock_get_db, mock_get_role):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_role.return_value = {'id': 2, 'name': 'user'}
        pending_request = {
            'id': 7, 'google_subject': 'google-subject-123', 'email': 'newperson@example.com',
            'display_name': 'New Person', 'avatar_url': None, 'status': 'pending',
        }
        approved_request = {**pending_request, 'status': 'approved'}
        mock_cursor.fetchone.side_effect = [pending_request, approved_request]
        mock_cursor.lastrowid = 42

        response = self.client.post('/api/user-requests/7/approve', headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        insert_call = next(c for c in mock_cursor.execute.call_args_list if 'INSERT INTO users' in c[0][0])
        # (username, display_name, email, avatar_url, is_admin, role_id, enabled, api_key)
        params = insert_call[0][1]
        self.assertFalse(params[4], 'approval must never set is_admin=True')
        self.assertEqual(params[5], 2, 'approval must assign the default user role id')


if __name__ == '__main__':
    unittest.main()
