"""GET /api/auth/subsonic-token and the lms.db logic behind it (bug report 103).

The lms.db side runs against real SQLite files carrying the columns LMS's `user` and `auth_token`
tables have, so the SQL is exercised for real; only the MuMa account lookup (`verify_token`) is
patched, since that is MariaDB and is covered by tests/integration/test_router_sql.py.
"""

import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector')

import services.music_manager.routers.users as users_router
from services.music_manager import subsonic_token
from services.music_manager.api_key import resolve_system_api_key

users_router.run_lms_db_sync = lambda only_sources=None: None

from fastapi.testclient import TestClient

from services.music_manager.main import app
from services.music_manager.rate_limit import auth_limiter, reset_limiters


def make_lms_db(path, users=(), tokens=()):
    """An lms.db with LMS's `user` and `auth_token` columns (auth_token as migrateFromV115 makes it).

    `users` holds (id, login_name, muma_id) and `tokens` (user_id, value) rows.
    """
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE user (id INTEGER PRIMARY KEY, login_name TEXT, muma_id INTEGER, disabled INTEGER)')
    conn.execute(
        'CREATE TABLE auth_token (id INTEGER PRIMARY KEY AUTOINCREMENT, version INTEGER NOT NULL DEFAULT 0, '
        "domain TEXT NOT NULL DEFAULT '', value TEXT NOT NULL DEFAULT '', expiry DATETIME, "
        'use_count INTEGER NOT NULL DEFAULT 0, last_used TEXT, max_use_count INTEGER, user_id INTEGER)'
    )
    conn.execute('CREATE UNIQUE INDEX auth_token_domain_value_unique_idx ON auth_token(domain, value)')
    for user_id, login, muma_id in users:
        conn.execute(
            'INSERT INTO user (id, login_name, muma_id, disabled) VALUES (?, ?, ?, 0)', (user_id, login, muma_id)
        )
    for user_id, value in tokens:
        conn.execute("INSERT INTO auth_token (domain, value, user_id) VALUES ('subsonic', ?, ?)", (value, user_id))
    conn.commit()
    conn.close()


