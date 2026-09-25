import os
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('mutagen', 'markdown', 'pymysql', 'dbutils', 'DatabaseConnector')

# Mock external modules to avoid import errors, but only when they aren't already
# provided by services/tests/mock_base.py (loaded once for the whole pytest session
# via services/conftest.py) or by the real installed packages -- blindly overwriting
# sys.modules here would clobber the properly-constructed mutagen mock classes with
# a plain MagicMock, breaking isinstance() checks in any importer/downloader test
# that runs afterward in the same pytest session.


import services.music_manager.routers.users
from services.music_manager.api_key import resolve_system_api_key

services.music_manager.routers.users.run_lms_db_sync = lambda: None
import services.music_manager.database

services.music_manager.database.get_db_connection = MagicMock(return_value=None)

from fastapi.testclient import TestClient

from services.music_manager.main import app


class TestUsers(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.api_key = resolve_system_api_key()

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
            'id': 3,
            'username': 'google-user',
            'password_hash': None,
            'enabled': True,
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
            'id': 4,
            'username': 'disabled-user',
            'password_hash': self.password_hash,
            'enabled': False,
        }

        response = self.client.post(
            '/api/auth/login', json={'username': 'disabled-user', 'password': 'correct-password'}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['detail'], 'Account disabled')

    @patch('services.music_manager.routers.users.get_db_connection')
    def test_login_wrong_password_returns_generic_error(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            'id': 5,
            'username': 'plain-user',
            'password_hash': self.password_hash,
            'enabled': True,
        }

        response = self.client.post('/api/auth/login', json={'username': 'plain-user', 'password': 'wrong-password'})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['detail'], 'Invalid username or password')

    @patch('services.music_manager.routers.users.get_db_connection')
    def test_login_google_only_account_can_authenticate_with_its_api_key(self, mock_get_db):
        """A Google-only account has no plaintext password the frontend can ever learn (see
        AuthOverlay.svelte's handleGoogleResponse), so it must be able to log in (and, via LMS's
        MusicManagementPasswordService, authenticate Subsonic calls) using its own `api_key` as
        the password -- this is what makes Google-authenticated users actually see their music.
        """
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        user_row = {
            'id': 7,
            'username': 'google-user',
            'display_name': 'Google User',
            'email': 'g@example.com',
            'avatar_url': None,
            'server_user_id': None,
            'password_hash': None,
            'api_key': 'the-api-key',
            'role_id': 2,
            'enabled': True,
        }
        mock_cursor.fetchone.side_effect = [user_row, {'name': 'user'}]
        mock_cursor.fetchall.return_value = []

        response = self.client.post('/api/auth/login', json={'username': 'google-user', 'password': 'the-api-key'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['api_key'], 'the-api-key')
        self.assertEqual(body['user']['username'], 'google-user')

    @patch('services.music_manager.routers.users.get_db_connection')
    def test_login_google_only_account_rejects_wrong_password(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            'id': 8,
            'username': 'google-user-2',
            'password_hash': None,
            'api_key': 'the-real-api-key',
            'enabled': True,
        }

        response = self.client.post(
            '/api/auth/login', json={'username': 'google-user-2', 'password': 'not-the-api-key'}
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['detail'], 'Invalid username or password')

    @patch('services.music_manager.routers.users.get_db_connection')
    def test_login_correct_credentials_issue_tokens(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        user_row = {
            'id': 6,
            'username': 'plain-user',
            'display_name': 'Plain User',
            'email': None,
            'avatar_url': None,
            'server_user_id': None,
            'password_hash': self.password_hash,
            'api_key': 'existing-api-key',
            'role_id': 2,
            'enabled': True,
        }
        # 1) user lookup, 2) role-name lookup (inside build_auth_user)
        mock_cursor.fetchone.side_effect = [user_row, {'name': 'user'}]
        mock_cursor.fetchall.return_value = []

        response = self.client.post('/api/auth/login', json={'username': 'plain-user', 'password': 'correct-password'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['api_key'], 'existing-api-key')
        self.assertIn('refresh_token', body)
        self.assertEqual(body['user']['username'], 'plain-user')
        insert_calls = [c for c in mock_cursor.execute.call_args_list if 'INSERT INTO user_refresh_tokens' in c[0][0]]
        self.assertEqual(len(insert_calls), 1, 'a successful login must issue a refresh token')

    def _login_as(self, mock_get_db, row, password):
        """POST a login for `row` with `password` against a mocked users table."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = row
        return self.client.post('/api/auth/login', json={'username': row['username'], 'password': password})

    @patch('services.music_manager.routers.users.get_db_connection')
    def test_login_with_a_non_ascii_password_is_rejected_not_a_crash(self, mock_get_db):
        # compare_digest raises TypeError on a non-ASCII str: this was a 500, and the rate
        # limiter, which counts rejections, never saw it.
        row = {'id': 9, 'username': 'plain-user', 'password_hash': None, 'api_key': 'the-api-key', 'enabled': True}
        response = self._login_as(mock_get_db, row, 'wachtwoord-\u00e9\u00e8\U0001f3b5')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['detail'], 'Invalid username or password')

    @patch('services.music_manager.routers.users.get_db_connection')
    def test_login_with_a_password_over_bcrypts_limit_is_rejected_not_a_crash(self, mock_get_db):
        row = {'id': 10, 'username': 'plain-user', 'password_hash': self.password_hash, 'enabled': True}
        response = self._login_as(mock_get_db, row, 'x' * 200)
        self.assertEqual(response.status_code, 401)

    @patch('services.music_manager.routers.users.bcrypt.checkpw', side_effect=ValueError('password too long'))
    @patch('services.music_manager.routers.users.get_db_connection')
    def test_login_treats_a_bcrypt_value_error_as_a_wrong_password(self, mock_get_db, _mock_checkpw):
        # bcrypt 5 raises for a password over 72 bytes instead of truncating it.
        row = {'id': 11, 'username': 'plain-user', 'password_hash': self.password_hash, 'enabled': True}
        response = self._login_as(mock_get_db, row, 'x' * 100)
        self.assertEqual(response.status_code, 401)


class TestPasswordMatches(unittest.TestCase):
    """The comparison behind login, which must answer yes or no for any input."""

    def setUp(self):
        import bcrypt

        self.password_hash = bcrypt.hashpw('p\u00e4ssw\u00f6rd'.encode(), bcrypt.gensalt()).decode('utf-8')

    def test_a_non_ascii_password_matches_its_own_hash(self):
        user = {'password_hash': self.password_hash, 'api_key': None}
        self.assertTrue(users_router_password_matches('p\u00e4ssw\u00f6rd', user))
        self.assertFalse(users_router_password_matches('passwort', user))

    def test_a_non_ascii_api_key_candidate_is_compared_as_bytes(self):
        user = {'password_hash': None, 'api_key': 'abc123'}
        self.assertFalse(users_router_password_matches('\u00e9\u00e9\u00e9', user))
        self.assertTrue(users_router_password_matches('abc123', user))

    def test_a_malformed_stored_hash_is_no_match(self):
        self.assertFalse(users_router_password_matches('anything', {'password_hash': 'not-a-bcrypt-hash'}))

    def test_an_account_without_credentials_never_matches(self):
        self.assertFalse(users_router_password_matches('', {'password_hash': None, 'api_key': None}))


def users_router_password_matches(password, user):
    """Indirection so the tests read as sentences about the helper under test."""
    return services.music_manager.routers.users.password_matches(password, user)


class TestServerDbSyncNeverDropsUserTable(unittest.TestCase):
    """Regression test for docs/bug-reports/005-lms-user-table-corruption.md: sync_single_server_db
    used to run `DROP TABLE IF EXISTS user` against the player's on-disk SQLite database. That
    table is real, persistent, non-volatile state the running player process reads/writes
    directly (unlike auth_token/ui_state, which live in its own private in-memory "volatile"
    schema and are never touched by this on-disk connection at all) -- dropping it caused a
    production outage. This must never happen again, regardless of table contents/schema.
    """

    def test_sync_single_server_db_does_not_drop_or_touch_user_table(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = os.path.join(tmp_dir, 'lms.db')
            conn = sqlite3.connect(db_path)
            conn.execute(
                "CREATE TABLE user (id INTEGER PRIMARY KEY, login_name TEXT, password_salt TEXT NOT NULL, password_hash TEXT NOT NULL)"
            )
            conn.execute(
                "INSERT INTO user (id, login_name, password_salt, password_hash) VALUES (1, 'user', 'salt', 'hash')"
            )
            conn.commit()
            conn.close()

            mock_muma_conn = MagicMock()
            mock_muma_cursor = MagicMock()
            mock_muma_conn.cursor.return_value.__enter__.return_value = mock_muma_cursor
            mock_muma_cursor.fetchall.return_value = []

            with patch('services.music_manager.routers.artist_images.sync_artist_images_to_server', MagicMock()):
                services.music_manager.routers.users.sync_single_server_db(mock_muma_conn, db_path, 'server-stable')

            check_conn = sqlite3.connect(db_path)
            cur = check_conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user'")
            self.assertIsNotNone(cur.fetchone(), 'the "user" table must still exist after sync')
            cur.execute('PRAGMA table_info(user)')
            columns = {row[1] for row in cur.fetchall()}
            self.assertIn('password_salt', columns)
            self.assertIn('password_hash', columns)
            cur.execute('SELECT login_name FROM user WHERE id = 1')
            self.assertEqual(cur.fetchone()[0], 'user', 'existing user rows must be left untouched')
            check_conn.close()


if __name__ == '__main__':
    unittest.main()
