"""The authentication gaps left after the September 2026 audit.

See docs/bug-reports/052-the-last-admin-could-demote-itself.md. One class per gap:
the last-admin guard on demote/disable/delete, the setup race, username enumeration
through login timing, the key checks that turned a database outage into "Invalid API
key", a scrobble written under another account's name, and the refresh-token table
that only ever grew.
"""

import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.easyid3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())

import bcrypt

import services.music_manager.routers.users as users_router
from services.music_manager.api_key import resolve_system_api_key

users_router.run_lms_db_sync = lambda only_sources=None: None

from fastapi.testclient import TestClient

from services.music_manager import events_retention, rbac
from services.music_manager.main import app
from services.music_manager.routers import library as library_router
from services.music_manager.routers import rating as rating_router
from services.music_manager.routers import scrobbler as scrobbler_router

SYSTEM_KEY = resolve_system_api_key()
SYSTEM = {'x-api-key': SYSTEM_KEY}


def auth_for(user_id, username, role_name, permissions):
    """A verify_token result for an account with the given role and permissions."""
    return {
        'status': 'ok',
        'type': 'user',
        'user': {'id': user_id, 'username': username, 'role_name': role_name, 'permissions': sorted(permissions)},
    }


LISTENER = auth_for(5, 'listener', 'user', rbac.USER_ROLE_PERMISSIONS)
ADMIN = auth_for(1, 'root', 'admin', {name for name, _ in rbac.PERMISSIONS})


def roles_by_name(_cursor, name):
    """rbac.get_role_by_name against a roles table holding admin (1) and user (2)."""
    return {'admin': {'id': 1, 'name': 'admin'}, 'user': {'id': 2, 'name': 'user'}}.get(name)


class MockedDatabaseTestCase(unittest.TestCase):
    """A TestClient with users.get_db_connection answering from a MagicMock cursor."""

    def setUp(self):
        self.client = TestClient(app)
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = self.cursor
        self.conn.cursor.return_value.__exit__.return_value = False
        patcher = patch.object(users_router, 'get_db_connection', return_value=self.conn)
        patcher.start()
        self.addCleanup(patcher.stop)

    def statements(self):
        """Every SQL statement the endpoint executed, in order."""
        return [call.args[0] for call in self.cursor.execute.call_args_list]

    def writes(self, fragment):
        """The executed statements containing `fragment`."""
        return [s for s in self.statements() if fragment in s]


