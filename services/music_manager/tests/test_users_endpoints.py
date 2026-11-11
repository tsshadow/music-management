"""End-to-end coverage of the /api/users and /api/auth endpoints.

Everything runs against the FastAPI TestClient with the system API key, which
``verify_api_key`` accepts outright, so these tests exercise the endpoint bodies
rather than the permission wiring (that already lives in test_rbac.py).
"""

import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector')


import services.music_manager.routers.users as users_router

users_router.run_lms_db_sync = lambda only_sources=None: None
import services.music_manager.database

services.music_manager.database.get_db_connection = MagicMock(return_value=None)

from fastapi.testclient import TestClient

from services.music_manager.main import app
from services.music_manager.tests.scripted_cursor import assert_atomic, assert_rolled_back, transaction_log

API_KEY = users_router.API_KEY


class UsersEndpointTestCase(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.headers = {'x-api-key': API_KEY}
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = self.cursor
        self.conn.cursor.return_value.__exit__.return_value = False
        patcher = patch.object(users_router, 'get_db_connection', return_value=self.conn)
        patcher.start()
        self.addCleanup(patcher.stop)

    def statements(self):
        return [call.args[0] for call in self.cursor.execute.call_args_list]


class AuthEndpointTest(UsersEndpointTestCase):
    def test_the_system_key_verifies_as_a_system_caller(self):
        response = self.client.get('/api/auth/verify', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok', 'type': 'system'})

    def test_a_request_without_a_key_is_unauthorized(self):
        self.assertEqual(self.client.get('/api/auth/verify').status_code, 401)

    def test_an_unknown_key_is_forbidden(self):
        self.cursor.fetchone.return_value = None
        response = self.client.get('/api/auth/verify', headers={'x-api-key': 'nope'})
        self.assertEqual(response.status_code, 403)

    def test_a_user_key_verifies_as_that_user(self):
        self.cursor.fetchone.side_effect = [
            {'id': 4, 'username': 'user', 'enabled': True, 'role_id': 2},
            {'name': 'user'},
        ]
        with patch.object(users_router.rbac, 'get_permissions_for_role', return_value={'users.read'}):
            response = self.client.get('/api/auth/verify', headers={'x-api-key': 'user-key'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['type'], 'user')
        self.assertEqual(body['user']['username'], 'user')
        self.assertEqual(body['user']['permissions'], ['users.read'])
        self.assertFalse(body['user']['is_admin'])

    def test_a_disabled_user_key_is_refused(self):
        self.cursor.fetchone.return_value = {'id': 4, 'username': 'user', 'enabled': False, 'role_id': 2}
        response = self.client.get('/api/auth/verify', headers={'x-api-key': 'user-key'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['detail'], 'Account disabled')

    def test_a_user_holding_the_admin_role_is_flagged_as_admin(self):
        self.cursor.fetchone.side_effect = [
            {'id': 1, 'username': 'root', 'enabled': True, 'role_id': 1},
            {'name': users_router.rbac.ADMIN_ROLE_NAME},
        ]
        with patch.object(users_router.rbac, 'get_permissions_for_role', return_value=set()):
            response = self.client.get('/api/auth/verify', headers={'x-api-key': 'admin-key'})
        self.assertTrue(response.json()['user']['is_admin'])

    def test_a_user_without_a_role_has_no_role_name(self):
        self.cursor.fetchone.return_value = {'id': 4, 'username': 'user', 'enabled': True, 'role_id': None}
        with patch.object(users_router.rbac, 'get_permissions_for_role', return_value=set()):
            response = self.client.get('/api/auth/verify', headers={'x-api-key': 'user-key'})
        self.assertIsNone(response.json()['user']['role_name'])


class RefreshTokenTest(UsersEndpointTestCase):
    def test_a_valid_refresh_token_yields_a_fresh_access_token(self):
        self.cursor.fetchone.side_effect = [
            {'id': 9, 'user_id': 4},
            {'id': 4, 'username': 'user', 'enabled': True, 'role_id': 2, 'api_key': 'the-key'},
            {'name': 'user'},
        ]
        with patch.object(users_router.rbac, 'get_permissions_for_role', return_value=set()):
            response = self.client.post('/api/auth/refresh', json={'refresh_token': 'rt'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['access_token'], 'the-key')

    def test_an_unknown_refresh_token_is_rejected(self):
        self.cursor.fetchone.return_value = None
        response = self.client.post('/api/auth/refresh', json={'refresh_token': 'rt'})
        self.assertEqual(response.status_code, 401)

    def test_a_refresh_token_of_a_disabled_account_is_rejected(self):
        self.cursor.fetchone.side_effect = [{'id': 9, 'user_id': 4}, {'id': 4, 'enabled': False}]
        response = self.client.post('/api/auth/refresh', json={'refresh_token': 'rt'})
        self.assertEqual(response.status_code, 403)

    def test_a_database_outage_is_reported_as_a_server_error(self):
        with patch.object(users_router, 'get_db_connection', return_value=None):
            response = self.client.post('/api/auth/refresh', json={'refresh_token': 'rt'})
        self.assertEqual(response.status_code, 500)


class SetupTest(UsersEndpointTestCase):
    def test_an_empty_user_table_means_setup_is_required(self):
        self.cursor.fetchone.return_value = {'count': 0}
        self.assertTrue(self.client.get('/api/auth/setup-status').json()['setup_required'])

    def test_an_existing_user_means_setup_is_done(self):
        self.cursor.fetchone.return_value = {'count': 3}
        self.assertFalse(self.client.get('/api/auth/setup-status').json()['setup_required'])

    def test_the_first_admin_can_be_created(self):
        self.cursor.fetchone.return_value = {'count': 0}
        self.cursor.lastrowid = 1
        with (
            patch.object(users_router.rbac, 'get_role_by_name', return_value={'id': 1}),
            patch.object(users_router, 'notify_server_sync_users') as notify,
        ):
            response = self.client.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['is_admin'])
        notify.assert_called_once()

    def test_setup_cannot_run_twice(self):
        self.cursor.fetchone.return_value = {'count': 1}
        response = self.client.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'})
        self.assertEqual(response.status_code, 409)

    def test_setup_requires_a_password(self):
        self.cursor.fetchone.return_value = {'count': 0}
        response = self.client.post('/api/auth/setup', json={'username': 'root'})
        self.assertEqual(response.status_code, 400)


class DynamicPlaylistTest(UsersEndpointTestCase):
    def test_the_playlists_of_a_user_are_listed(self):
        self.cursor.fetchall.return_value = [{'id': 1, 'name': 'Hardstyle'}]
        response = self.client.get('/api/users/4/dynamic-playlists', headers=self.headers)
        self.assertEqual(response.json(), [{'id': 1, 'name': 'Hardstyle'}])

    def test_a_single_playlist_is_returned(self):
        self.cursor.fetchone.return_value = {'id': 1, 'name': 'Hardstyle'}
        response = self.client.get('/api/users/4/dynamic-playlists/1', headers=self.headers)
        self.assertEqual(response.status_code, 200)

    def test_a_missing_playlist_is_a_not_found(self):
        self.cursor.fetchone.return_value = None
        response = self.client.get('/api/users/4/dynamic-playlists/1', headers=self.headers)
        self.assertEqual(response.status_code, 404)

    def test_a_playlist_can_be_created(self):
        self.cursor.lastrowid = 12
        response = self.client.post(
            '/api/users/4/dynamic-playlists', headers=self.headers, json={'name': 'New', 'params': '{}'}
        )
        self.assertEqual(response.json(), {'status': 'ok', 'id': 12})

    def test_updating_both_name_and_params_writes_both(self):
        self.client.put('/api/users/4/dynamic-playlists/1', headers=self.headers, json={'name': 'New', 'params': '{}'})
        self.assertIn('SET name = %s, params = %s', self.statements()[0])

    def test_updating_only_the_name_leaves_the_params_alone(self):
        self.client.put('/api/users/4/dynamic-playlists/1', headers=self.headers, json={'name': 'New'})
        self.assertIn('SET name = %s WHERE', self.statements()[0])

    def test_updating_only_the_params_leaves_the_name_alone(self):
        self.client.put('/api/users/4/dynamic-playlists/1', headers=self.headers, json={'params': '{}'})
        self.assertIn('SET params = %s WHERE', self.statements()[0])

    def test_a_definition_that_is_not_a_json_object_is_a_422(self):
        for params in ('not json', '[]'):
            with self.subTest(params=params):
                response = self.client.post(
                    '/api/users/4/dynamic-playlists', headers=self.headers, json={'name': 'New', 'params': params}
                )
                self.assertEqual(response.status_code, 422)
        self.assertEqual(self.statements(), [])

    def test_a_size_above_the_cap_is_a_422_on_create_and_update(self):
        params = json.dumps({'size': 1_000_000})
        created = self.client.post(
            '/api/users/4/dynamic-playlists', headers=self.headers, json={'name': 'New', 'params': params}
        )
        updated = self.client.put('/api/users/4/dynamic-playlists/1', headers=self.headers, json={'params': params})
        self.assertEqual((created.status_code, updated.status_code), (422, 422))
        self.assertEqual(self.statements(), [])

    def test_an_empty_update_writes_nothing(self):
        response = self.client.put('/api/users/4/dynamic-playlists/1', headers=self.headers, json={})
        self.assertEqual(response.json(), {'status': 'ok'})
        self.assertEqual(self.statements(), [])


class DynamicPlaylistTracksTest(UsersEndpointTestCase):
    """The rating filter on a seeded playlist.

    ``rating_tracks`` arrives by LEFT JOIN, so an unrated track has a NULL rating
    and fails every comparison. A range covering the whole scale is the UI's way
    of saying "no filter", and has to build no clause at all -- comparing against
    it drops every unrated track, which in this library is almost all of them.
    """

    def playlist(self, params):
        self.cursor.fetchone.side_effect = [
            {'username': 'user'},
            {'params': json.dumps(params)},
        ]
        self.cursor.fetchall.return_value = []
        self.client.get('/api/users/4/dynamic-playlists/1/tracks', headers=self.headers)
        return [s for s in self.statements() if 'FROM library_tracks' in s][0]

    def test_the_full_range_builds_no_rating_clause(self):
        query = self.playlist({'genres': ['Hardstyle'], 'rating_range': [0, 100]})

        self.assertNotIn('rt.rating >=', query)

    def test_a_missing_rating_range_builds_no_rating_clause(self):
        query = self.playlist({'genres': ['Hardstyle']})

        self.assertNotIn('rt.rating >=', query)

    def test_a_real_lower_bound_still_filters(self):
        query = self.playlist({'genres': ['Hardstyle'], 'rating_range': [4, 100]})

        self.assertIn('rt.rating >=', query)

    def test_a_real_upper_bound_still_filters(self):
        query = self.playlist({'genres': ['Hardstyle'], 'rating_range': [0, 60]})

        self.assertIn('rt.rating >=', query)

    def test_a_wider_than_full_range_is_still_no_filter(self):
        query = self.playlist({'genres': ['Hardstyle'], 'rating_range': [-1, 200]})

        self.assertNotIn('rt.rating >=', query)

    def test_a_playlist_can_be_deleted(self):
        response = self.client.delete('/api/users/4/dynamic-playlists/1', headers=self.headers)
        self.assertEqual(response.json(), {'status': 'ok'})
        self.assertIn('DELETE FROM dynamic_playlists', self.statements()[0])

    def test_the_default_playlists_can_be_seeded(self):
        response = self.client.post('/api/users/4/dynamic-playlists/seed-defaults', headers=self.headers)
        self.assertEqual(response.json(), {'status': 'ok'})
        self.assertEqual(len(self.statements()), 4)

    def test_seeding_skips_a_default_the_user_already_has(self):
        self.client.post('/api/users/4/dynamic-playlists/seed-defaults', headers=self.headers)
        for statement in self.statements():
            self.assertIn(
                "WHERE NOT EXISTS (SELECT 1 FROM dynamic_playlists WHERE user_id = %s AND source = 'default'", statement
            )

    def test_a_stored_size_above_the_cap_is_clamped_in_the_query(self):
        self.cursor.fetchone.side_effect = [{'username': 'user'}, {'params': '{"size": 1000000}'}]
        self.cursor.fetchall.return_value = []
        response = self.client.get('/api/users/4/dynamic-playlists/1/tracks', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.cursor.execute.call_args.args[1][-1], 2000)

    def test_a_stored_definition_that_is_not_an_object_still_answers(self):
        self.cursor.fetchone.side_effect = [{'username': 'user'}, {'params': '[1, 2]'}]
        self.cursor.fetchall.return_value = []
        response = self.client.get('/api/users/4/dynamic-playlists/1/tracks', headers=self.headers)
        self.assertEqual(response.status_code, 200)


class PlaylistTracksTest(UsersEndpointTestCase):
    def build(self, params):
        self.cursor.fetchone.side_effect = [{'username': 'user'}, {'params': params}]
        self.cursor.fetchall.return_value = []
        response = self.client.get('/api/users/4/dynamic-playlists/1/tracks', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        return self.cursor.execute.call_args.args

    def test_a_missing_playlist_is_a_not_found(self):
        self.cursor.fetchone.side_effect = [{'username': 'user'}, None]
        response = self.client.get('/api/users/4/dynamic-playlists/1/tracks', headers=self.headers)
        self.assertEqual(response.status_code, 404)

    def test_the_rating_join_is_scoped_to_the_requesting_user(self):
        _query, params = self.build(json.dumps({}))
        self.assertEqual(params[0], 'user')

    def test_an_unknown_user_still_produces_a_query(self):
        self.cursor.fetchone.side_effect = [None, {'params': '{}'}]
        self.cursor.fetchall.return_value = []
        self.client.get('/api/users/4/dynamic-playlists/1/tracks', headers=self.headers)
        self.assertEqual(self.cursor.execute.call_args.args[1][0], 'unknown')

    def test_selected_genres_are_matched_against_both_tags_and_ml_labels(self):
        query, params = self.build(json.dumps({'genres': ['Hardstyle']}))
        self.assertIn('library_track_genres', query)
        self.assertIn('library_track_ml_labels', query)
        self.assertEqual(params.count('Hardstyle'), 2)

    def test_an_extra_genre_rule_widens_the_selection(self):
        _query, params = self.build(json.dumps({'genres': [], 'rules': [{'column': 'genre', 'value': 'Uptempo'}]}))
        self.assertEqual(params.count('Uptempo'), 2)

    def test_a_rule_repeating_a_selected_genre_is_not_added_twice(self):
        _query, params = self.build(
            json.dumps({'genres': ['Hardstyle'], 'rules': [{'column': 'genre', 'value': 'Hardstyle'}]})
        )
        self.assertEqual(params.count('Hardstyle'), 2)

    def test_short_tracks_only(self):
        query, _ = self.build(json.dumps({'song_type': 'track'}))
        self.assertIn('duration_secs < 600', query)

    def test_long_sets_only(self):
        query, _ = self.build(json.dumps({'song_type': 'set'}))
        self.assertIn('duration_secs >= 600', query)

    def test_random_ordering(self):
        query, _ = self.build(json.dumps({'sort_method': 'random'}))
        self.assertIn('ORDER BY RAND()', query)

    def test_highest_rated_ordering(self):
        query, _ = self.build(json.dumps({'sort_method': 'highest_rated'}))
        self.assertIn('rt.rating DESC', query)

    def test_oldest_first_ordering(self):
        query, _ = self.build(json.dumps({'sort_method': 'oldest'}))
        self.assertIn('created_at ASC', query)

    def test_newest_first_is_the_default_ordering(self):
        query, _ = self.build(json.dumps({}))
        self.assertIn('created_at DESC', query)

    def test_the_configured_size_becomes_the_limit(self):
        query, params = self.build(json.dumps({'size': 25}))
        self.assertIn('LIMIT %s', query)
        self.assertEqual(params[-1], 25)

    def test_legacy_query_string_parameters_are_still_understood(self):
        query, params = self.build('size=10&sort_method=random')
        self.assertIn('ORDER BY RAND()', query)
        self.assertEqual(params[-1], 10)

    def test_unparseable_parameters_fall_back_to_the_defaults(self):
        query, params = self.build('not json at all')
        self.assertIn('created_at DESC', query)
        self.assertEqual(params[-1], 500)


class UserManagementTest(UsersEndpointTestCase):
    def test_all_users_are_listed(self):
        self.cursor.fetchall.return_value = [{'id': 1, 'username': 'root'}]
        response = self.client.get('/api/users', headers=self.headers)
        self.assertEqual(response.json(), [{'id': 1, 'username': 'root'}])

    def test_a_new_user_gets_the_default_role_and_never_admin(self):
        self.cursor.fetchone.return_value = None  # no account carries the name in any case
        self.cursor.lastrowid = 5
        with patch.object(users_router.rbac, 'get_role_by_name', return_value={'id': 2}) as get_role:
            response = self.client.post(
                '/api/users', headers=self.headers, json={'username': 'newbie', 'is_admin': True}
            )
        self.assertEqual(response.json(), {'status': 'ok', 'id': 5})
        self.assertEqual(get_role.call_args.args[1], users_router.rbac.DEFAULT_ROLE_NAME)
        self.assertFalse(self.cursor.execute.call_args.args[1][2])

    def test_a_new_user_without_a_role_table_entry_gets_no_role(self):
        self.cursor.fetchone.return_value = None  # no account carries the name in any case
        with patch.object(users_router.rbac, 'get_role_by_name', return_value=None):
            self.client.post('/api/users', headers=self.headers, json={'username': 'newbie'})
        self.assertIsNone(self.cursor.execute.call_args.args[1][3])

    def test_a_supplied_password_is_stored_hashed(self):
        self.cursor.fetchone.return_value = None  # no account carries the name in any case
        with patch.object(users_router.rbac, 'get_role_by_name', return_value={'id': 2}):
            self.client.post('/api/users', headers=self.headers, json={'username': 'newbie', 'password': 'hunter2'})
        stored = self.cursor.execute.call_args.args[1][5]
        self.assertNotEqual(stored, 'hunter2')
        self.assertTrue(stored.startswith('$2'))

    def test_the_roles_are_listed(self):
        self.cursor.fetchall.return_value = [{'id': 1, 'name': 'admin'}]
        self.assertEqual(self.client.get('/api/users/roles', headers=self.headers).status_code, 200)

    def test_a_role_can_be_assigned(self):
        with (
            patch.object(users_router.rbac, 'get_role_by_name', return_value={'id': 1}),
            patch.object(users_router.rbac, 'record_audit_event') as audit,
        ):
            response = self.client.put('/api/users/4/role', headers=self.headers, json={'role': 'admin'})
        self.assertEqual(response.json(), {'status': 'ok'})
        self.assertEqual(audit.call_args.args[1], 'user.role_assigned')

    def test_assigning_an_unknown_role_is_a_not_found(self):
        with patch.object(users_router.rbac, 'get_role_by_name', return_value=None):
            response = self.client.put('/api/users/4/role', headers=self.headers, json={'role': 'wizard'})
        self.assertEqual(response.status_code, 404)

    def test_a_user_can_be_enabled(self):
        with (
            patch.object(users_router.rbac, 'record_audit_event') as audit,
            patch.object(users_router, 'notify_server_sync_users') as notify,
        ):
            response = self.client.post('/api/users/4/enable', headers=self.headers)
        self.assertEqual(response.json(), {'status': 'ok'})
        self.assertIn('enabled = TRUE', self.statements()[0])
        self.assertEqual(audit.call_args.args[1], 'user.enabled')
        notify.assert_called_once()

    def test_a_user_can_be_disabled(self):
        with (
            patch.object(users_router.rbac, 'record_audit_event'),
            patch.object(users_router, 'notify_server_sync_users') as notify,
        ):
            self.client.post('/api/users/4/disable', headers=self.headers)
        self.assertTrue(any('enabled = FALSE' in s for s in self.statements()))
        # LMS caches a granted password for five minutes; the poke is what ends that early.
        # Without it a disabled listener keeps playing until the cache happens to lapse.
        notify.assert_called_once()

    def test_the_sync_poke_comes_after_the_commit(self):
        # LMS answers the poke by fetching /api/users/; a poke before the commit would let it
        # read the old row and cache the account as enabled all over again.
        order = []
        self.conn.commit.side_effect = lambda: order.append('commit')
        with (
            patch.object(users_router.rbac, 'record_audit_event'),
            patch.object(users_router, 'notify_server_sync_users', side_effect=lambda: order.append('notify')),
        ):
            self.client.post('/api/users/4/disable', headers=self.headers)
        self.assertEqual(order, ['commit', 'notify'])

    def test_revoking_sessions_clears_the_api_key_and_the_refresh_tokens(self):
        with patch.object(users_router.rbac, 'record_audit_event'):
            response = self.client.post('/api/users/4/sessions/revoke', headers=self.headers)
        self.assertEqual(response.json(), {'status': 'ok'})
        self.assertIn('api_key = NULL', self.statements()[0])
        self.assertIn('revoked_at = NOW()', self.statements()[1])

    def test_the_linked_identities_are_listed(self):
        self.cursor.fetchall.return_value = [{'id': 1, 'provider': 'google'}]
        response = self.client.get('/api/users/4/identities', headers=self.headers)
        self.assertEqual(response.json()[0]['provider'], 'google')

    def test_a_password_change_is_stored_hashed(self):
        self.client.post('/api/users/4/password', headers=self.headers, json={'password': 'hunter2'})
        stored = self.cursor.execute.call_args.args[1][0]
        self.assertTrue(stored.startswith('$2'))


class ListenBrainzTest(UsersEndpointTestCase):
    def test_a_linked_account_is_returned(self):
        self.cursor.fetchone.return_value = {'lb_username': 'user', 'lb_token': 'tok'}
        response = self.client.get('/api/users/4/listenbrainz', headers=self.headers)
        self.assertEqual(response.json()['lb_username'], 'user')

    def test_an_unlinked_account_returns_empty_values(self):
        self.cursor.fetchone.return_value = None
        response = self.client.get('/api/users/4/listenbrainz', headers=self.headers)
        self.assertEqual(response.json(), {'lb_username': '', 'lb_token': ''})

    def test_an_account_can_be_linked(self):
        response = self.client.post(
            '/api/users/4/listenbrainz', headers=self.headers, json={'lb_username': 'user', 'lb_token': 'tok'}
        )
        self.assertEqual(response.json(), {'status': 'ok'})
        self.assertEqual(self.cursor.execute.call_args.args[1], (4, 'user', 'tok'))


class AppSettingsTest(UsersEndpointTestCase):
    def test_stored_settings_are_returned(self):
        self.cursor.fetchone.return_value = {'settings_json': '{"theme":"dark"}', 'updated_at': '2026-01-01'}
        response = self.client.get('/api/users/4/settings/ultrasonic', headers=self.headers)
        self.assertEqual(response.json()['settings'], '{"theme":"dark"}')

    def test_an_app_without_stored_settings_returns_nothing(self):
        self.cursor.fetchone.return_value = None
        response = self.client.get('/api/users/4/settings/ultrasonic', headers=self.headers)
        self.assertEqual(response.json(), {'settings': None})

    def test_settings_can_be_stored(self):
        response = self.client.post(
            '/api/users/4/settings/ultrasonic', headers=self.headers, json={'settings': '{"theme":"dark"}'}
        )
        self.assertEqual(response.json(), {'status': 'ok'})
        self.assertEqual(self.cursor.execute.call_args.args[1], (4, 'ultrasonic', '{"theme":"dark"}'))

    def test_storing_settings_for_an_unknown_user_is_a_not_found(self):
        # Without the existence check the insert fails on the foreign key and answers 500, which
        # reads like a broken server instead of a caller naming a user that is not there.
        self.cursor.fetchone.return_value = None
        response = self.client.post(
            '/api/users/0/settings/ultrasonic', headers=self.headers, json={'settings': '{"theme":"dark"}'}
        )
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('INSERT', self.cursor.execute.call_args.args[0])


class MergeSettingsBlobTest(unittest.TestCase):
    """The pure top-level merge behind PATCH /api/users/{id}/settings/{app_id}."""

    def test_named_keys_are_set_and_every_other_key_is_kept(self):
        merged = users_router.merge_settings_blob('{"language":"nl","favoriteGenres":["A"]}', {'trackPageSize': 50}, [])
        self.assertEqual(merged, {'language': 'nl', 'favoriteGenres': ['A'], 'trackPageSize': 50})

    def test_a_value_replaces_the_stored_one_whole_rather_than_merging_into_it(self):
        merged = users_router.merge_settings_blob(
            '{"setResume":{"work:1":{},"work:2":{}}}', {'setResume': {'work:3': {}}}, []
        )
        self.assertEqual(merged, {'setResume': {'work:3': {}}})

    def test_removed_keys_are_gone_and_a_missing_one_is_no_error(self):
        merged = users_router.merge_settings_blob('{"a":1,"b":2}', {}, ['a', 'never-there'])
        self.assertEqual(merged, {'b': 2})

    def test_a_missing_broken_or_non_object_blob_counts_as_empty(self):
        for stored in (None, '', 'garbage', '[1,2]', 'null', '"text"'):
            with self.subTest(stored=stored):
                self.assertEqual(users_router.merge_settings_blob(stored, {'a': 1}, []), {'a': 1})

    def test_null_is_a_value_like_any_other(self):
        # Removing is explicit (`remove`), so a client can still store a JSON null on purpose.
        self.assertEqual(users_router.merge_settings_blob('{"a":1}', {'a': None}, []), {'a': None})


class PatchAppSettingsTest(UsersEndpointTestCase):
    """PATCH /api/users/{id}/settings/{app_id}: a locked per-key read-merge-write."""

    def patch(self, body, user_id=4):
        return self.client.patch(f'/api/users/{user_id}/settings/frontend', headers=self.headers, json=body)

    def write(self):
        """The (statement, params) of the INSERT or UPDATE the endpoint wrote the blob with."""
        for call in self.cursor.execute.call_args_list:
            statement = call.args[0]
            if statement.startswith(('UPDATE user_app_settings', 'INSERT INTO user_app_settings')):
                return statement, call.args[1]
        return None

    def test_only_the_named_keys_change_and_the_rest_of_the_blob_is_kept(self):
        self.cursor.fetchone.side_effect = [
            {'id': 4},
            {'settings_json': '{"language":"nl","favoriteGenres":["Hardcore"]}'},
            {'updated_at': '2026-09-26 12:00:00'},
        ]
        response = self.patch({'set': {'trackPageSize': 50}, 'remove': ['language']})

        self.assertEqual(response.status_code, 200, response.text)
        statement, params = self.write()
        self.assertTrue(statement.startswith('UPDATE'))
        self.assertEqual(json.loads(params[0]), {'favoriteGenres': ['Hardcore'], 'trackPageSize': 50})
        self.assertEqual(params[1:], (4, 'frontend'))
        body = response.json()
        self.assertEqual(json.loads(body['settings']), {'favoriteGenres': ['Hardcore'], 'trackPageSize': 50})
        self.assertEqual(body['updated_at'], '2026-09-26 12:00:00')
        self.assertEqual(body['status'], 'ok')

    def test_the_stored_blob_is_read_under_a_row_lock_inside_one_transaction(self):
        # Without FOR UPDATE two concurrent writers read the same blob and the second UPDATE
        # drops the first one's key -- exactly the lost update the endpoint exists to prevent.
        self.cursor.fetchone.side_effect = [{'id': 4}, {'settings_json': '{}'}, {'updated_at': 'x'}]
        self.patch({'set': {'a': 1}})

        reads = [s for s in self.statements() if s.startswith('SELECT settings_json')]
        self.assertEqual(len(reads), 1)
        self.assertTrue(reads[0].rstrip().endswith('FOR UPDATE'))
        self.conn.begin.assert_called_once()
        self.conn.commit.assert_called_once()
        self.conn.rollback.assert_not_called()

    def test_an_account_without_a_blob_gets_one_inserted(self):
        self.cursor.fetchone.side_effect = [{'id': 4}, None, {'updated_at': 'x'}]
        response = self.patch({'set': {'language': 'en'}})

        self.assertEqual(response.status_code, 200, response.text)
        statement, params = self.write()
        self.assertTrue(statement.startswith('INSERT'))
        self.assertEqual(params[:2], (4, 'frontend'))
        self.assertEqual(json.loads(params[2]), {'language': 'en'})

    def test_an_unknown_user_is_a_not_found_and_nothing_is_written(self):
        self.cursor.fetchone.side_effect = [None]
        response = self.patch({'set': {'a': 1}}, user_id=99)

        self.assertEqual(response.status_code, 404)
        self.assertIsNone(self.write())
        self.conn.rollback.assert_called_once()

    def test_a_key_both_set_and_removed_is_refused_before_the_database(self):
        response = self.patch({'set': {'a': 1}, 'remove': ['a']})

        self.assertEqual(response.status_code, 422)
        self.cursor.execute.assert_not_called()

    def test_set_must_be_an_object_and_remove_a_list_of_strings(self):
        for body in ({'set': [1, 2]}, {'set': 'text'}, {'remove': 'a'}, {'remove': [{'a': 1}]}):
            with self.subTest(body=body):
                self.assertEqual(self.patch(body).status_code, 422)

    def test_a_user_may_not_patch_another_users_settings(self):
        auth = {'type': 'user', 'user': {'id': 5}, 'permissions': set()}
        app.dependency_overrides[users_router.verify_api_key] = lambda: auth
        self.addCleanup(app.dependency_overrides.pop, users_router.verify_api_key, None)

        response = self.patch({'set': {'a': 1}}, user_id=4)

        self.assertEqual(response.status_code, 403)
        self.cursor.execute.assert_not_called()

    def test_a_deadlock_is_retried_from_the_top(self):
        # Two first writes of a missing row both hold its gap lock; MariaDB kills one with 1213.
        # The retry reads the row again -- by then holding the other writer's key -- and merges.
        self.cursor.fetchone.side_effect = [
            {'id': 4},
            None,
            {'id': 4},
            {'settings_json': '{"other":true}'},
            {'updated_at': 'x'},
        ]
        attempts = []

        def execute(statement, _params=None):
            if statement.startswith('INSERT INTO user_app_settings'):
                attempts.append(statement)
                raise users_router.pymysql.err.OperationalError(1213, 'Deadlock found')

        self.cursor.execute.side_effect = execute
        response = self.patch({'set': {'mine': 1}})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(attempts), 1)
        self.assertEqual(json.loads(response.json()['settings']), {'other': True, 'mine': 1})
        self.assertEqual(self.conn.rollback.call_count, 1)

    def test_no_plain_read_comes_before_the_row_lock(self):
        # A plain SELECT opens the read view before the FOR UPDATE has waited for another writer,
        # and snapshot isolation then refuses the UPDATE with 1020 -- what CI caught on MariaDB 13.
        self.cursor.fetchone.side_effect = [{'id': 4}, {'settings_json': '{}'}, {'updated_at': 'x'}]
        self.patch({'set': {'a': 1}})

        statements = self.statements()
        lock = next(i for i, s in enumerate(statements) if s.startswith('SELECT settings_json'))
        for statement in statements[:lock]:
            self.assertRegex(statement, r'(LOCK IN SHARE MODE|FOR UPDATE)\s*$')

    def test_a_record_changed_since_last_read_is_retried(self):
        self.cursor.fetchone.side_effect = [
            {'id': 4},
            {'settings_json': '{}'},
            {'id': 4},
            {'settings_json': '{}'},
            {'updated_at': 'x'},
        ]
        failures = []

        def execute(statement, _params=None):
            if statement.startswith('UPDATE user_app_settings') and not failures:
                failures.append(statement)
                raise users_router.pymysql.err.OperationalError(1020, 'Record has changed since last read')

        self.cursor.execute.side_effect = execute
        response = self.patch({'set': {'a': 1}})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.conn.begin.call_count, 2)

    def test_a_write_that_keeps_colliding_gives_up_after_three_attempts(self):
        self.cursor.fetchone.side_effect = lambda: {'id': 4, 'settings_json': '{}'}

        def execute(statement, _params=None):
            if statement.startswith('UPDATE user_app_settings'):
                raise users_router.pymysql.err.OperationalError(1213, 'Deadlock found')

        self.cursor.execute.side_effect = execute
        client = TestClient(app, raise_server_exceptions=False)
        response = client.patch('/api/users/4/settings/frontend', headers=self.headers, json={'set': {'a': 1}})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.conn.begin.call_count, 3)

    def test_other_database_errors_are_not_retried(self):
        self.cursor.fetchone.side_effect = lambda: {'id': 4, 'settings_json': '{}'}

        def execute(statement, _params=None):
            if statement.startswith('UPDATE user_app_settings'):
                raise users_router.pymysql.err.OperationalError(2013, 'Lost connection')

        self.cursor.execute.side_effect = execute
        client = TestClient(app, raise_server_exceptions=False)
        response = client.patch('/api/users/4/settings/frontend', headers=self.headers, json={'set': {'a': 1}})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.conn.begin.call_count, 1)


class DeleteUserTest(UsersEndpointTestCase):
    def setUp(self):
        super().setUp()
        notify = patch.object(users_router, 'notify_server_sync_users')
        self.notify = notify.start()
        self.addCleanup(notify.stop)

    def test_the_server_is_told_to_sync_after_the_delete_commits(self):
        # LMS disables an account that has gone from /api/users/; until it syncs, the deleted
        # account's Subsonic key keeps working. A poke before the commit would find it still there.
        self.cursor.fetchone.return_value = {'id': 4, 'username': 'user', 'role_id': 2}
        order = []
        self.conn.commit.side_effect = lambda: order.append('commit')
        self.notify.side_effect = lambda: order.append('notify')
        with (
            patch.object(users_router.rbac, 'get_role_by_name', return_value={'id': 1}),
            patch.object(users_router.rbac, 'record_audit_event'),
        ):
            response = self.client.delete('/api/users/4', headers=self.headers)
        self.assertEqual(response.json(), {'status': 'ok'})
        self.assertEqual(order, ['commit', 'notify'])

    def test_a_refused_delete_does_not_poke_the_server(self):
        self.cursor.fetchone.return_value = None
        self.client.delete('/api/users/4', headers=self.headers)
        self.notify.assert_not_called()

    def test_a_user_and_all_its_dependent_rows_are_removed(self):
        self.cursor.fetchone.return_value = {'id': 4, 'username': 'user', 'role_id': 2}
        with (
            patch.object(users_router.rbac, 'get_role_by_name', return_value={'id': 1}),
            patch.object(users_router.rbac, 'record_audit_event'),
        ):
            response = self.client.delete('/api/users/4', headers=self.headers)
        self.assertEqual(response.json(), {'status': 'ok'})
        for table in (
            'user_identities',
            'user_refresh_tokens',
            'dynamic_playlists',
            'user_app_settings',
            'user_listenbrainz_accounts',
        ):
            self.assertTrue(any(f'DELETE FROM {table}' in s for s in self.statements()))

    def test_deleting_an_unknown_user_is_a_not_found(self):
        self.cursor.fetchone.return_value = None
        response = self.client.delete('/api/users/4', headers=self.headers)
        self.assertEqual(response.status_code, 404)

    def test_the_last_admin_account_cannot_be_deleted(self):
        # `cnt` counts the *other* enabled admins.
        self.cursor.fetchone.side_effect = [{'id': 1, 'username': 'root', 'role_id': 1}, {'cnt': 0}]
        with patch.object(users_router.rbac, 'get_role_by_name', return_value={'id': 1}):
            response = self.client.delete('/api/users/1', headers=self.headers)
        self.assertEqual(response.status_code, 409)

    def test_one_of_several_admins_can_be_deleted(self):
        self.cursor.fetchone.side_effect = [{'id': 1, 'username': 'root', 'role_id': 1}, {'cnt': 2}]
        with (
            patch.object(users_router.rbac, 'get_role_by_name', return_value={'id': 1}),
            patch.object(users_router.rbac, 'record_audit_event'),
        ):
            response = self.client.delete('/api/users/1', headers=self.headers)
        self.assertEqual(response.status_code, 200)

    def test_an_unexpected_database_failure_is_reported_as_a_server_error(self):
        self.cursor.fetchone.return_value = {'id': 4, 'username': 'user', 'role_id': 2}
        self.cursor.execute.side_effect = [None, RuntimeError('constraint')]
        with patch.object(users_router.rbac, 'get_role_by_name', return_value=None):
            response = self.client.delete('/api/users/4', headers=self.headers)
        self.assertEqual(response.status_code, 500)
        self.assertIn('Delete failed', response.json()['detail'])


class ServerSyncTest(unittest.TestCase):
    def test_the_sync_endpoint_reports_how_many_users_were_synced(self):
        client = TestClient(app)
        with patch.object(users_router, 'run_lms_db_sync', return_value=3):
            response = client.post('/api/users/sync/muma-server', headers={'x-api-key': API_KEY})
        self.assertEqual(response.json()['synced'], 3)

    def test_every_configured_server_host_is_notified(self):
        with (
            patch.object(users_router, 'MUMA_SERVER_HOSTS', 'a:5082, b:5082'),
            patch.object(users_router, 'requests') as http,
            patch('builtins.print'),
        ):
            users_router.notify_server_sync_users()
        self.assertEqual(http.post.call_count, 2)

    def test_without_configured_hosts_nothing_is_notified(self):
        with patch.object(users_router, 'MUMA_SERVER_HOSTS', ''), patch.object(users_router, 'requests') as http:
            users_router.notify_server_sync_users()
        http.post.assert_not_called()

    def test_a_host_that_cannot_be_reached_does_not_stop_the_others(self):
        with (
            patch.object(users_router, 'MUMA_SERVER_HOSTS', 'a:5082,b:5082'),
            patch.object(users_router, 'requests') as http,
            patch('builtins.print'),
        ):
            http.post.side_effect = [RuntimeError('down'), None]
            users_router.notify_server_sync_users()
        self.assertEqual(http.post.call_count, 2)

    def test_playlists_are_synced_for_users_known_on_both_sides(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = {'id': 7}
        sqlite_cursor = MagicMock()
        sqlite_cursor.fetchall.side_effect = [
            [(0, 'smart_params')],
            [(3, 'lms-user', 'Smart list', '{}')],
        ]
        users_router._sync_server_playlists(cursor, sqlite_cursor, 'lms')
        self.assertEqual(cursor.execute.call_args.args[1][0], 7)

    def test_a_server_without_smart_playlists_is_skipped(self):
        cursor = MagicMock()
        sqlite_cursor = MagicMock()
        sqlite_cursor.fetchall.return_value = [(0, 'name')]
        users_router._sync_server_playlists(cursor, sqlite_cursor, 'lms')
        cursor.execute.assert_not_called()

    def test_a_playlist_belonging_to_an_unknown_user_is_skipped(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        sqlite_cursor = MagicMock()
        sqlite_cursor.fetchall.side_effect = [
            [(0, 'smart_params')],
            [(3, 'lms-user', 'Smart list', '{}')],
        ]
        users_router._sync_server_playlists(cursor, sqlite_cursor, 'lms')
        self.assertEqual(len(cursor.execute.call_args_list), 1)

    def test_a_failing_playlist_sync_is_swallowed(self):
        sqlite_cursor = MagicMock()
        sqlite_cursor.execute.side_effect = RuntimeError('no such table')
        with patch('builtins.print'):
            users_router._sync_server_playlists(MagicMock(), sqlite_cursor, 'lms')  # must not raise

    def test_user_rows_are_never_pulled_back_from_the_server(self):
        self.assertEqual(users_router._sync_server_users(MagicMock(), MagicMock()), 0)


class SyncSingleServerDbTest(unittest.TestCase):
    def test_a_sqlite_database_is_opened_read_and_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, 'lms.db')
            sqlite3.connect(db_path).close()
            muma_conn = MagicMock()
            with (
                patch('services.music_manager.routers.artist_images.sync_artist_images_to_server') as sync_images,
                patch('builtins.print'),
            ):
                users_router.sync_single_server_db(muma_conn, db_path, 'lms')
            sync_images.assert_called_once()
            # The server's name reaches the image sync, so its log lines say which server.
            self.assertEqual(sync_images.call_args.args[2], 'lms')
        self.assertEqual(muma_conn.commit.call_count, 2)

    def test_an_unreadable_database_does_not_raise(self):
        with patch('builtins.print'):
            self.assertEqual(users_router.sync_single_server_db(MagicMock(), '/does/not/exist.db', 'lms'), 0)


class RevokeSessionsAtomicityTest(UsersEndpointTestCase):
    """The api_key, the refresh tokens and the audit row land together (bug report 115)."""

    def revoke(self):
        return self.client.post('/api/users/4/sessions/revoke', headers=self.headers)

    def test_the_revocation_and_its_audit_row_are_one_transaction(self):
        log = transaction_log(self.conn, self.cursor)
        self.assertEqual(self.revoke().json(), {'status': 'ok'})
        assert_atomic(self, log, 'api_key = NULL', 'UPDATE user_refresh_tokens', 'INSERT INTO audit_events')

    def test_a_failing_audit_row_rolls_the_revocation_back(self):
        """Without it the refresh tokens could stay valid, or the audit log missed a revocation."""
        log = transaction_log(self.conn, self.cursor, fail_on='INSERT INTO audit_events')
        with self.assertRaises(RuntimeError):
            self.revoke()
        assert_rolled_back(self, log)


if __name__ == '__main__':
    unittest.main()
