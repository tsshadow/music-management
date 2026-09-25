import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('mutagen', 'markdown', 'pymysql', 'dbutils', 'DatabaseConnector')

# Only stub these when they aren't already provided by services/tests/mock_base.py
# (loaded once for the whole pytest session via services/conftest.py) or by the real
# installed packages -- blindly overwriting sys.modules here would clobber the
# properly-constructed mutagen mock classes with a plain MagicMock, breaking
# isinstance() checks in any importer/downloader test that runs afterward in the
# same pytest session.


import services.music_manager.routers.users
from services.music_manager.api_key import resolve_system_api_key

services.music_manager.routers.users.run_lms_db_sync = lambda: None
import services.music_manager.database

services.music_manager.database.get_db_connection = MagicMock(return_value=None)

from fastapi.testclient import TestClient

from services.music_manager import rbac
from services.music_manager.main import app


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

    def test_curation_permission_exists_and_is_not_granted_to_plain_users(self):
        """The artist/label/genre edit pages hang off one permission.

        A normal user may look at an artist's MBID; changing it, or writing a tagging
        rule that alters how every future file is tagged, is an admin act.
        """
        names = {name for name, _ in rbac.PERMISSIONS}
        self.assertIn('rules.manage', names)
        self.assertNotIn('rules.manage', rbac.USER_ROLE_PERMISSIONS)

    def test_admin_role_is_seeded_with_every_permission(self):
        all_names = {name for name, _ in rbac.PERMISSIONS}
        self.assertTrue(rbac.USER_ROLE_PERMISSIONS.issubset(all_names))


class TestPermissionGatedEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.api_key = resolve_system_api_key()

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
            {
                'id': 5,
                'username': 'plain-user',
                'display_name': 'Plain',
                'is_admin': False,
                'role_id': 2,
                'enabled': True,
            },
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
            {
                'id': 5,
                'username': 'plain-user',
                'display_name': 'Plain',
                'is_admin': False,
                'role_id': 2,
                'enabled': True,
            },
            {'name': 'user'},
        ]
        mock_cursor.fetchall.return_value = []

        response = self.client.get('/api/users/5/dynamic-playlists', headers={'x-api-key': 'user-token'})
        self.assertEqual(response.status_code, 200)


