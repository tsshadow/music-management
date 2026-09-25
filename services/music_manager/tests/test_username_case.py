"""One identity per account, whatever case its name is typed in.

docs/bug-reports/074-login-case-forks-user-identity.md: "Teun" typed for the account
"user" was accepted by the login (MariaDB compares case-insensitively), travelled on as
the typed spelling, made LMS create a second user, and came back as scrobbles stored
under the variant. Account names are case-insensitive everywhere now, and whatever is
stored or compared uses the spelling in `users.username`.
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.easyid3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())

import bcrypt

import services.music_manager.routers.users as users_router

users_router.run_lms_db_sync = lambda only_sources=None: None

from fastapi.testclient import TestClient

from services.music_manager import identity
from services.music_manager.api_key import resolve_system_api_key
from services.music_manager.main import app
from services.music_manager.routers import feeds as feeds_router
from services.music_manager.routers import rating as rating_router
from services.music_manager.routers import scrobbler as scrobbler_router
from services.music_manager.routers import user_requests as user_requests_router
from services.music_manager.tests.scripted_cursor import ScriptedCursor

SYSTEM = {'x-api-key': resolve_system_api_key()}
ACCOUNTS = [{'id': 1, 'username': 'user'}]
# What `LOWER(username) = LOWER(%s)` finds for any spelling of "user".
CANONICAL_LOOKUP = ('SELECT username FROM users WHERE LOWER(username) = LOWER(%s)', None, {'username': 'user'})


def user_auth(username):
    """A verify_token result for an ordinary account."""
    return {
        'status': 'ok',
        'type': 'user',
        'user': {'id': 1, 'username': username, 'role_name': 'user', 'permissions': []},
    }


def connection(cursor):
    """A connection whose cursor context manager hands out `cursor`."""
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    conn.cursor.return_value.__exit__.return_value = False
    return conn


def statement_for(cursor, fragment):
    """The first executed statement containing `fragment`, with its parameters."""
    for sql, params in cursor.executed:
        if fragment in sql:
            return sql, params
    raise AssertionError(f'no statement containing {fragment!r} in {cursor.executed!r}')


class IdentityHelpersTest(unittest.TestCase):
    """services/music_manager/identity.py, on its own."""

    def test_same_username_ignores_case_and_never_matches_blank(self):
        self.assertTrue(identity.same_username('Teun', 'user'))
        self.assertTrue(identity.same_username('TEUN', 'user'))
        self.assertFalse(identity.same_username('user', 'teun2'))
        self.assertFalse(identity.same_username('', ''))
        self.assertFalse(identity.same_username(None, 'user'))

    def test_canonical_username_returns_the_accounts_own_spelling(self):
        cursor = ScriptedCursor([CANONICAL_LOOKUP])
        self.assertEqual(identity.canonical_username(cursor, 'Teun'), 'user')
        self.assertEqual(cursor.executed[0][1], ('Teun',))

    def test_a_name_no_account_carries_comes_back_unchanged(self):
        self.assertEqual(identity.canonical_username(ScriptedCursor(), 'lms-only'), 'lms-only')

    def test_username_taken_sees_a_case_variant(self):
        cursor = ScriptedCursor([('SELECT id FROM users WHERE LOWER(username) = LOWER(%s)', None, {'id': 1})])
        self.assertTrue(identity.username_taken(cursor, 'TEUN'))
        self.assertFalse(identity.username_taken(ScriptedCursor(), 'anna'))

    def test_account_spellings_map_every_case_to_the_account(self):
        cursor = ScriptedCursor([('SELECT username FROM users', None, ACCOUNTS)])
        spellings = identity.account_spellings(cursor)
        self.assertEqual(identity.spelled(spellings, 'Teun'), 'user')
        self.assertEqual(identity.spelled(spellings, 'anna'), 'anna')


class LoginCaseTest(unittest.TestCase):
    """POST /api/auth/login with a case variant of the account name."""

    def setUp(self):
        self.client = TestClient(app)
        self.cursor = MagicMock()
        patcher = patch.object(users_router, 'get_db_connection', return_value=connection(self.cursor))
        patcher.start()
        self.addCleanup(patcher.stop)
        roles = patch.object(users_router.rbac, 'get_permissions_for_role', return_value=set())
        roles.start()
        self.addCleanup(roles.stop)

    def test_a_case_variant_login_returns_the_canonical_username(self):
        self.cursor.fetchone.return_value = {
            'id': 1,
            'username': 'user',
            'password_hash': bcrypt.hashpw(b'pw', bcrypt.gensalt(4)).decode(),
            'api_key': 'own-key',
            'enabled': True,
            'role_id': None,
        }

        response = self.client.post('/api/auth/login', json={'username': 'Teun', 'password': 'pw'})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['user']['username'], 'user')
        lookup_sql, lookup_params = self.cursor.execute.call_args_list[0].args
        self.assertIn('LOWER(username) = LOWER(%s)', lookup_sql)
        self.assertEqual(lookup_params, ('Teun',))

    def test_the_rate_limit_counts_every_case_of_a_name_as_one_account(self):
        with patch.object(users_router, 'auth_attempt') as attempt:
            attempt.return_value.__enter__.return_value = None
            attempt.return_value.__exit__.return_value = False
            self.cursor.fetchone.return_value = None
            self.client.post('/api/auth/login', json={'username': 'TeUn', 'password': 'pw'})
        self.assertEqual(attempt.call_args.args[1], 'user')


class AccountCreationCaseTest(unittest.TestCase):
    """A new account may not take a name that differs only in case from an existing one."""

    def setUp(self):
        self.client = TestClient(app)

    def test_create_user_refuses_a_case_variant(self):
        cursor = ScriptedCursor([('SELECT id FROM users WHERE LOWER(username) = LOWER(%s)', None, {'id': 1})])
        with patch.object(users_router, 'get_db_connection', return_value=connection(cursor)):
            response = self.client.post('/api/users', headers=SYSTEM, json={'username': 'Teun', 'password': 'pw'})
        self.assertEqual(response.status_code, 409)
        self.assertFalse([sql for sql, _ in cursor.executed if 'INSERT INTO users' in sql])

    def test_create_user_accepts_a_new_name(self):
        cursor = ScriptedCursor(lastrowid=2)
        with (
            patch.object(users_router, 'get_db_connection', return_value=connection(cursor)),
            patch.object(users_router.rbac, 'get_role_by_name', return_value={'id': 2}),
        ):
            response = self.client.post('/api/users', headers=SYSTEM, json={'username': 'anna'})
        self.assertEqual(response.status_code, 200, response.text)
        statement_for(cursor, 'INSERT INTO users')

    def test_approving_a_google_request_refuses_a_case_variant_of_an_existing_name(self):
        request_row = {
            'id': 9,
            'status': 'pending',
            'email': 'Teun@Example.com',
            'google_subject': 'sub-123456789012',
            'display_name': None,
            'avatar_url': None,
        }
        cursor = ScriptedCursor(
            [
                ('SELECT * FROM user_requests WHERE id = %s', None, request_row),
                ('SELECT id FROM users WHERE LOWER(username) = LOWER(%s)', None, {'id': 1}),
            ]
        )
        with (
            patch.object(user_requests_router, 'get_db_connection', return_value=connection(cursor)),
            patch.object(user_requests_router.rbac, 'get_role_by_name', return_value={'id': 2}),
        ):
            response = self.client.post('/api/user-requests/9/approve', headers=SYSTEM, json={})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertFalse([sql for sql, _ in cursor.executed if 'INSERT INTO users' in sql])


class ScrobbleCaseTest(unittest.TestCase):
    """POST /api/scrobble/event stores the account's own spelling, never the body's."""

    EVENT = {'artist_name': 'Angerfist', 'track_title': 'Raise & Revolt'}

    def setUp(self):
        self.client = TestClient(app)
        self.cursor = ScriptedCursor([CANONICAL_LOOKUP])
        patcher = patch.object(scrobbler_router, 'get_db_connection', return_value=connection(self.cursor))
        patcher.start()
        self.addCleanup(patcher.stop)
        finder = patch.object(scrobbler_router, 'find_track', return_value=None)
        finder.start()
        self.addCleanup(finder.stop)

    def stored_username(self):
        _sql, params = statement_for(self.cursor, 'INSERT INTO scrobble_unmatched_listens')
        return params[6]

    def test_a_user_key_with_a_case_variant_stores_its_own_spelling(self):
        with patch.object(users_router, 'verify_token', return_value=user_auth('user')):
            response = self.client.post(
                '/api/scrobble/event', headers={'x-api-key': 'user-key'}, json={**self.EVENT, 'username': 'Teun'}
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.stored_username(), 'user')

    def test_the_system_key_relaying_a_case_variant_stores_the_canonical_spelling(self):
        # What LMS did for the fork it created: the system key, naming its own local user.
        response = self.client.post('/api/scrobble/event', headers=SYSTEM, json={**self.EVENT, 'username': 'Teun'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.stored_username(), 'user')

    def test_another_accounts_name_is_still_refused(self):
        # !938's self-only rule survives the case-insensitive comparison.
        with patch.object(users_router, 'verify_token', return_value=user_auth('user')):
            response = self.client.post(
                '/api/scrobble/event', headers={'x-api-key': 'user-key'}, json={**self.EVENT, 'username': 'anna'}
            )
        self.assertEqual(response.status_code, 403)


class RatingWebhookCaseTest(unittest.TestCase):
    """The LMS rating webhook stores the account's own spelling."""

    def test_a_case_variant_from_lms_is_stored_canonically(self):
        cursor = ScriptedCursor([CANONICAL_LOOKUP])
        with patch.object(rating_router, 'get_db_connection', return_value=connection(cursor)):
            response = TestClient(app).post(
                '/api/rating/server-event',
                headers=SYSTEM,
                json={
                    'event': 'rating_changed',
                    'object_type': 'track',
                    'object_id': 'uid-1',
                    'username': 'Teun',
                    'rating': 5,
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        _sql, params = statement_for(cursor, 'INSERT INTO rating_tracks')
        self.assertEqual(params[2], 'user')

    def test_reading_your_own_ratings_ignores_case(self):
        cursor = ScriptedCursor()
        with (
            patch.object(rating_router, 'get_db_connection', return_value=connection(cursor)),
            patch.object(users_router, 'verify_token', return_value=user_auth('user')),
        ):
            response = TestClient(app).get('/api/rating/ratings/Teun', headers={'x-api-key': 'user-key'})
        self.assertEqual(response.status_code, 200, response.text)


class FeedsCaseTest(unittest.TestCase):
    """The system key's `username` is resolved to the account's spelling: the picks are seeded on it."""

    def test_the_system_key_gets_the_canonical_spelling(self):
        cursor = ScriptedCursor([CANONICAL_LOOKUP])
        with patch.object(feeds_router, 'get_db_connection', return_value=connection(cursor)):
            self.assertEqual(feeds_router._resolve_username({'type': 'system'}, 'Teun'), 'user')

    def test_a_user_key_keeps_its_own_account(self):
        self.assertEqual(feeds_router._resolve_username(user_auth('user'), 'Anna'), 'user')


if __name__ == '__main__':
    unittest.main()