def tokens_of(path, user_id):
    """Every Subsonic token value stored for `user_id`, oldest first."""
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute(
            "SELECT value FROM auth_token WHERE domain = 'subsonic' AND user_id = ? ORDER BY id", (user_id,)
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


class OwnSubsonicTokenTest(unittest.TestCase):
    """`subsonic_token.own_subsonic_token` against real SQLite files."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, 'lms.db')

    def test_an_existing_token_is_returned_and_nothing_is_written(self):
        make_lms_db(self.path, users=[(1, 'user', 7)], tokens=[(1, 'an-admin-issued-token-1234')])

        result = subsonic_token.own_subsonic_token([(self.path, 'server-direct')], 7, 'user')

        self.assertEqual(result.token, 'an-admin-issued-token-1234')
        self.assertEqual(result.username, 'user')
        self.assertFalse(result.issued)
        self.assertEqual(tokens_of(self.path, 1), ['an-admin-issued-token-1234'])

    def test_a_user_without_a_token_gets_one_that_lms_accepts(self):
        make_lms_db(self.path, users=[(1, 'user', 7)])

        result = subsonic_token.own_subsonic_token([(self.path, 'server-direct')], 7, 'user')

        self.assertTrue(result.issued)
        self.assertGreaterEqual(len(result.token), subsonic_token.MIN_TOKEN_LENGTH)
        self.assertEqual(tokens_of(self.path, 1), [result.token])
        # The second call finds it rather than issuing another.
        again = subsonic_token.own_subsonic_token([(self.path, 'server-direct')], 7, 'user')
        self.assertEqual(again.token, result.token)
        self.assertFalse(again.issued)
        self.assertEqual(tokens_of(self.path, 1), [result.token])

    def test_the_row_has_the_shape_lms_writes(self):
        make_lms_db(self.path, users=[(1, 'user', 7)])

        subsonic_token.own_subsonic_token([(self.path, 'server-direct')], 7, 'user')

        conn = sqlite3.connect(self.path)
        row = conn.execute(
            'SELECT version, domain, expiry, use_count, last_used, max_use_count FROM auth_token'
        ).fetchone()
        conn.close()
        self.assertEqual(row, (0, 'subsonic', None, 0, None, None))

    def test_muma_id_decides_over_the_login_name(self):
        make_lms_db(
            self.path,
            users=[(1, 'user', 99), (2, 'someone-else', 7)],
            tokens=[(1, 'the-wrong-users-token-x'), (2, 'the-callers-own-token-y')],
        )

        result = subsonic_token.own_subsonic_token([(self.path, 'server-direct')], 7, 'user')

        self.assertEqual(result.token, 'the-callers-own-token-y')
        self.assertEqual(result.username, 'someone-else')

    def test_the_exact_spelling_wins_over_a_case_fork(self):
        # Bug report 074 left a second LMS user for a case variant; the account's own spelling wins.
        make_lms_db(
            self.path,
            users=[(1, 'User', None), (2, 'user', None)],
            tokens=[(1, 'the-forked-users-token-1'), (2, 'the-real-users-token-22')],
        )

        result = subsonic_token.own_subsonic_token([(self.path, 'server-direct')], 7, 'user')

        self.assertEqual(result.token, 'the-real-users-token-22')
        self.assertEqual(result.username, 'user')

    def test_a_case_variant_is_found_when_it_is_the_only_one(self):
        make_lms_db(self.path, users=[(1, 'User', None)])

        result = subsonic_token.own_subsonic_token([(self.path, 'server-direct')], None, 'user')

        self.assertEqual(result.username, 'User')

    def test_a_too_short_token_is_not_handed_out(self):
        make_lms_db(self.path, users=[(1, 'user', 7)], tokens=[(1, 'short')])

        result = subsonic_token.own_subsonic_token([(self.path, 'server-direct')], 7, 'user')

        self.assertNotEqual(result.token, 'short')
        self.assertEqual(tokens_of(self.path, 1), ['short', result.token])

    def test_an_unknown_account_is_not_on_the_server(self):
        make_lms_db(self.path, users=[(1, 'someone', 3)])

        with self.assertRaises(subsonic_token.NotOnServer):
            subsonic_token.own_subsonic_token([(self.path, 'server-direct')], 7, 'user')
        self.assertEqual(tokens_of(self.path, 1), [])

    def test_no_database_at_all(self):
        with self.assertRaises(subsonic_token.NoServerDatabase):
            subsonic_token.own_subsonic_token([], 7, 'user')

    def test_an_unreadable_only_database_raises(self):
        with open(self.path, 'w', encoding='utf-8') as handle:
            handle.write('not a database')

        with self.assertRaises(sqlite3.Error):
            subsonic_token.own_subsonic_token([(self.path, 'server-direct')], 7, 'user')

    def test_the_token_is_copied_to_a_second_server_that_lacks_it(self):
        second = os.path.join(self.dir.name, 'b.db')
        make_lms_db(self.path, users=[(1, 'user', 7)])
        make_lms_db(second, users=[(5, 'user', 7)], tokens=[(5, 'the-token-on-server-two')])

        result = subsonic_token.own_subsonic_token([(self.path, 'server-direct'), (second, 'server-b')], 7, 'user')

        self.assertEqual(result.token, 'the-token-on-server-two')
        self.assertEqual(tokens_of(self.path, 1), ['the-token-on-server-two'])
        self.assertEqual(tokens_of(second, 5), ['the-token-on-server-two'])

    def test_a_broken_second_server_does_not_stop_the_first(self):
        broken = os.path.join(self.dir.name, 'broken.db')
        with open(broken, 'w', encoding='utf-8') as handle:
            handle.write('not a database')
        make_lms_db(self.path, users=[(1, 'user', 7)])

        result = subsonic_token.own_subsonic_token([(self.path, 'server-direct'), (broken, 'server-x')], 7, 'user')

        self.assertEqual(tokens_of(self.path, 1), [result.token])


class SubsonicTokenRouteTest(unittest.TestCase):
    """The route: who may call it, and what each failure answers."""

    def setUp(self):
        reset_limiters()
        self.addCleanup(reset_limiters)
        self.client = TestClient(app)
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, 'lms.db')

    def user_key(self, user_id=7, username='user'):
        """Patches the key lookup so `user-key` resolves to this account."""
        answer = {'status': 'ok', 'type': 'user', 'user': {'id': user_id, 'username': username}}
        patcher = patch.object(users_router, 'verify_token', return_value=answer)
        patcher.start()
        self.addCleanup(patcher.stop)

    def targets(self, targets):
        patcher = patch.object(users_router, 'lms_db_targets', return_value=targets)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_user_gets_their_own_token(self):
        make_lms_db(self.path, users=[(1, 'user', 7), (2, 'other', 8)], tokens=[(2, 'the-other-users-token-zz')])
        self.user_key()
        self.targets([(self.path, 'server-direct')])

        response = self.client.get('/api/auth/subsonic-token', headers={'x-api-key': 'user-key'})

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['username'], 'user')
        self.assertEqual(tokens_of(self.path, 1), [body['token']])
        self.assertNotEqual(body['token'], 'the-other-users-token-zz')

    def test_no_request_parameter_can_name_another_user(self):
        make_lms_db(self.path, users=[(1, 'user', 7), (2, 'other', 8)], tokens=[(2, 'the-other-users-token-zz')])
        self.user_key()
        self.targets([(self.path, 'server-direct')])

        response = self.client.get(
            '/api/auth/subsonic-token?username=other&user_id=8', headers={'x-api-key': 'user-key'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.json()['token'], 'the-other-users-token-zz')

    def test_no_key_is_401(self):
        response = self.client.get('/api/auth/subsonic-token')
        self.assertEqual(response.status_code, 401)

    def test_a_system_key_is_403(self):
        response = self.client.get('/api/auth/subsonic-token', headers={'x-api-key': resolve_system_api_key()})
        self.assertEqual(response.status_code, 403)

    def test_wrong_keys_are_rate_limited(self):
        attempts = auth_limiter.attempts
        codes = [self.client.get('/api/auth/subsonic-token').status_code for _ in range(attempts + 2)]
        self.assertEqual(set(codes[:attempts]), {401})
        self.assertEqual(codes[-1], 429)

    def test_an_account_not_on_the_server_is_404(self):
        make_lms_db(self.path, users=[(1, 'someone', 3)])
        self.user_key()
        self.targets([(self.path, 'server-direct')])

        response = self.client.get('/api/auth/subsonic-token', headers={'x-api-key': 'user-key'})

        self.assertEqual(response.status_code, 404)

    def test_no_server_database_is_503(self):
        self.user_key()
        self.targets([])

        response = self.client.get('/api/auth/subsonic-token', headers={'x-api-key': 'user-key'})

        self.assertEqual(response.status_code, 503)

    def test_a_broken_server_database_is_503_and_the_token_is_not_logged(self):
        with open(self.path, 'w', encoding='utf-8') as handle:
            handle.write('not a database')
        self.user_key()
        self.targets([(self.path, 'server-direct')])

        response = self.client.get('/api/auth/subsonic-token', headers={'x-api-key': 'user-key'})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers.get('retry-after'), '5')

    def test_issuing_logs_the_user_but_never_the_token(self):
        make_lms_db(self.path, users=[(1, 'user', 7)])
        self.user_key()
        self.targets([(self.path, 'server-direct')])

        with self.assertLogs('music-manager.subsonic-token', level='INFO') as logs:
            response = self.client.get('/api/auth/subsonic-token', headers={'x-api-key': 'user-key'})

        token = response.json()['token']
        self.assertTrue(any('user' in line for line in logs.output))
        self.assertFalse(any(token in line for line in logs.output))


if __name__ == '__main__':
    unittest.main()