class LastAdminGuardTest(MockedDatabaseTestCase):
    """Demote, disable and delete all refuse to remove the last enabled admin."""

    def setUp(self):
        super().setUp()
        for patcher in (
            patch.object(users_router.rbac, 'get_role_by_name', side_effect=roles_by_name),
            patch.object(users_router.rbac, 'record_audit_event'),
            patch.object(users_router, 'notify_server_sync_users'),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def arrange(self, target, other_enabled_admins):
        """The target row, then the count of other enabled admins."""
        self.cursor.fetchone.side_effect = [target, {'cnt': other_enabled_admins}]

    ROOT = {'id': 1, 'username': 'root', 'role_id': 1, 'enabled': True}

    def test_the_last_enabled_admin_cannot_be_demoted(self):
        self.arrange(self.ROOT, 0)
        response = self.client.put('/api/users/1/role', headers=SYSTEM, json={'role': 'user'})
        self.assertEqual(response.status_code, 409)
        self.assertIn('beheerder', response.json()['detail'])
        self.assertEqual(self.writes('UPDATE users'), [])
        self.conn.commit.assert_not_called()

    def test_one_of_two_admins_can_be_demoted(self):
        self.arrange(self.ROOT, 1)
        response = self.client.put('/api/users/1/role', headers=SYSTEM, json={'role': 'user'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.writes('UPDATE users SET role_id')), 1)

    def test_promoting_to_admin_needs_no_check(self):
        response = self.client.put('/api/users/4/role', headers=SYSTEM, json={'role': 'admin'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.writes('COUNT(*)'), [])

    def test_the_last_enabled_admin_cannot_be_disabled(self):
        self.arrange(self.ROOT, 0)
        response = self.client.post('/api/users/1/disable', headers=SYSTEM)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.writes('enabled = FALSE'), [])

    def test_one_of_two_admins_can_be_disabled(self):
        self.arrange(self.ROOT, 1)
        response = self.client.post('/api/users/1/disable', headers=SYSTEM)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.writes('enabled = FALSE')), 1)

    def test_a_plain_user_is_disabled_without_counting_admins(self):
        self.cursor.fetchone.side_effect = [{'id': 4, 'username': 'user', 'role_id': 2, 'enabled': True}]
        response = self.client.post('/api/users/4/disable', headers=SYSTEM)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.writes('COUNT(*)'), [])

    def test_an_already_disabled_admin_is_not_the_one_the_guard_protects(self):
        self.cursor.fetchone.side_effect = [{**self.ROOT, 'enabled': 0}]
        response = self.client.post('/api/users/1/disable', headers=SYSTEM)
        self.assertEqual(response.status_code, 200)

    def test_disabling_an_unknown_account_is_a_not_found(self):
        self.cursor.fetchone.side_effect = [None]
        response = self.client.post('/api/users/99/disable', headers=SYSTEM)
        self.assertEqual(response.status_code, 404)

    def test_the_last_enabled_admin_cannot_be_deleted(self):
        self.arrange(self.ROOT, 0)
        response = self.client.delete('/api/users/1', headers=SYSTEM)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.writes('DELETE FROM users'), [])

    def test_only_other_enabled_admins_count(self):
        # A disabled admin cannot log in to repair anything, and the target itself is no
        # "other" admin; the old delete check counted both.
        self.arrange(self.ROOT, 1)
        self.client.delete('/api/users/1', headers=SYSTEM)
        count = self.writes('COUNT(*)')[0]
        self.assertIn('enabled = TRUE', count)
        self.assertIn('id <> %s', count)

    def test_the_check_and_the_write_share_one_lock(self):
        seen = []
        self.cursor.execute.side_effect = lambda sql, *a: seen.append(users_router._admin_guard_lock.locked())
        self.arrange(self.ROOT, 1)
        self.client.post('/api/users/1/disable', headers=SYSTEM)
        self.assertTrue(seen and all(seen))
        self.assertFalse(users_router._admin_guard_lock.locked())


