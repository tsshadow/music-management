"""End-to-end coverage of the /api/users and /api/auth endpoints.

Everything runs against the FastAPI TestClient with the system API key, which
``verify_api_key`` accepts outright, so these tests exercise the endpoint bodies
rather than the permission wiring (that already lives in test_rbac.py).
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.easyid3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())


import services.music_manager.routers.users as users_router

users_router.run_lms_db_sync = lambda: None
import services.music_manager.database

services.music_manager.database.get_db_connection = MagicMock(return_value=None)

from fastapi.testclient import TestClient

from services.music_manager.main import app

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
        self.assertEqual(response.status_code, 400)

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
        query, params = self.build(json.dumps({}))
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
        query, params = self.build(json.dumps({'genres': [], 'rules': [{'column': 'genre', 'value': 'Uptempo'}]}))
        self.assertEqual(params.count('Uptempo'), 2)

    def test_a_rule_repeating_a_selected_genre_is_not_added_twice(self):
        query, params = self.build(
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
        self.cursor.lastrowid = 5
        with patch.object(users_router.rbac, 'get_role_by_name', return_value={'id': 2}) as get_role:
            response = self.client.post(
                '/api/users', headers=self.headers, json={'username': 'newbie', 'is_admin': True}
            )
        self.assertEqual(response.json(), {'status': 'ok', 'id': 5})
        self.assertEqual(get_role.call_args.args[1], users_router.rbac.DEFAULT_ROLE_NAME)
        self.assertFalse(self.cursor.execute.call_args.args[1][2])

    def test_a_new_user_without_a_role_table_entry_gets_no_role(self):
        with patch.object(users_router.rbac, 'get_role_by_name', return_value=None):
            self.client.post('/api/users', headers=self.headers, json={'username': 'newbie'})
        self.assertIsNone(self.cursor.execute.call_args.args[1][3])

    def test_a_supplied_password_is_stored_hashed(self):
        with patch.object(users_router.rbac, 'get_role_by_name', return_value={'id': 2}):
            self.client.post('/api/users', headers=self.headers, json={'username': 'newbie', 'password': 'hunter2'})
        stored = self.cursor.execute.call_args.args[1][5]
        self.assertNotEqual(stored, 'hunter2')
        self.assertTrue(stored.startswith('$2'))

    def test_the_roles_are_listed(self):
        self.cursor.fetchall.return_value = [{'id': 1, 'name': 'admin'}]
        self.assertEqual(self.client.get('/api/users/roles', headers=self.headers).status_code, 200)

    def test_the_permissions_are_listed(self):
        self.cursor.fetchall.return_value = [{'id': 1, 'name': 'users.read'}]
        self.assertEqual(self.client.get('/api/users/permissions', headers=self.headers).status_code, 200)

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
        self.assertIn('enabled = FALSE', self.statements()[0])
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
        response = self.client.get('/api/users/4/lb-account', headers=self.headers)
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


class DeleteUserTest(UsersEndpointTestCase):
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
        self.cursor.fetchone.side_effect = [{'id': 1, 'username': 'root', 'role_id': 1}, {'cnt': 1}]
        with patch.object(users_router.rbac, 'get_role_by_name', return_value={'id': 1}):
            response = self.client.delete('/api/users/1', headers=self.headers)
        self.assertEqual(response.status_code, 400)

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
        self.assertIn('Verwijderen mislukt', response.json()['detail'])


class ServerSyncTest(unittest.TestCase):
    def test_the_sync_endpoint_reports_how_many_users_were_synced(self):
        client = TestClient(app)
        with patch.object(users_router, 'run_lms_db_sync', return_value=3):
            response = client.post('/api/users/sync/lms', headers={'x-api-key': API_KEY})
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
        self.assertEqual(muma_conn.commit.call_count, 2)

    def test_an_unreadable_database_does_not_raise(self):
        with patch('builtins.print'):
            self.assertEqual(users_router.sync_single_server_db(MagicMock(), '/does/not/exist.db', 'lms'), 0)


if __name__ == '__main__':
    unittest.main()
