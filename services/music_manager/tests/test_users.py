import unittest
from unittest.mock import MagicMock, patch
import os
import sys
import json

# Mock external modules to avoid import errors, but only when they aren't already
# provided by services/tests/mock_base.py (loaded once for the whole pytest session
# via services/conftest.py) or by the real installed packages -- blindly overwriting
# sys.modules here would clobber the properly-constructed mutagen mock classes with
# a plain MagicMock, breaking isinstance() checks in any importer/downloader test
# that runs afterward in the same pytest session.
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

class TestUsers(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.api_key = os.getenv('API_KEY') or os.getenv('MUMA_API_KEY') or '00000000-0000-4000-8000-000000000000'

    @patch('services.music_manager.routers.users.get_db_connection')
    def test_update_password_post_works(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        payload = {'password': 'newpassword123'}
        response = self.client.post('/api/users/1/password', json=payload, headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    @patch('services.music_manager.routers.users.get_db_connection')
    def test_update_password_put_works(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        payload = {'password': 'newpassword123'}
        response = self.client.put('/api/users/1/password', json=payload, headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})


class TestLoginFlows(unittest.TestCase):
    """Covers the username+password login flows described in the auth model doc:
    unknown username -> error, wrong password -> error, disabled account -> error,
    and a correct login actually succeeding.
    """

    def setUp(self):
        self.client = TestClient(app)
        import bcrypt
        self.password_hash = bcrypt.hashpw(b'correct-password', bcrypt.gensalt()).decode('utf-8')

    @patch('services.music_manager.routers.users.get_db_connection')
    def test_login_unknown_username_returns_generic_error(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        response = self.client.post('/api/auth/login', json={'username': 'ghost', 'password': 'whatever'})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['detail'], 'Invalid username or password')

    @patch('services.music_manager.routers.users.get_db_connection')
    def test_login_google_only_account_has_no_password_returns_generic_error(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            'id': 3, 'username': 'google-user', 'password_hash': None, 'enabled': True,
        }

        response = self.client.post('/api/auth/login', json={'username': 'google-user', 'password': 'whatever'})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['detail'], 'Invalid username or password')

    @patch('services.music_manager.routers.users.get_db_connection')
    def test_login_disabled_account_is_rejected(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            'id': 4, 'username': 'disabled-user', 'password_hash': self.password_hash, 'enabled': False,
        }

        response = self.client.post('/api/auth/login', json={'username': 'disabled-user', 'password': 'correct-password'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['detail'], 'Account disabled')

    @patch('services.music_manager.routers.users.get_db_connection')
    def test_login_wrong_password_returns_generic_error(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            'id': 5, 'username': 'plain-user', 'password_hash': self.password_hash, 'enabled': True,
        }

        response = self.client.post('/api/auth/login', json={'username': 'plain-user', 'password': 'wrong-password'})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['detail'], 'Invalid username or password')

    @patch('services.music_manager.routers.users.get_db_connection')
    def test_login_correct_credentials_issue_tokens(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        user_row = {
            'id': 6, 'username': 'plain-user', 'display_name': 'Plain User', 'email': None,
            'avatar_url': None, 'server_user_id': None, 'password_hash': self.password_hash,
            'api_key': 'existing-api-key', 'role_id': 2, 'enabled': True,
        }
        # 1) user lookup, 2) role-name lookup (inside build_auth_user)
        mock_cursor.fetchone.side_effect = [user_row, {'name': 'user'}]
        mock_cursor.fetchall.return_value = []

        response = self.client.post('/api/auth/login', json={'username': 'plain-user', 'password': 'correct-password'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['api_key'], 'existing-api-key')
        self.assertIn('refresh_token', body)
        self.assertEqual(body['username'], 'plain-user')
        insert_calls = [c for c in mock_cursor.execute.call_args_list if 'INSERT INTO user_refresh_tokens' in c[0][0]]
        self.assertEqual(len(insert_calls), 1, 'a successful login must issue a refresh token')


if __name__ == '__main__':
    unittest.main()