class SetupRaceTest(MockedDatabaseTestCase):
    """Two simultaneous first-time setups create exactly one admin."""

    def setUp(self):
        super().setUp()
        for patcher in (
            patch.object(users_router.rbac, 'get_role_by_name', side_effect=roles_by_name),
            patch.object(users_router, 'notify_server_sync_users'),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_the_insert_itself_refuses_a_non_empty_table(self):
        self.cursor.fetchone.return_value = {'count': 0}
        self.cursor.lastrowid = 1
        self.client.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'})
        insert = self.writes('INSERT INTO users')[0]
        self.assertIn('WHERE NOT EXISTS (SELECT 1 FROM users)', insert)

    def test_an_insert_that_found_a_row_after_all_is_a_conflict(self):
        # Another process won between our COUNT and our INSERT; the lock cannot see it.
        self.cursor.fetchone.return_value = {'count': 0}
        self.cursor.rowcount = 0
        response = self.client.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'})
        self.assertEqual(response.status_code, 409)
        self.conn.commit.assert_not_called()

    def test_two_simultaneous_setups_create_one_admin(self):
        table = []
        barrier = threading.Barrier(2)

        def connection():
            cursor = MagicMock()

            def execute(sql, params=None):
                if sql.startswith('SELECT COUNT(*)'):
                    cursor.fetchone.return_value = {'count': len(table)}
                    time.sleep(0.05)  # widen the gap between the check and the insert
                elif sql.startswith('INSERT INTO users'):
                    cursor.rowcount = 1
                    table.append(params[0])

            cursor.execute.side_effect = execute
            conn = MagicMock()
            conn.cursor.return_value.__enter__.return_value = cursor
            conn.cursor.return_value.__exit__.return_value = False
            return conn

        statuses = []

        def attempt(name):
            barrier.wait()
            statuses.append(
                self.client.post('/api/auth/setup', json={'username': name, 'password': 'hunter2'}).status_code
            )

        with patch.object(users_router, 'get_db_connection', side_effect=connection):
            threads = [threading.Thread(target=attempt, args=(name,)) for name in ('alice', 'bob')]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertEqual(sorted(statuses), [200, 409])
        self.assertEqual(len(table), 1)


class LoginEnumerationTest(MockedDatabaseTestCase):
    """An unknown username costs a bcrypt check and reads like a wrong password."""

    def setUp(self):
        super().setUp()
        self.password_hash = bcrypt.hashpw(b'correct-password', bcrypt.gensalt(4)).decode()

    def login(self, row, password='whatever'):
        """POST a login whose users lookup answers `row`."""
        self.cursor.fetchone.return_value = row
        return self.client.post('/api/auth/login', json={'username': 'someone', 'password': password})

    def test_an_unknown_username_runs_the_dummy_bcrypt_check(self):
        with patch.object(users_router.bcrypt, 'checkpw', wraps=bcrypt.checkpw) as checkpw:
            response = self.login(None)
        self.assertEqual(response.status_code, 401)
        checkpw.assert_called_once()
        self.assertEqual(checkpw.call_args.args[1], users_router.timing_dummy_hash())

    def test_an_unknown_username_and_a_wrong_password_read_the_same(self):
        unknown = self.login(None)
        wrong = self.login({'id': 5, 'username': 'someone', 'password_hash': self.password_hash, 'enabled': True})
        self.assertEqual((unknown.status_code, unknown.json()), (wrong.status_code, wrong.json()))

    def test_an_account_with_a_hash_does_not_also_pay_for_the_dummy(self):
        row = {'id': 5, 'username': 'someone', 'password_hash': self.password_hash, 'enabled': True}
        with patch.object(users_router, '_equalise_bcrypt_cost') as dummy:
            self.login(row)
        dummy.assert_not_called()

    def test_an_account_without_a_hash_pays_for_the_dummy_too(self):
        row = {'id': 3, 'username': 'someone', 'password_hash': None, 'api_key': 'k', 'enabled': True}
        with patch.object(users_router, '_equalise_bcrypt_cost') as dummy:
            self.login(row)
        dummy.assert_called_once()

    def test_a_disabled_account_is_only_named_to_someone_with_its_password(self):
        row = {'id': 4, 'username': 'someone', 'password_hash': self.password_hash, 'enabled': False}
        self.assertEqual(self.login(row, 'wrong').status_code, 401)
        self.assertEqual(self.login(row, 'correct-password').status_code, 403)

    def test_the_dummy_hash_is_a_real_cost_12_bcrypt_hash(self):
        self.assertTrue(users_router.timing_dummy_hash().startswith(b'$2b$12$'))
        self.assertIs(users_router.timing_dummy_hash(), users_router.timing_dummy_hash())


class KeyCheckOutageTest(unittest.TestCase):
    """Every router's key check reports a database outage as 503, not as a bad key."""

    ROUTES = [
        ('get', '/api/library/genres'),
        ('get', '/api/scrobble/import/latest'),
        ('get', '/api/rating/ratings/listener'),
        ('get', '/api/users'),
    ]

    def setUp(self):
        self.client = TestClient(app)

    def call(self, method, path):
        """Call `path` with a user key while the users table is unreachable."""
        return getattr(self.client, method)(path, headers={'x-api-key': 'a-user-key'})

    def test_no_pool_is_a_503(self):
        with patch.object(users_router, 'get_db_connection', return_value=None):
            for method, path in self.ROUTES:
                with self.subTest(path=path):
                    self.assertEqual(self.call(method, path).status_code, 503)

    def test_a_connection_error_is_a_503(self):
        with patch.object(users_router, 'get_db_connection', side_effect=OSError('refused')):
            for method, path in self.ROUTES:
                with self.subTest(path=path):
                    self.assertEqual(self.call(method, path).status_code, 503)

    def test_a_failing_query_is_a_503(self):
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value.execute.side_effect = RuntimeError('gone away')
        with patch.object(users_router, 'get_db_connection', return_value=conn):
            response = self.client.get('/api/auth/verify', headers={'x-api-key': 'a-user-key'})
        self.assertEqual(response.status_code, 503)
        conn.close.assert_called_once()

    def test_a_disabled_account_stays_a_403_on_every_router(self):
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value = {'id': 4, 'enabled': False}
        with patch.object(users_router, 'get_db_connection', return_value=conn):
            for method, path in self.ROUTES:
                with self.subTest(path=path):
                    response = self.call(method, path)
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(response.json()['detail'], 'Account disabled')

    def test_a_missing_key_stays_a_401(self):
        for method, path in self.ROUTES:
            with self.subTest(path=path):
                self.assertEqual(getattr(self.client, method)(path).status_code, 401)

    def test_no_router_keeps_a_swallowing_copy(self):
        # Each router's verify_api_key is the canonical check itself, not a copy or a
        # wrapper (test_router_api_key_dependency.py covers every router).
        for module in (library_router, scrobbler_router, rating_router):
            with self.subTest(module=module.__name__):
                self.assertIs(module.verify_api_key, users_router.verify_api_key)


class ScrobbleUsernameTest(unittest.TestCase):
    """A user key scrobbles into its own history only."""

    EVENT = {'artist_name': 'Angerfist', 'track_title': 'Raise & Revolt', 'username': 'someone-else'}

    def setUp(self):
        self.client = TestClient(app)
        self.conn = MagicMock()
        patcher = patch.object(scrobbler_router, 'get_db_connection', return_value=self.conn)
        patcher.start()
        self.addCleanup(patcher.stop)
        finder = patch.object(scrobbler_router, 'find_track', return_value=None)
        finder.start()
        self.addCleanup(finder.stop)

    def post(self, auth, username):
        """POST a scrobble naming `username`, as the account `auth` resolves to."""
        with patch.object(users_router, 'verify_token', return_value=auth):
            return self.client.post(
                '/api/scrobble/event', headers={'x-api-key': 'user-key'}, json={**self.EVENT, 'username': username}
            )

    def test_another_accounts_name_is_refused(self):
        response = self.post(LISTENER, 'someone-else')
        self.assertEqual(response.status_code, 403)
        self.conn.cursor.assert_not_called()

    def test_the_callers_own_name_is_accepted(self):
        self.assertEqual(self.post(LISTENER, 'listener').status_code, 200)

    def test_an_admin_may_scrobble_for_anyone(self):
        self.assertEqual(self.post(ADMIN, 'someone-else').status_code, 200)

    def test_the_system_key_may_scrobble_for_anyone(self):
        response = self.client.post('/api/scrobble/event', headers=SYSTEM, json=self.EVENT)
        self.assertEqual(response.status_code, 200)


class RefreshTokenCapTest(MockedDatabaseTestCase):
    """Issuing a refresh token prunes the account's oldest; the daily pass prunes all."""

    def test_issuing_a_token_inserts_then_prunes_that_account(self):
        cursor = MagicMock()
        rbac.issue_refresh_token(cursor, 7, 'tok')
        (insert, _), (prune, prune_params) = [c.args for c in cursor.execute.call_args_list]
        self.assertIn('INSERT INTO user_refresh_tokens', insert)
        self.assertIn('DELETE FROM user_refresh_tokens WHERE user_id = %s AND id <', prune)
        self.assertEqual(prune_params, (7, 7, rbac.REFRESH_TOKENS_PER_USER - 1))

    def test_a_password_login_prunes(self):
        password_hash = bcrypt.hashpw(b'pw', bcrypt.gensalt(4)).decode()
        self.cursor.fetchone.return_value = {
            'id': 5,
            'username': 'user',
            'password_hash': password_hash,
            'api_key': 'k',
            'enabled': True,
            'role_id': None,
        }
        with patch.object(users_router.rbac, 'get_permissions_for_role', return_value=set()):
            response = self.client.post('/api/auth/login', json={'username': 'user', 'password': 'pw'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.writes('DELETE FROM user_refresh_tokens WHERE user_id = %s AND id <')), 1)

    def test_the_daily_pass_caps_every_account_and_drops_old_revoked_rows(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.rowcount = 3
        removed = rbac.purge_refresh_tokens(conn)
        (cap, cap_params), (revoked, revoked_params) = [c.args for c in cursor.execute.call_args_list]
        self.assertIn('PARTITION BY user_id', cap)
        self.assertEqual(cap_params, (rbac.REFRESH_TOKENS_PER_USER,))
        self.assertIn('revoked_at IS NOT NULL', revoked)
        self.assertEqual(revoked_params, (rbac.REVOKED_REFRESH_TOKEN_DAYS,))
        self.assertEqual(removed, 6)
        conn.commit.assert_called_once()

    def test_the_retention_loop_runs_the_refresh_token_pass(self):
        conn = MagicMock()
        with (
            patch.object(events_retention, 'get_db_connection', return_value=conn),
            patch.object(events_retention, 'purge_once'),
            patch.object(events_retention, 'purge_refresh_tokens') as purge,
        ):
            events_retention.retention_tick()
        purge.assert_called_once_with(conn)
        conn.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
