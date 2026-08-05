"""Covers the account merge endpoint, the users schema bootstrap and the
server-database discovery in services/music_manager/routers/users.py."""
import importlib.util
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from services.music_manager.main import app
from services.music_manager.routers import users as users_router

API_KEY = os.getenv('API_KEY') or os.getenv('MUMA_API_KEY') or '00000000-0000-4000-8000-000000000000'


def _load_pristine_users_module():
    """Return a private copy of the users router module.

    Twenty test modules replace ``users_router.run_lms_db_sync`` with a no-op at
    import time, to keep the app's startup hook from kicking off a real database
    sync. That assignment is permanent for the session, so by the time these tests
    run the real function is no longer reachable through the shared module. Loading
    the file a second time under its own name gets it back without disturbing the
    module every other test is using; coverage still credits the same source file.
    """
    name = 'services.music_manager.routers.users_pristine'
    spec = importlib.util.spec_from_file_location(name, Path(users_router.__file__))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pristine_users = _load_pristine_users_module()


def normalize(sql):
    return ' '.join(sql.split())


class ScriptedCursor:
    """A cursor that answers fetchone/fetchall from a rule table.

    Each rule is ``(sql_fragment, params_or_None, result)``. The first rule whose
    fragment appears in the executed statement -- and whose params match, when it
    pins them down -- supplies the result: a list is served by fetchall, a mapping
    by fetchone. Anything unmatched reads as an empty table, which is what the
    merge code should treat as "the secondary account owns nothing here".
    """

    def __init__(self, rules=()):
        self.rules = list(rules)
        self.executed = []
        self._result = None

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql, params=None):
        statement = normalize(sql)
        self.executed.append((statement, params))
        self._result = None
        for fragment, expected_params, result in self.rules:
            if fragment in statement and (expected_params is None or expected_params == params):
                self._result = result
                break

    def fetchone(self):
        if isinstance(self._result, list):
            return self._result[0] if self._result else None
        return self._result

    def fetchall(self):
        if isinstance(self._result, list):
            return self._result
        return [self._result] if self._result else []

    def statements_matching(self, fragment):
        return [(sql, params) for sql, params in self.executed if fragment in sql]


PRIMARY = {'id': 1, 'username': 'user', 'display_name': 'Teun'}
SECONDARY = {'id': 2, 'username': 'user.google', 'display_name': 'Teun G'}


