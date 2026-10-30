"""Covers the account merge endpoint, the users schema bootstrap and the
server-database discovery in services/music_manager/routers/users.py."""

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from services.music_manager.api_key import resolve_system_api_key
from services.music_manager.main import app
from services.music_manager.routers import users as users_router
from services.music_manager.tests.scripted_cursor import (
    ScriptedCursor,
    assert_atomic,
    assert_rolled_back,
    transaction_log,
)

pytestmark = pytest.mark.mock_base('DatabaseConnector')

API_KEY = resolve_system_api_key()


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

        self.assertIn(('UPDATE dynamic_playlists SET user_id = %s WHERE user_id = %s', (1, 2)), cursor.executed)

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
            (
                'SELECT id, entity_type, entity_id FROM rating_tracks',
                ('user.google',),
                [{'id': 7, 'entity_type': 'track', 'entity_id': 55}],
            ),
        ]

        _response, cursor, _connection = self.merge(rules)

        self.assertIn(('UPDATE rating_tracks SET username = %s WHERE id = %s', ('user', 7)), cursor.executed)
        self.assertIn(
            ('UPDATE scrobble_imports SET username = %s WHERE username = %s', ('user', 'user.google')),
            cursor.executed,
        )

    def test_a_rating_the_primary_already_has_is_dropped(self):
        rules = self.base_rules() + [
            (
                'SELECT id, entity_type, entity_id FROM rating_tracks',
                ('user.google',),
                [{'id': 7, 'entity_type': 'track', 'entity_id': 55}],
            ),
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
    """init_db only seeds: the tables come from services/common/schema_tables.py."""

    def test_it_seeds_the_roles_and_touches_no_schema(self):
        cursor = ScriptedCursor()
        with patch.object(users_router.rbac, 'init_db') as rbac_init:
            users_router.init_db(cursor)

        rbac_init.assert_called_once_with(cursor)
        self.assertEqual(cursor.statements_matching('ALTER TABLE'), [])
        self.assertEqual(cursor.statements_matching('CREATE TABLE'), [])


def make_lms_db(path):
    """An SQLite file at `path` with the core LMS tables, so lms_db_targets() keeps it."""
    import sqlite3

    conn = sqlite3.connect(path)
    for table in ('user', 'track', 'listen'):
        conn.execute(f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY)')
    conn.commit()
    conn.close()


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
        with (
            patch.dict(os.environ, environment, clear=False),
            patch.object(pristine_users, 'get_db_connection', return_value=self.connection),
            patch.object(pristine_users, 'sync_single_server_db', return_value=per_db_result) as sync,
        ):
            total = pristine_users.run_lms_db_sync()
        return total, sync

    def test_nothing_to_sync_when_the_root_is_empty(self):
        total, sync = self.run_sync({})

        self.assertEqual(total, 0)
        sync.assert_not_called()
        self.connection.close.assert_called_once()

    def test_a_database_directly_under_the_root_is_picked_up(self):
        make_lms_db(self.root / 'lms.db')

        total, sync = self.run_sync({})

        self.assertEqual(total, 1)
        self.assertEqual(sync.call_args[0][2], 'server-root')

    def test_a_database_in_a_subdirectory_is_picked_up_under_its_own_name(self):
        instance = self.root / 'instance-a'
        instance.mkdir()
        make_lms_db(instance / 'lms.db')

        total, sync = self.run_sync({})

        self.assertEqual(total, 1)
        self.assertEqual(sync.call_args[0][2], 'server-instance-a')

    def test_an_explicit_database_path_is_synced_as_well(self):
        direct = self.root.parent / 'direct.db'
        make_lms_db(direct)
        self.addCleanup(direct.unlink)

        total, sync = self.run_sync({'MUMA_SERVER_DB_PATH': str(direct)})

        self.assertEqual(total, 1)
        self.assertEqual(sync.call_args[0][2], 'server-direct')

    def test_the_totals_of_every_database_are_added_up(self):
        make_lms_db(self.root / 'lms.db')
        instance = self.root / 'instance-a'
        instance.mkdir()
        make_lms_db(instance / 'lms.db')

        total, sync = self.run_sync({}, per_db_result=3)

        self.assertEqual(total, 6)
        self.assertEqual(sync.call_count, 2)

    def test_a_file_without_the_lms_schema_is_never_handed_to_the_sync(self):
        """Bug 070: production's stale alpha/lms.db has no `user` table and no server behind it."""
        make_lms_db(self.root / 'lms.db')
        stale = self.root / 'alpha'
        stale.mkdir()
        (stale / 'lms.db').write_text('', encoding='utf-8')

        total, sync = self.run_sync({})

        self.assertEqual(total, 1)
        self.assertEqual([c.args[2] for c in sync.call_args_list], ['server-root'])

    def test_a_database_that_is_down_syncs_nothing(self):
        make_lms_db(self.root / 'lms.db')

        with (
            patch.dict(os.environ, {'MUMA_SERVER_DB_ROOT': str(self.root)}, clear=False),
            patch.object(pristine_users, 'get_db_connection', return_value=None),
            patch.object(pristine_users, 'sync_single_server_db') as sync,
        ):
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


class MergeAtomicityTest(unittest.TestCase):
    """A merge moves every row and deletes the secondary account in one transaction."""

    setUp = MergeUsersTest.setUp
    base_rules = MergeUsersTest.base_rules

    def merge_logged(self, rules, fail_on=None):
        cursor = ScriptedCursor(rules)
        connection = MagicMock()
        connection.cursor.return_value = cursor
        log = transaction_log(connection, cursor, fail_on=fail_on)
        with patch.object(users_router, 'get_db_connection', return_value=connection):
            response = self.client.post(
                '/api/users/1/merge', json={'secondary_user_id': 2}, headers={'x-api-key': API_KEY}
            )
        return response, log

    def test_the_moves_and_the_account_delete_are_one_transaction(self):
        response, log = self.merge_logged(self.base_rules())
        self.assertEqual(response.status_code, 200)
        assert_atomic(self, log, 'UPDATE dynamic_playlists', 'DELETE FROM users WHERE id')

    def test_a_failure_half_way_moves_nothing(self):
        response, log = self.merge_logged(self.base_rules(), fail_on='DELETE FROM users WHERE id')
        self.assertEqual(response.status_code, 500)
        assert_rolled_back(self, log)


if __name__ == '__main__':
    unittest.main()