class TestGoogleLoginAndUserRequests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.api_key = resolve_system_api_key()
        self.google_claims = {
            'sub': 'google-subject-123',
            'email': 'newperson@example.com',
            'name': 'New Person',
            'picture': 'https://example.com/avatar.png',
            'iss': 'https://accounts.google.com',
        }

    @patch('services.music_manager.routers.user_requests.GOOGLE_CLIENT_ID', None)
    def test_google_login_fails_loudly_when_client_id_is_not_configured(self):
        """A misconfigured/missing GOOGLE_CLIENT_ID must never be treated as "accept any
        Google account" (google-auth's verify_oauth2_token() silently skips the `aud`
        check when audience=None) -- it must fail with a clear server error instead.
        """
        response = self.client.post('/api/auth/google', json={'id_token': 'irrelevant'})
        self.assertEqual(response.status_code, 500)
        self.assertIn('GOOGLE_CLIENT_ID', response.json()['detail'])

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
    def test_linked_google_identity_returns_nested_user(self, mock_get_db, mock_verify):
        """A successful Google login must return {status, user, api_key, ...}, with
        the account fields nested under `user` -- matching /api/auth/login and
        /api/auth/verify -- and not spread onto the top level of the response.
        """
        mock_verify.return_value = self.google_claims
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        identity_row = {'id': 1, 'user_id': 1, 'provider': 'google', 'provider_subject': 'google-subject-123'}
        user_row = {
            'id': 1,
            'username': 'user',
            'display_name': 'user',
            'email': None,
            'avatar_url': None,
            'server_user_id': '1',
            'api_key': 'existing-api-key',
            'role_id': 1,
            'enabled': True,
        }
        # 1) identity lookup, 2) user lookup, 3) role-name lookup (inside build_auth_user)
        mock_cursor.fetchone.side_effect = [identity_row, user_row, {'name': 'admin'}]
        mock_cursor.fetchall.return_value = []

        response = self.client.post('/api/auth/google', json={'id_token': 'fake-token'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['status'], 'ok')
        self.assertIn('api_key', body)
        self.assertIn('refresh_token', body)
        self.assertNotIn('username', body, 'account fields must be nested under `user`, not spread onto the top level')
        self.assertEqual(body['user']['username'], 'user')
        self.assertEqual(body['user']['role_name'], 'admin')

    @patch('services.music_manager.routers.user_requests._verify_google_id_token')
    @patch('services.music_manager.routers.user_requests.get_db_connection')
    def test_access_request_is_idempotent_per_subject(self, mock_get_db, mock_verify):
        mock_verify.return_value = self.google_claims
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        existing_request = {
            'id': 1,
            'google_subject': 'google-subject-123',
            'email': 'newperson@example.com',
            'display_name': 'New Person',
            'avatar_url': None,
            'status': 'pending',
            'requested_at': None,
            'reviewed_at': None,
            'reviewed_by_user_id': None,
            'created_user_id': None,
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
            'id': 7,
            'google_subject': 'google-subject-123',
            'email': 'newperson@example.com',
            'display_name': 'New Person',
            'avatar_url': None,
            'status': 'pending',
        }
        approved_request = {**pending_request, 'status': 'approved'}
        mock_cursor.fetchone.side_effect = [pending_request, None, approved_request]  # None: the name is free
        mock_cursor.lastrowid = 42

        response = self.client.post('/api/user-requests/7/approve', headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        insert_call = next(c for c in mock_cursor.execute.call_args_list if 'INSERT INTO users' in c[0][0])
        # (username, display_name, email, avatar_url, is_admin, role_id, enabled, api_key)
        params = insert_call[0][1]
        self.assertFalse(params[4], 'approval must never set is_admin=True')
        self.assertEqual(params[5], 2, 'approval must assign the default user role id')

    @patch('services.music_manager.rbac.get_role_by_name')
    @patch('services.music_manager.routers.user_requests.get_db_connection')
    def test_approving_a_request_accepts_a_custom_display_name(self, mock_get_db, mock_get_role):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_role.return_value = {'id': 2, 'name': 'user'}
        pending_request = {
            'id': 8,
            'google_subject': 'google-subject-456',
            'email': 'weird.name@example.com',
            'display_name': 'weird google name',
            'avatar_url': None,
            'status': 'pending',
        }
        approved_request = {**pending_request, 'status': 'approved'}
        mock_cursor.fetchone.side_effect = [pending_request, None, approved_request]  # None: the name is free
        mock_cursor.lastrowid = 43

        response = self.client.post(
            '/api/user-requests/8/approve', json={'display_name': 'Nice Name'}, headers={'x-api-key': self.api_key}
        )
        self.assertEqual(response.status_code, 200)
        insert_call = next(c for c in mock_cursor.execute.call_args_list if 'INSERT INTO users' in c[0][0])
        params = insert_call[0][1]
        self.assertEqual(params[1], 'Nice Name', 'a supplied display_name must override the Google profile name')

    @patch('services.music_manager.routers.user_requests.get_db_connection')
    def test_approving_with_link_user_id_links_instead_of_creating(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        pending_request = {
            'id': 9,
            'google_subject': 'google-subject-789',
            'email': 'user@example.com',
            'display_name': 'Teun',
            'avatar_url': None,
            'status': 'pending',
        }
        existing_user = {'id': 1, 'username': 'user', 'display_name': 'Teun Schriks'}
        approved_request = {**pending_request, 'status': 'approved', 'created_user_id': 1, 'linked_existing': True}
        mock_cursor.fetchone.side_effect = [pending_request, existing_user, approved_request]

        response = self.client.post(
            '/api/user-requests/9/approve', json={'link_user_id': 1}, headers={'x-api-key': self.api_key}
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['request']['linked_existing'])
        create_calls = [c for c in mock_cursor.execute.call_args_list if 'INSERT INTO users' in c[0][0]]
        self.assertEqual(len(create_calls), 0, 'linking to an existing account must never create a new one')
        identity_calls = [c for c in mock_cursor.execute.call_args_list if 'INSERT INTO user_identities' in c[0][0]]
        self.assertEqual(len(identity_calls), 1)
        self.assertEqual(identity_calls[0][0][1][0], 1, 'the identity must be linked to the existing user id')

    @patch('services.music_manager.routers.user_requests.get_db_connection')
    def test_reject_pending_request(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        pending_request = {
            'id': 10,
            'google_subject': 'google-subject-000',
            'email': 'nope@example.com',
            'display_name': 'Nope',
            'avatar_url': None,
            'status': 'pending',
        }
        rejected_request = {**pending_request, 'status': 'rejected'}
        mock_cursor.fetchone.side_effect = [pending_request, rejected_request]

        response = self.client.post('/api/user-requests/10/reject', headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['request']['status'], 'rejected')

    @patch('services.music_manager.routers.user_requests.get_db_connection')
    def test_unapprove_a_pending_request_is_rejected(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'id': 11, 'status': 'pending'}

        response = self.client.post('/api/user-requests/11/unapprove', headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 400)

    @patch('services.music_manager.rbac.get_role_by_name')
    @patch('services.music_manager.routers.user_requests.get_db_connection')
    def test_unapprove_a_newly_created_account_deletes_it(self, mock_get_db, mock_get_role):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        approved_request = {
            'id': 12,
            'google_subject': 'google-subject-111',
            'email': 'newacc@example.com',
            'status': 'approved',
            'created_user_id': 55,
            'linked_existing': False,
        }
        pending_again = {**approved_request, 'status': 'pending', 'created_user_id': None, 'linked_existing': False}
        # 1) the request itself, 2) delete_user_row's own "SELECT id, username, role_id" lookup, 3) final re-fetch
        mock_cursor.fetchone.side_effect = [
            approved_request,
            {'id': 55, 'username': 'google-newacc', 'role_id': 2},
            pending_again,
        ]
        mock_get_role.return_value = {'id': 1, 'name': 'admin'}

        response = self.client.post('/api/user-requests/12/unapprove', headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['request']['status'], 'pending')
        delete_calls = [
            c for c in mock_cursor.execute.call_args_list if c[0][0].strip().startswith('DELETE FROM users')
        ]
        self.assertEqual(len(delete_calls), 1, 'unapproving a freshly-created account must delete it')

    @patch('services.music_manager.routers.user_requests.get_db_connection')
    def test_unapprove_a_linked_account_only_removes_the_identity(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        approved_request = {
            'id': 13,
            'google_subject': 'google-subject-222',
            'email': 'user@example.com',
            'status': 'approved',
            'created_user_id': 1,
            'linked_existing': True,
        }
        pending_again = {**approved_request, 'status': 'pending', 'created_user_id': None, 'linked_existing': False}
        mock_cursor.fetchone.side_effect = [approved_request, pending_again]

        response = self.client.post('/api/user-requests/13/unapprove', headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        delete_user_calls = [
            c for c in mock_cursor.execute.call_args_list if c[0][0].strip().startswith('DELETE FROM users')
        ]
        self.assertEqual(len(delete_user_calls), 0, 'a merely-linked account must never be deleted')
        delete_identity_calls = [
            c for c in mock_cursor.execute.call_args_list if 'DELETE FROM user_identities' in c[0][0]
        ]
        self.assertEqual(len(delete_identity_calls), 1)


if __name__ == '__main__':
    unittest.main()