class MergeUsersTest(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def merge(self, rules, primary_id=1, secondary_id=2):
        cursor = ScriptedCursor(rules)
        connection = MagicMock()
        connection.cursor.return_value = cursor
        with patch.object(users_router, 'get_db_connection', return_value=connection):
            response = self.client.post(
                f'/api/users/{primary_id}/merge',
                json={'secondary_user_id': secondary_id},
                headers={'x-api-key': API_KEY},
            )
        return response, cursor, connection

    def base_rules(self, **extra):
        rules = [
            ('SELECT * FROM users WHERE id = %s', (1,), PRIMARY),
            ('SELECT * FROM users WHERE id = %s', (2,), SECONDARY),
        ]
        rules.extend(extra.pop('rules', []))
        return rules

    def test_a_clean_merge_reports_the_surviving_account(self):
        merged = {'id': 1, 'username': 'user', 'role_name': 'admin'}
        rules = self.base_rules() + [('FROM users u LEFT JOIN roles r', (1,), merged)]

        response, _cursor, connection = self.merge(rules)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok', 'user': merged})
        connection.commit.assert_called_once()
        connection.close.assert_called_once()

    def test_the_secondary_account_is_deleted(self):
        response, cursor, _connection = self.merge(self.base_rules())

        self.assertEqual(response.status_code, 200)
        self.assertIn(('DELETE FROM users WHERE id = %s', (2,)), cursor.executed)

    def test_merging_an_account_into_itself_is_rejected(self):
        response, _cursor, _connection = self.merge(self.base_rules(), secondary_id=1)

        self.assertEqual(response.status_code, 400)
        self.assertIn('zichzelf', response.json()['detail'])

    def test_an_unknown_account_is_a_404(self):
        rules = [('SELECT * FROM users WHERE id = %s', (1,), PRIMARY)]

        response, _cursor, connection = self.merge(rules)

        self.assertEqual(response.status_code, 404)
        connection.commit.assert_not_called()
        connection.close.assert_called_once()

    def test_a_database_that_is_down_is_a_500(self):
        with patch.object(users_router, 'get_db_connection', return_value=None):
            response = self.client.post(
                '/api/users/1/merge', json={'secondary_user_id': 2}, headers={'x-api-key': API_KEY}
            )

        self.assertEqual(response.status_code, 500)

    def test_an_unexpected_failure_is_reported_and_the_connection_closed(self):
        connection = MagicMock()
        connection.cursor.side_effect = RuntimeError('connection reset')

        with patch.object(users_router, 'get_db_connection', return_value=connection):
            response = self.client.post(
                '/api/users/1/merge', json={'secondary_user_id': 2}, headers={'x-api-key': API_KEY}
            )

        self.assertEqual(response.status_code, 500)
        self.assertIn('connection reset', response.json()['detail'])
        connection.close.assert_called_once()

    def test_an_identity_the_primary_lacks_is_moved_over(self):
        rules = self.base_rules() + [
            ('SELECT provider FROM user_identities WHERE user_id = %s', (1,), []),
            ('SELECT id, provider FROM user_identities WHERE user_id = %s', (2,), [{'id': 9, 'provider': 'google'}]),
        ]

        _response, cursor, _connection = self.merge(rules)

        self.assertIn(('UPDATE user_identities SET user_id = %s WHERE id = %s', (1, 9)), cursor.executed)

    def test_a_duplicate_identity_is_dropped_in_favour_of_the_primary(self):
        rules = self.base_rules() + [
            ('SELECT provider FROM user_identities WHERE user_id = %s', (1,), [{'provider': 'google'}]),
            ('SELECT id, provider FROM user_identities WHERE user_id = %s', (2,), [{'id': 9, 'provider': 'google'}]),
        ]

        _response, cursor, _connection = self.merge(rules)

        self.assertIn(('DELETE FROM user_identities WHERE id = %s', (9,)), cursor.executed)

    def test_the_secondary_sessions_are_revoked(self):
        _response, cursor, _connection = self.merge(self.base_rules())

        self.assertIn(('DELETE FROM user_refresh_tokens WHERE user_id = %s', (2,)), cursor.executed)

    def test_dynamic_playlists_are_repointed(self):
        _response, cursor, _connection = self.merge(self.base_rules())

        self.assertIn(
            ('UPDATE dynamic_playlists SET user_id = %s WHERE user_id = %s', (1, 2)), cursor.executed
        )

    def test_app_settings_the_primary_lacks_are_moved_over(self):
        rules = self.base_rules() + [
            ('SELECT app_id FROM user_app_settings WHERE user_id = %s', (1,), []),
            ('SELECT id, app_id FROM user_app_settings WHERE user_id = %s', (2,), [{'id': 4, 'app_id': 'ultrasonic'}]),
        ]

        _response, cursor, _connection = self.merge(rules)

        self.assertIn(('UPDATE user_app_settings SET user_id = %s WHERE id = %s', (1, 4)), cursor.executed)

    def test_duplicate_app_settings_are_dropped(self):
        rules = self.base_rules() + [
            ('SELECT app_id FROM user_app_settings WHERE user_id = %s', (1,), [{'app_id': 'ultrasonic'}]),
            ('SELECT id, app_id FROM user_app_settings WHERE user_id = %s', (2,), [{'id': 4, 'app_id': 'ultrasonic'}]),
        ]

        _response, cursor, _connection = self.merge(rules)

        self.assertIn(('DELETE FROM user_app_settings WHERE id = %s', (4,)), cursor.executed)

    def test_the_listenbrainz_link_is_adopted_when_the_primary_has_none(self):
        _response, cursor, _connection = self.merge(self.base_rules())

        self.assertIn(
            ('UPDATE user_listenbrainz_accounts SET user_id = %s WHERE user_id = %s', (1, 2)), cursor.executed
        )

    def test_the_primary_listenbrainz_link_wins(self):
        rules = self.base_rules() + [
            ('SELECT user_id FROM user_listenbrainz_accounts WHERE user_id = %s', (1,), {'user_id': 1}),
        ]

        _response, cursor, _connection = self.merge(rules)

        self.assertIn(('DELETE FROM user_listenbrainz_accounts WHERE user_id = %s', (2,)), cursor.executed)

    def test_ratings_and_listens_are_repointed_to_the_surviving_username(self):
        rules = self.base_rules() + [
            ('SELECT id, entity_type, entity_id FROM rating_tracks', ('user.google',), [{'id': 7, 'entity_type': 'track', 'entity_id': 55}]),
        ]

        _response, cursor, _connection = self.merge(rules)

        self.assertIn(('UPDATE rating_tracks SET username = %s WHERE id = %s', ('user', 7)), cursor.executed)
        self.assertIn(
            ('UPDATE scrobble_imports SET username = %s WHERE username = %s', ('user', 'user.google')),
            cursor.executed,
        )

    def test_a_rating_the_primary_already_has_is_dropped(self):
        rules = self.base_rules() + [
            ('SELECT id, entity_type, entity_id FROM rating_tracks', ('user.google',), [{'id': 7, 'entity_type': 'track', 'entity_id': 55}]),
            ('SELECT id FROM rating_tracks WHERE username = %s', ('user', 'track', 55), {'id': 3}),
        ]

        _response, cursor, _connection = self.merge(rules)

        self.assertIn(('DELETE FROM rating_tracks WHERE id = %s', (7,)), cursor.executed)

    def test_historical_references_follow_the_surviving_account(self):
        _response, cursor, _connection = self.merge(self.base_rules())

        self.assertIn(
            ('UPDATE user_requests SET reviewed_by_user_id = %s WHERE reviewed_by_user_id = %s', (1, 2)),
            cursor.executed,
        )
        self.assertIn(
            ('UPDATE user_requests SET created_user_id = %s WHERE created_user_id = %s', (1, 2)),
            cursor.executed,
        )

    def test_the_merge_is_written_to_the_audit_log(self):
        with patch.object(users_router.rbac, 'record_audit_event') as record:
            self.merge(self.base_rules())

        self.assertEqual(record.call_args[0][1], 'user.merged')
        self.assertEqual(record.call_args.kwargs['target_user_id'], 1)
        self.assertIn('user.google', record.call_args.kwargs['details'])


class InitDbTest(unittest.TestCase):
    """init_db has to survive both a fresh database and every intermediate schema
    the users table has had, so the branches are driven by what SHOW COLUMNS returns."""

    def run_init(self, present_columns):
        cursor = ScriptedCursor([
            (f"SHOW COLUMNS FROM {table} LIKE '{column}'", None, {'Field': column})
            for table, column in present_columns
        ])
        with patch.object(users_router.rbac, 'init_db') as rbac_init:
            users_router.init_db(cursor)
        return cursor, rbac_init

    def test_a_fresh_database_gets_every_column_added(self):
        cursor, rbac_init = self.run_init([])

        added = ' '.join(sql for sql, _params in cursor.statements_matching('ALTER TABLE'))
        self.assertIn('ADD COLUMN server_user_id', added)
        self.assertIn('ADD COLUMN is_admin', added)
        self.assertIn('ADD COLUMN password_hash', added)
        self.assertIn('ADD COLUMN api_key', added)
        self.assertIn('ADD COLUMN remote_id', added)
        self.assertIn('ADD COLUMN source', added)
        rbac_init.assert_called_once_with(cursor)

    def test_a_legacy_lms_user_id_column_is_renamed_rather_than_added(self):
        cursor, _rbac_init = self.run_init([('users', 'lms_user_id')])

        renamed = cursor.statements_matching('CHANGE lms_user_id server_user_id')
        self.assertEqual(len(renamed), 1)
        self.assertEqual(cursor.statements_matching('ADD COLUMN server_user_id'), [])

    def test_an_up_to_date_schema_is_left_alone(self):
        columns = [
            ('users', 'server_user_id'), ('users', 'is_admin'), ('users', 'password_hash'),
            ('users', 'api_key'), ('dynamic_playlists', 'remote_id'), ('dynamic_playlists', 'source'),
        ]

        cursor, _rbac_init = self.run_init(columns)

        self.assertEqual(cursor.statements_matching('ADD COLUMN'), [])

    def test_a_duplicate_column_race_is_tolerated(self):
        cursor = ScriptedCursor()
        original_execute = cursor.execute

        def execute(sql, params=None):
            original_execute(sql, params)
            if 'ADD COLUMN is_admin' in sql:
                raise RuntimeError('Duplicate column name: is_admin')

        cursor.execute = execute
        with patch.object(users_router.rbac, 'init_db'):
            users_router.init_db(cursor)

        self.assertTrue(cursor.statements_matching('ADD COLUMN api_key'))

    def test_any_other_alter_failure_is_raised(self):
        cursor = ScriptedCursor()
        original_execute = cursor.execute

        def execute(sql, params=None):
            original_execute(sql, params)
            if 'ADD COLUMN password_hash' in sql:
                raise RuntimeError('disk full')

        cursor.execute = execute
        with patch.object(users_router.rbac, 'init_db'), self.assertRaises(RuntimeError):
            users_router.init_db(cursor)


class RunServerDbSyncTest(unittest.TestCase):
    """run_lms_db_sync only discovers databases and hands each to
    sync_single_server_db; the sync itself is exercised elsewhere."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.connection = MagicMock()

    def run_sync(self, env, per_db_result=1):
        environment = {'MUMA_SERVER_DB_ROOT': str(self.root), **env}
        with patch.dict(os.environ, environment, clear=False), \
             patch.object(pristine_users, 'get_db_connection', return_value=self.connection), \
             patch.object(pristine_users, 'sync_single_server_db', return_value=per_db_result) as sync:
            total = pristine_users.run_lms_db_sync()
        return total, sync

    def test_nothing_to_sync_when_the_root_is_empty(self):
        total, sync = self.run_sync({})

        self.assertEqual(total, 0)
        sync.assert_not_called()
        self.connection.close.assert_called_once()

    def test_a_database_directly_under_the_root_is_picked_up(self):
        (self.root / 'lms.db').write_text('', encoding='utf-8')

        total, sync = self.run_sync({})

        self.assertEqual(total, 1)
        self.assertEqual(sync.call_args[0][2], 'server-root')

    def test_a_database_in_a_subdirectory_is_picked_up_under_its_own_name(self):
        instance = self.root / 'instance-a'
        instance.mkdir()
        (instance / 'lms.db').write_text('', encoding='utf-8')

        total, sync = self.run_sync({})

        self.assertEqual(total, 1)
        self.assertEqual(sync.call_args[0][2], 'server-instance-a')

    def test_an_explicit_database_path_is_synced_as_well(self):
        direct = self.root.parent / 'direct.db'
        direct.write_text('', encoding='utf-8')
        self.addCleanup(direct.unlink)

        total, sync = self.run_sync({'MUMA_SERVER_DB_PATH': str(direct)})

        self.assertEqual(total, 1)
        self.assertEqual(sync.call_args[0][2], 'server-direct')

    def test_the_totals_of_every_database_are_added_up(self):
        (self.root / 'lms.db').write_text('', encoding='utf-8')
        instance = self.root / 'instance-a'
        instance.mkdir()
        (instance / 'lms.db').write_text('', encoding='utf-8')

        total, sync = self.run_sync({}, per_db_result=3)

        self.assertEqual(total, 6)
        self.assertEqual(sync.call_count, 2)

    def test_a_database_that_is_down_syncs_nothing(self):
        (self.root / 'lms.db').write_text('', encoding='utf-8')

        with patch.dict(os.environ, {'MUMA_SERVER_DB_ROOT': str(self.root)}, clear=False), \
             patch.object(pristine_users, 'get_db_connection', return_value=None), \
             patch.object(pristine_users, 'sync_single_server_db') as sync:
            self.assertEqual(pristine_users.run_lms_db_sync(), 0)

        sync.assert_not_called()


class VerifyApiKeyTest(unittest.TestCase):

    def test_a_request_without_a_key_is_unauthorized(self):
        response = TestClient(app).get('/api/users')

        self.assertEqual(response.status_code, 401)

    def test_a_key_that_is_neither_the_system_key_nor_a_session_is_unauthorized(self):
        with patch.object(users_router, 'verify_token', return_value={'status': 'error'}):
            response = TestClient(app).get('/api/users', headers={'x-api-key': 'not-a-key'})

        self.assertEqual(response.status_code, 401)


if __name__ == '__main__':
    unittest.main()
