"""Coverage for the /api management router: rules, accounts, system info and proxies."""

import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector', 'Cache')


import services.common.Helpers.RescanInvalidator as rescan_invalidator_module
import services.music_manager.routers.users as users_router
from services.music_manager.api_key import resolve_system_api_key

users_router.run_lms_db_sync = lambda: None

from fastapi import HTTPException
from fastapi.testclient import TestClient

from services.common.Helpers import Cache
from services.common.Helpers.ReleaseFolder import CONFLICT, MOVED
from services.music_manager.main import app
from services.music_manager.routers import management as management_router
from services.music_manager.tests.scripted_cursor import assert_atomic, assert_rolled_back, transaction_log

API_KEY = resolve_system_api_key()


class ManagementTestCase(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.headers = {'x-api-key': API_KEY}
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = self.cursor
        self.conn.cursor.return_value.__exit__.return_value = False
        patcher = patch.object(management_router, 'get_db_connection', return_value=self.conn)
        patcher.start()
        self.addCleanup(patcher.stop)

    def statements(self):
        return [call.args[0] for call in self.cursor.execute.call_args_list]


class AuthTest(unittest.TestCase):
    def test_a_request_without_a_key_is_unauthorized(self):
        self.assertEqual(TestClient(app).get('/api/artists').status_code, 401)

    def test_a_user_key_that_verifies_is_accepted(self):
        with (
            patch.object(users_router, 'verify_token', return_value={'status': 'ok', 'type': 'user'}),
            patch.object(management_router, 'get_db_connection', return_value=None),
        ):
            response = TestClient(app).get('/api/artists', headers={'x-api-key': 'user-key'})
        self.assertEqual(response.status_code, 500)

    def test_a_key_that_does_not_verify_is_rejected(self):
        with patch.object(users_router, 'verify_token', side_effect=HTTPException(status_code=403)):
            response = TestClient(app).get('/api/artists', headers={'x-api-key': 'bad'})
        self.assertEqual(response.status_code, 403)


class GenreRulesTest(ManagementTestCase):
    def test_the_genre_rules_are_returned_with_the_ignore_list(self):
        self.cursor.fetchall.side_effect = [[{'id': 1, 'name': 'Hardcore'}], [{'name': 'Misc'}]]
        self.cursor.fetchone.return_value = ('rules_ignored_genres',)
        body = self.client.get('/api/rules', headers=self.headers).json()
        self.assertEqual(body['genres'][0]['name'], 'Hardcore')
        self.assertEqual(body['ignored_genres'], [{'name': 'Misc'}])

    def test_a_deployment_without_the_ignore_table_returns_an_empty_list(self):
        self.cursor.fetchall.return_value = []
        self.cursor.fetchone.return_value = None
        body = self.client.get('/api/rules', headers=self.headers).json()
        self.assertEqual(body['ignored_genres'], [])

    def test_a_database_outage_is_reported_as_a_server_error(self):
        with patch.object(management_router, 'get_db_connection', return_value=None):
            self.assertEqual(self.client.get('/api/rules', headers=self.headers).status_code, 500)


class SearchTest(ManagementTestCase):
    def test_artists_are_searched_with_a_wildcard(self):
        self.cursor.fetchall.return_value = [{'id': 1, 'name': 'Angerfist'}]
        response = self.client.get('/api/artists?q=anger', headers=self.headers)
        self.assertEqual(response.json()[0]['name'], 'Angerfist')
        self.assertEqual(self.cursor.execute.call_args.args[1], ('%anger%',))

    def test_labels_are_searched_with_a_wildcard(self):
        self.cursor.fetchall.return_value = [{'id': 1, 'name': 'Scantraxx'}]
        response = self.client.get('/api/labels?q=scan', headers=self.headers)
        self.assertEqual(response.json()[0]['name'], 'Scantraxx')


class ConfigAndDocsTest(ManagementTestCase):
    def test_the_config_reports_the_database_and_version(self):
        with patch.dict('os.environ', {'DB_HOST': 'db.internal', 'DB_DB': 'muma'}):
            body = self.client.get('/api/config', headers=self.headers).json()
        self.assertEqual(body['DB_HOST'], 'db.internal')
        self.assertEqual(body['DB_NAME'], 'muma')
        self.assertIn('VERSION', body)

    def test_a_missing_version_file_falls_back_to_a_default(self):
        with patch('builtins.open', side_effect=FileNotFoundError):
            body = self.client.get('/api/config', headers=self.headers).json()
        self.assertEqual(body['VERSION'], '1.3.0')

    def test_the_about_page_is_rendered_from_the_readme(self):
        with (
            patch.object(management_router.os.path, 'exists', return_value=True),
            patch('builtins.open', unittest.mock.mock_open(read_data='# Title')),
            patch.object(management_router, 'markdown') as md,
        ):
            md.markdown.return_value = '<h1>Title</h1>'
            response = self.client.get('/api/about', headers=self.headers)
        self.assertIn('<h1>Title</h1>', response.text)

    def test_a_missing_readme_still_renders_a_page(self):
        with (
            patch.object(management_router.os.path, 'exists', return_value=False),
            patch.object(management_router, 'markdown') as md,
        ):
            md.markdown.return_value = '<h1>Music Manager</h1>'
            response = self.client.get('/api/about', headers=self.headers)
        self.assertEqual(response.status_code, 200)

    def test_the_release_notes_and_changelog_are_served(self):
        with (
            patch.object(management_router, 'get_release_notes', return_value='notes'),
            patch.object(management_router, 'get_changelog', return_value='log'),
        ):
            body = self.client.get('/api/notes', headers=self.headers).json()
        self.assertEqual(body, {'release_notes': 'notes', 'changelog': 'log'})

    def test_the_all_notes_alias_serves_the_same_payload(self):
        with (
            patch.object(management_router, 'get_release_notes', return_value='notes'),
            patch.object(management_router, 'get_changelog', return_value='log'),
        ):
            body = self.client.get('/api/all-notes', headers=self.headers).json()
        self.assertEqual(body['release_notes'], 'notes')

    def test_every_python_service_reports_the_same_version(self):
        with patch.object(management_router, 'get_version', return_value='0.0.99'):
            body = self.client.get('/api/versions', headers=self.headers).json()
        self.assertEqual(body['music-manager'], '0.0.99')
        self.assertEqual(body['muma-tagger'], '0.0.99')
        self.assertEqual(body['ultrasonic'], 'unknown')


class SystemTest(ManagementTestCase):
    def make_container(self, name, image_tags=('muma:latest',)):
        container = MagicMock()
        container.name = name
        container.short_id = 'abc123'
        container.status = 'running'
        container.image.tags = list(image_tags)
        return container

    def test_only_the_projects_own_containers_are_listed(self):
        with patch.object(management_router, 'docker') as docker:
            docker.from_env.return_value.containers.list.return_value = [
                self.make_container('muma-manager'),
                self.make_container('unrelated-nginx'),
            ]
            body = self.client.get('/api/system/containers', headers=self.headers).json()
        self.assertEqual([c['name'] for c in body], ['muma-manager'])

    def test_a_container_without_an_image_tag_is_reported_as_unknown(self):
        with patch.object(management_router, 'docker') as docker:
            docker.from_env.return_value.containers.list.return_value = [
                self.make_container('muma-manager', image_tags=())
            ]
            body = self.client.get('/api/system/containers', headers=self.headers).json()
        self.assertEqual(body[0]['image'], 'unknown')

    def test_an_unreachable_docker_daemon_is_a_server_error(self):
        with patch.object(management_router, 'docker') as docker:
            docker.from_env.side_effect = RuntimeError('no socket')
            self.assertEqual(self.client.get('/api/system/containers', headers=self.headers).status_code, 500)

    def test_container_logs_are_decoded(self):
        with patch.object(management_router, 'docker') as docker:
            docker.from_env.return_value.containers.get.return_value.name = 'muma-manager'
            docker.from_env.return_value.containers.get.return_value.logs.return_value = b'hello'
            body = self.client.get('/api/system/logs/muma-manager', headers=self.headers).json()
        self.assertEqual(body['logs'], 'hello')

    def test_a_docker_failure_on_a_listed_container_is_a_server_error(self):
        with patch.object(management_router, 'docker') as docker:
            docker.from_env.return_value.containers.get.side_effect = RuntimeError('not found')
            self.assertEqual(self.client.get('/api/system/logs/muma-gone', headers=self.headers).status_code, 500)

    def test_logs_of_a_container_outside_the_list_are_refused(self):
        with patch.object(management_router, 'docker') as docker:
            response = self.client.get('/api/system/logs/nginx-proxy', headers=self.headers)
        self.assertEqual(response.status_code, 404)
        docker.from_env.assert_not_called()

    def test_a_listed_name_resolving_to_another_container_is_refused(self):
        # Docker resolves id prefixes too; the resolved container's own name decides.
        with patch.object(management_router, 'docker') as docker:
            docker.from_env.return_value.containers.get.return_value.name = 'password manager'
            response = self.client.get('/api/system/logs/db', headers=self.headers)
        self.assertEqual(response.status_code, 404)

    def test_the_activity_feed_returns_both_recently_added_and_recently_tagged(self):
        self.cursor.fetchall.side_effect = [[{'title': 'A'}], [{'title': 'B'}]]
        body = self.client.get('/api/system/activity?limit=5', headers=self.headers).json()
        self.assertEqual(body['recent_added'][0]['title'], 'A')
        self.assertEqual(body['recent_tagged'][0]['title'], 'B')
        self.assertEqual(self.cursor.execute.call_args.args[1], (5,))


class DownloadAccountsTest(ManagementTestCase):
    def test_the_soundcloud_accounts_are_listed(self):
        self.cursor.fetchall.return_value = [{'name': 'artist', 'soundcloud_id': 1}]
        response = self.client.get('/api/soundcloud', headers=self.headers)
        self.assertEqual(response.json()[0]['name'], 'artist')

    def test_a_soundcloud_account_can_be_added(self):
        response = self.client.post(
            '/api/soundcloud', headers=self.headers, json={'name': 'artist', 'soundcloud_id': 7}
        )
        self.assertEqual(response.json()['status'], 'ok')
        self.assertEqual(self.cursor.execute.call_args.args[1], ('artist', 7))

    def test_a_soundcloud_account_can_be_removed(self):
        response = self.client.delete('/api/soundcloud/artist', headers=self.headers)
        self.assertEqual(response.json(), {'status': 'ok'})
        self.assertIn('DELETE FROM downloads_soundcloud_accounts', self.statements()[0])

    def test_the_youtube_accounts_are_listed(self):
        self.cursor.fetchall.return_value = [{'name': 'channel', 'channel_id': 'abc'}]
        response = self.client.get('/api/youtube', headers=self.headers)
        self.assertEqual(response.json()[0]['name'], 'channel')

    def test_a_youtube_account_is_added_as_an_audio_download(self):
        response = self.client.post('/api/youtube', headers=self.headers, json={'name': 'channel'})
        self.assertEqual(response.json()['status'], 'ok')
        self.assertEqual(self.cursor.execute.call_args.args[1], ('channel', 'audio', 60))

    def test_a_youtube_account_can_be_added_as_a_video_download(self):
        """The duration floor keeps trailers and teasers out of an event channel."""
        response = self.client.post(
            '/api/youtube', headers=self.headers, json={'name': '@qdance', 'download_type': 'video'}
        )
        self.assertEqual(response.json()['status'], 'ok')
        self.assertEqual(self.cursor.execute.call_args.args[1], ('@qdance', 'video', 1200))

    def test_an_unknown_youtube_download_type_is_rejected(self):
        response = self.client.post(
            '/api/youtube', headers=self.headers, json={'name': 'channel', 'download_type': 'hologram'}
        )
        self.assertEqual(response.status_code, 400)

    def test_a_youtube_account_can_be_removed(self):
        response = self.client.delete('/api/youtube/channel', headers=self.headers)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_removing_one_form_of_a_channel_leaves_the_other(self):
        """A channel can hold both rows, so a delete without a type would take both."""
        response = self.client.delete('/api/youtube/@qdance?download_type=video', headers=self.headers)
        self.assertEqual(response.json(), {'status': 'ok'})
        self.assertEqual(self.cursor.execute.call_args.args[1], ('@qdance', 'video'))


class GenreCurationQueueTest(ManagementTestCase):
    def test_the_whole_table_is_returned_without_a_state_filter(self):
        self.cursor.fetchall.side_effect = [[{'id': 1, 'name': 'Hardcore'}], []]
        response = self.client.get('/api/rules/genres', headers=self.headers)
        self.assertEqual(response.json()[0]['name'], 'Hardcore')
        self.assertNotIn('WHERE g.state', self.statements()[0])

    def test_a_state_filter_narrows_the_query(self):
        self.cursor.fetchall.side_effect = [[{'id': 1, 'name': 'Upterror'}], []]
        self.client.get('/api/rules/genres?state=unknown', headers=self.headers)
        self.assertIn('WHERE g.state = %s', self.statements()[0])

    def test_an_unknown_state_is_rejected(self):
        response = self.client.get('/api/rules/genres?state=purple', headers=self.headers)
        self.assertEqual(response.status_code, 400)

    def test_the_rewrite_targets_are_attached_to_each_genre(self):
        self.cursor.fetchall.side_effect = [
            [{'id': 1, 'name': 'Upterror'}, {'id': 2, 'name': 'Hardcore'}],
            [
                {'genre_id': 1, 'target_id': 9, 'target_name': 'Uptempo Hardcore'},
                {'genre_id': 1, 'target_id': 8, 'target_name': 'Terror'},
            ],
        ]
        body = self.client.get('/api/rules/genres', headers=self.headers).json()
        self.assertEqual([t['name'] for t in body[0]['canonical_targets']], ['Uptempo Hardcore', 'Terror'])
        self.assertEqual(body[1]['canonical_targets'], [])

    def test_an_empty_queue_skips_the_targets_query(self):
        self.cursor.fetchall.return_value = []
        self.client.get('/api/rules/genres', headers=self.headers)
        self.assertEqual(len(self.statements()), 1)


class DecideGenreTest(ManagementTestCase):
    def decide(self, payload, genre_id=1):
        return self.client.post(f'/api/rules/genres/{genre_id}/decide', headers=self.headers, json=payload)

    def test_a_genre_can_be_whitelisted(self):
        self.cursor.fetchone.return_value = {'id': 1}
        response = self.decide({'state': management_router.WHITE})
        self.assertEqual(response.json(), {'status': 'ok'})
        self.assertTrue(any('UPDATE rules_genres' in s for s in self.statements()))

    def test_a_decision_refreshes_the_tagger_cache(self):
        """The decision marks files for a retag; the retag has to see the decision.

        The tagger's ResolveGenreRule reads a GenreRulesHelper preloaded at import.
        Without the refresh the retag this decision queued would rewrite every file
        with the genre still resolving the old way, and nothing would say so.
        """
        Cache.reload.reset_mock()
        self.cursor.fetchone.return_value = {'id': 1, 'name': 'Electronic'}
        self.decide({'state': management_router.BLACK})
        Cache.reload.assert_called_once_with('genre_rules')

    def test_an_invalid_state_is_rejected(self):
        self.assertEqual(self.decide({'state': 'purple'}).status_code, 400)

    def test_a_genre_cannot_correct_to_itself(self):
        response = self.decide({'state': management_router.BLACK, 'canonical_id': 1})
        self.assertEqual(response.status_code, 400)

    def test_an_unknown_genre_is_a_not_found(self):
        self.cursor.fetchone.return_value = None
        self.assertEqual(self.decide({'state': management_router.WHITE}).status_code, 404)

    def test_an_unknown_correction_target_is_rejected(self):
        self.cursor.fetchone.side_effect = [{'id': 1}, None]
        response = self.decide({'state': management_router.BLACK, 'canonical_id': 9})
        self.assertEqual(response.status_code, 400)

    def test_a_contraction_stores_every_target_in_order(self):
        self.cursor.fetchone.side_effect = [{'id': 1}, {'id': 8}, {'id': 9}]
        response = self.decide({'state': management_router.BLACK, 'canonical_ids': [8, 9]})
        self.assertEqual(response.json(), {'status': 'ok'})
        inserts = [
            call.args[1]
            for call in self.cursor.execute.call_args_list
            if 'INSERT INTO rules_genre_expansions' in call.args[0]
        ]
        self.assertEqual(inserts, [(1, 8, 0), (1, 9, 1)])

    def test_the_previous_targets_are_replaced_not_merged(self):
        self.cursor.fetchone.return_value = {'id': 1}
        self.decide({'state': management_router.WHITE})
        self.assertTrue(any('DELETE FROM rules_genre_expansions' in s for s in self.statements()))

    def test_a_system_decision_is_attributed_to_the_system(self):
        self.cursor.fetchone.return_value = {'id': 1}
        self.decide({'state': management_router.WHITE})
        update = [call for call in self.cursor.execute.call_args_list if 'UPDATE rules_genres' in call.args[0]][0]
        self.assertEqual(update.args[1][2], 'system')

    def test_a_user_decision_is_attributed_to_that_user(self):
        self.cursor.fetchone.return_value = {'id': 1}
        with patch.object(
            users_router,
            'verify_token',
            return_value={
                'status': 'ok',
                'type': 'user',
                'user': {'username': 'user', 'permissions': ['rules.manage']},
            },
        ):
            self.client.post(
                '/api/rules/genres/1/decide', headers={'x-api-key': 'user-key'}, json={'state': management_router.WHITE}
            )
        update = [call for call in self.cursor.execute.call_args_list if 'UPDATE rules_genres' in call.args[0]][0]
        self.assertEqual(update.args[1][2], 'user')

    def test_duplicate_targets_are_stored_once(self):
        self.cursor.fetchone.side_effect = [{'id': 1}, {'id': 8}]
        self.decide({'state': management_router.BLACK, 'canonical_ids': [8, 8]})
        inserts = [
            call.args[1]
            for call in self.cursor.execute.call_args_list
            if 'INSERT INTO rules_genre_expansions' in call.args[0]
        ]
        self.assertEqual(inserts, [(1, 8, 0)])


class ArtistAndLabelRulesTest(ManagementTestCase):
    def test_the_artist_genre_rules_are_listed(self):
        self.cursor.fetchall.return_value = [{'id': 1, 'artist_name': 'Angerfist'}]
        response = self.client.get('/api/rules/artist-genres', headers=self.headers)
        self.assertEqual(response.json()[0]['artist_name'], 'Angerfist')

    def test_a_rule_row_carries_the_library_artist_its_track_count_and_who_made_it(self):
        """The rules page opens the artist and shows the reach, so the list joins the library."""
        self.client.get('/api/rules/artist-genres', headers=self.headers)
        statement = self.statements()[0]
        for fragment in (
            'a.id AS artist_id',
            'track_count',
            'created_at',
            'r.created_by',
            'LEFT JOIN library_artists a',
        ):
            self.assertIn(fragment, statement)

    def test_a_label_rule_row_carries_the_same_provenance(self):
        self.client.get('/api/rules/label-genres', headers=self.headers)
        statement = self.statements()[0]
        for fragment in ('l.id AS label_id', 'track_count', 'created_at', 'LEFT JOIN library_labels l'):
            self.assertIn(fragment, statement)

    def test_an_artist_genre_rule_can_be_added(self):
        response = self.client.post(
            '/api/rules/artist-genres', headers=self.headers, json={'artist_name': 'Angerfist', 'genre_id': 3}
        )
        self.assertEqual(response.json(), {'status': 'ok'})
        self.assertEqual(self.cursor.execute.call_args.args[1], ('Angerfist', 3, 'system'))

    def test_adding_a_rule_here_refreshes_the_tagger_cache_too(self):
        """This endpoint predates the edit pages and had the same silent failure.

        Cache.databaseHelpers preloads rules_artist_genre once at import, so without
        the refresh a rule added from the Tagger tab did nothing until a restart.
        """
        Cache.reload.reset_mock()
        self.client.post(
            '/api/rules/artist-genres', headers=self.headers, json={'artist_name': 'Angerfist', 'genre_id': 3}
        )
        Cache.reload.assert_called_once_with('artistGenreHelper')

    def test_removing_a_rule_here_refreshes_the_tagger_cache_too(self):
        Cache.reload.reset_mock()
        self.client.delete('/api/rules/artist-genres/5', headers=self.headers)
        Cache.reload.assert_called_once_with('artistGenreHelper')

    def test_adding_a_label_rule_refreshes_the_label_helper(self):
        Cache.reload.reset_mock()
        self.client.post(
            '/api/rules/label-genres', headers=self.headers, json={'label_name': 'Scantraxx', 'genre_id': 3}
        )
        Cache.reload.assert_called_once_with('labelGenreHelper')

    def test_an_artist_genre_rule_can_be_removed(self):
        response = self.client.delete('/api/rules/artist-genres/5', headers=self.headers)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_the_label_genre_rules_are_listed(self):
        self.cursor.fetchall.return_value = [{'id': 1, 'label_name': 'Scantraxx'}]
        response = self.client.get('/api/rules/label-genres', headers=self.headers)
        self.assertEqual(response.json()[0]['label_name'], 'Scantraxx')

    def test_a_label_genre_rule_can_be_added(self):
        response = self.client.post(
            '/api/rules/label-genres', headers=self.headers, json={'label_name': 'Scantraxx', 'genre_id': 3}
        )
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_a_label_genre_rule_can_be_removed(self):
        response = self.client.delete('/api/rules/label-genres/5', headers=self.headers)
        self.assertEqual(response.json(), {'status': 'ok'})


class ProxyAndRescanTest(ManagementTestCase):
    def test_the_stats_proxy_delegates_to_the_stats_router(self):
        with patch('services.music_manager.routers.stats.get_stats', return_value={'tracks': 1}) as get_stats:
            body = self.client.get('/api/stats', headers=self.headers).json()
        self.assertEqual(body, {'tracks': 1})
        get_stats.assert_called_once()

    # The two scrobble proxies below are shadowed over HTTP: main.py mounts the scrobbler
    # router on /api/scrobble before management on /api, so a request never reaches them.
    # Call them directly to cover the delegation itself.
    def test_the_scrobble_import_list_is_proxied(self):
        with patch('services.music_manager.routers.scrobbler.get_latest_imports', return_value=[]) as proxied:
            self.assertEqual(management_router.get_latest_scrobble_imports_proxy({'type': 'system'}), [])
        proxied.assert_called_once()

    def test_a_scrobble_import_is_proxied(self):
        with patch(
            'services.music_manager.routers.scrobbler.trigger_lb_import', return_value={'status': 'ok'}
        ) as proxied:
            result = management_router.trigger_lb_import_proxy(MagicMock(), {'username': 'user'}, {'type': 'system'})
        self.assertEqual(result, {'status': 'ok'})
        proxied.assert_called_once()

    def test_the_whole_library_can_be_flagged_for_a_retag(self):
        with patch.object(management_router, 'ProcessedFilesHelper') as helper:
            body = self.client.post('/api/tagger/rescan', headers=self.headers).json()
        self.assertEqual(body['status'], 'ok')
        helper.return_value.mark_for_rescan.assert_called_once_with(reason='rescan_all')

    def test_a_single_file_can_be_flagged_for_a_retag(self):
        with patch.object(management_router, 'ProcessedFilesHelper') as helper:
            body = self.client.post(
                '/api/tagger/rescan/file', headers=self.headers, json={'filepath': '/music/a.mp3'}
            ).json()
        self.assertEqual(body['status'], 'ok')
        helper.return_value.mark_for_rescan.assert_called_once_with('/music/a.mp3', reason='manual')


class PodcastCurationQueueTest(ManagementTestCase):
    def test_the_whole_table_is_returned_without_a_state_filter(self):
        self.cursor.fetchall.side_effect = [[{'id': 1, 'name': 'Hard With Style'}], []]
        response = self.client.get('/api/rules/podcasts', headers=self.headers)
        self.assertEqual(response.json()[0]['name'], 'Hard With Style')
        self.assertNotIn('WHERE p.state', self.statements()[0])

    def test_a_state_filter_narrows_the_query(self):
        self.cursor.fetchall.side_effect = [[{'id': 1, 'name': 'Euphoricast'}], []]
        self.client.get('/api/rules/podcasts?state=unknown', headers=self.headers)
        self.assertIn('WHERE p.state = %s', self.statements()[0])

    def test_an_unknown_state_is_rejected(self):
        response = self.client.get('/api/rules/podcasts?state=purple', headers=self.headers)
        self.assertEqual(response.status_code, 400)

    def test_the_spellings_are_attached_to_each_show(self):
        self.cursor.fetchall.side_effect = [
            [{'id': 1, 'name': "Isaac's Hardstyle Sessions"}, {'id': 2, 'name': 'Euphoricast'}],
            [
                {'podcast_id': 1, 'alias': "Isaac's Hardstyle Sessions"},
                {'podcast_id': 1, 'alias': 'DJ ISAAC - HARDSTYLE SESSIONS'},
            ],
        ]
        body = self.client.get('/api/rules/podcasts', headers=self.headers).json()
        self.assertEqual(body[0]['aliases'], ["Isaac's Hardstyle Sessions", 'DJ ISAAC - HARDSTYLE SESSIONS'])
        self.assertEqual(body[1]['aliases'], [])

    def test_an_empty_queue_skips_the_alias_query(self):
        self.cursor.fetchall.return_value = []
        self.client.get('/api/rules/podcasts', headers=self.headers)
        self.assertEqual(len(self.statements()), 1)


class DecidePodcastTest(ManagementTestCase):
    def decide(self, payload, podcast_id=1):
        return self.client.post(f'/api/rules/podcasts/{podcast_id}/decide', headers=self.headers, json=payload)

    def test_a_show_can_be_approved(self):
        self.cursor.fetchone.return_value = {'id': 1, 'name': 'Hard With Style'}
        response = self.decide({'state': management_router.WHITE})
        self.assertEqual(response.json(), {'status': 'ok'})
        self.assertTrue(any('UPDATE rules_podcasts' in s for s in self.statements()))

    def test_an_invalid_state_is_rejected(self):
        self.assertEqual(self.decide({'state': 'purple'}).status_code, 400)

    def test_an_unknown_show_is_a_not_found(self):
        self.cursor.fetchone.return_value = None
        self.assertEqual(self.decide({'state': management_router.WHITE}).status_code, 404)

    def test_a_show_cannot_be_merged_into_itself(self):
        response = self.decide({'state': management_router.WHITE, 'merge_into_podcast_id': 1})
        self.assertEqual(response.status_code, 400)

    def test_an_unknown_merge_target_is_rejected(self):
        self.cursor.fetchone.side_effect = [{'id': 1, 'name': 'x'}, None]
        response = self.decide({'state': management_router.WHITE, 'merge_into_podcast_id': 9})
        self.assertEqual(response.status_code, 400)

    def test_a_merge_moves_the_spellings_and_drops_the_row(self):
        """Losing the alias would unmatch every file that spells the show that way."""
        self.cursor.fetchone.side_effect = [{'id': 1, 'name': 'DJ ISAAC - HARDSTYLE SESSIONS'}, {'id': 9}]
        response = self.decide({'state': management_router.WHITE, 'merge_into_podcast_id': 9})
        self.assertEqual(response.json(), {'status': 'ok', 'merged_into': 9})
        moves = [
            call.args[1]
            for call in self.cursor.execute.call_args_list
            if 'UPDATE rules_podcast_aliases' in call.args[0]
        ]
        self.assertEqual(moves, [(9, 1)])
        self.assertTrue(any('DELETE FROM rules_podcasts' in s for s in self.statements()))

    def test_a_merge_does_not_also_write_a_state(self):
        self.cursor.fetchone.side_effect = [{'id': 1, 'name': 'x'}, {'id': 9}]
        self.decide({'state': management_router.WHITE, 'merge_into_podcast_id': 9})
        self.assertFalse(any('UPDATE rules_podcasts' in s for s in self.statements()))

    def test_a_system_decision_is_attributed_to_the_system(self):
        self.cursor.fetchone.return_value = {'id': 1, 'name': 'x'}
        self.decide({'state': management_router.WHITE})
        update = [call for call in self.cursor.execute.call_args_list if 'UPDATE rules_podcasts' in call.args[0]][0]
        self.assertEqual(update.args[1][3], 'system')

    def test_the_host_and_station_are_stored_when_given(self):
        self.cursor.fetchone.return_value = {'id': 1, 'name': 'x'}
        self.decide({'state': management_router.WHITE, 'host': 'DJ Isaac', 'station': 'Q-dance'})
        update = [call for call in self.cursor.execute.call_args_list if 'UPDATE rules_podcasts' in call.args[0]][0]
        self.assertEqual(update.args[1][1:3], ('DJ Isaac', 'Q-dance'))

    def test_a_decision_refreshes_the_tagger_cache(self):
        """Without this an approved show stays invisible to the running tagger."""
        Cache.reload.reset_mock()
        self.cursor.fetchone.return_value = {'id': 1, 'name': 'x'}
        self.decide({'state': management_router.WHITE})
        Cache.reload.assert_called_once_with('podcastHelper')

    def test_a_merge_keeps_the_name_of_the_row_it_drops(self):
        """
        A renamed row's name is not in the alias table, so moving only the alias rows
        would lose the spelling the row was matched by.
        """
        self.cursor.fetchone.side_effect = [{'id': 1, 'name': 'Pure Hardstyle'}, {'id': 9}]
        self.decide({'state': management_router.WHITE, 'merge_into_podcast_id': 9})
        inserts = [
            call
            for call in self.cursor.execute.call_args_list
            if 'INSERT' in call.args[0] and 'rules_podcast_aliases' in call.args[0]
        ]
        self.assertEqual(inserts[0].args[1][:3], (9, 'Pure Hardstyle', 'pure hardstyle'))


class RenamePodcastTest(ManagementTestCase):
    """
    Renaming is what turns a detected spelling into a show name.

    `tools/detect_podcasts.py` proposes the raw filename fragment it grouped on --
    'KELTEK Presents | Pure Hardstyle |' -- and `PodcastHelper.get` writes that
    straight into the PODCAST tag, so without a rename the browse page is named
    after the uploader rather than after the show.
    """

    def rename(self, payload, podcast_id=1):
        return self.client.post(f'/api/rules/podcasts/{podcast_id}/rename', headers=self.headers, json=payload)

    def test_a_show_can_be_renamed(self):
        self.cursor.fetchone.side_effect = [{'id': 1, 'name': 'KELTEK Presents | Pure Hardstyle |'}, None]
        response = self.rename({'name': 'Pure Hardstyle'})
        self.assertEqual(response.json()['status'], 'ok')
        update = [call for call in self.cursor.execute.call_args_list if 'UPDATE rules_podcasts' in call.args[0]][0]
        self.assertEqual(update.args[1][:3], ('Pure Hardstyle', 'pure hardstyle', 1))

    def test_an_unknown_show_is_a_not_found(self):
        self.cursor.fetchone.return_value = None
        self.assertEqual(self.rename({'name': 'Pure Hardstyle'}).status_code, 404)

    def test_a_blank_name_is_rejected(self):
        self.cursor.fetchone.return_value = {'id': 1, 'name': 'x'}
        self.assertEqual(self.rename({'name': '   '}).status_code, 400)

    def test_a_name_too_short_to_be_a_safe_alias_is_rejected(self):
        """The name doubles as a matcher, and a two-letter one matches half the library."""
        self.cursor.fetchone.return_value = {'id': 1, 'name': 'x'}
        response = self.rename({'name': 'Q!'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('4', response.json()['detail'])

    def test_a_name_another_show_already_uses_is_a_conflict(self):
        self.cursor.fetchone.side_effect = [{'id': 1, 'name': 'a'}, {'id': 7, 'name': 'Pure Hardstyle'}]
        response = self.rename({'name': 'Pure Hardstyle'})
        self.assertEqual(response.status_code, 409)
        self.assertIn('Pure Hardstyle', response.json()['detail'])

    def test_renaming_to_the_same_key_is_not_a_conflict_with_itself(self):
        """Fixing only the casing must not read as a collision with the row itself."""
        self.cursor.fetchone.side_effect = [{'id': 1, 'name': 'pure hardstyle'}, {'id': 1, 'name': 'pure hardstyle'}]
        self.assertEqual(self.rename({'name': 'Pure Hardstyle'}).status_code, 200)

    def test_the_old_name_is_kept_as_a_spelling(self):
        """
        The name is an implicit alias: `PodcastHelper._load` seeds every show with it.
        Renaming without keeping it would unmatch every file spelled the old way.
        """
        self.cursor.fetchone.side_effect = [{'id': 1, 'name': 'KELTEK Presents | Pure Hardstyle |'}, None]
        self.rename({'name': 'Pure Hardstyle'})
        inserts = [
            call
            for call in self.cursor.execute.call_args_list
            if 'rules_podcast_aliases' in call.args[0] and 'INSERT' in call.args[0]
        ]
        self.assertEqual(
            inserts[0].args[1][:3], (1, 'KELTEK Presents | Pure Hardstyle |', 'keltek presents pure hardstyle')
        )

    def test_a_rename_refreshes_the_tagger_cache(self):
        Cache.reload.reset_mock()
        self.cursor.fetchone.side_effect = [{'id': 1, 'name': 'a'}, None]
        self.rename({'name': 'Pure Hardstyle'})
        Cache.reload.assert_called_once_with('podcastHelper')


class PodcastAliasTest(ManagementTestCase):
    """
    Spellings are the other half of a correct show.

    The rule matches on `title + path`, so the alias that catches every episode is
    the shortest fragment common to all of them; the detector only ever proposes the
    fragments that carried an episode marker.
    """

    def add(self, payload, podcast_id=1):
        return self.client.post(f'/api/rules/podcasts/{podcast_id}/aliases', headers=self.headers, json=payload)

    def remove(self, alias, podcast_id=1):
        return self.client.request(
            'DELETE', f'/api/rules/podcasts/{podcast_id}/aliases', headers=self.headers, params={'alias': alias}
        )

    def test_a_spelling_can_be_added(self):
        self.cursor.fetchone.side_effect = [{'id': 1, 'name': 'Pure Hardstyle'}, None]
        response = self.add({'alias': 'KELTEK | Pure Hardstyle |'})
        self.assertEqual(response.json()['status'], 'ok')
        insert = [
            call for call in self.cursor.execute.call_args_list if 'INSERT INTO rules_podcast_aliases' in call.args[0]
        ][0]
        self.assertEqual(insert.args[1][:3], (1, 'KELTEK | Pure Hardstyle |', 'keltek pure hardstyle'))

    def test_adding_to_an_unknown_show_is_a_not_found(self):
        self.cursor.fetchone.return_value = None
        self.assertEqual(self.add({'alias': 'whatever'}).status_code, 404)

    def test_a_blank_spelling_is_rejected(self):
        self.cursor.fetchone.return_value = {'id': 1, 'name': 'x'}
        self.assertEqual(self.add({'alias': ' - '}).status_code, 400)

    def test_a_spelling_too_short_to_be_safe_is_rejected(self):
        self.cursor.fetchone.return_value = {'id': 1, 'name': 'x'}
        response = self.add({'alias': 'HS'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('4', response.json()['detail'])

    def test_a_spelling_another_show_owns_is_a_conflict(self):
        self.cursor.fetchone.side_effect = [{'id': 1, 'name': 'a'}, {'podcast_id': 7, 'name': 'Hardcore Italia'}]
        response = self.add({'alias': 'Hardcore Italia'})
        self.assertEqual(response.status_code, 409)
        self.assertIn('Hardcore Italia', response.json()['detail'])

    def test_a_spelling_this_show_already_has_is_accepted_quietly(self):
        self.cursor.fetchone.side_effect = [{'id': 1, 'name': 'a'}, {'podcast_id': 1, 'name': 'a'}]
        response = self.add({'alias': 'Pure Hardstyle'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(any('INSERT INTO rules_podcast_aliases' in s for s in self.statements()))

    def test_adding_a_spelling_refreshes_the_tagger_cache(self):
        Cache.reload.reset_mock()
        self.cursor.fetchone.side_effect = [{'id': 1, 'name': 'a'}, None]
        self.add({'alias': 'Pure Hardstyle'})
        Cache.reload.assert_called_once_with('podcastHelper')

    def test_a_spelling_can_be_removed(self):
        self.cursor.fetchone.side_effect = [{'id': 1, 'name': 'a'}, {'id': 4}]
        response = self.remove('KELTEK | Pure Hardstyle |')
        self.assertEqual(response.json()['status'], 'ok')
        delete = [
            call for call in self.cursor.execute.call_args_list if 'DELETE FROM rules_podcast_aliases' in call.args[0]
        ][0]
        self.assertEqual(delete.args[1], (4,))

    def test_removing_a_spelling_the_show_does_not_have_is_a_not_found(self):
        self.cursor.fetchone.side_effect = [{'id': 1, 'name': 'a'}, None]
        self.assertEqual(self.remove('nope at all').status_code, 404)

    def test_the_last_spelling_may_go_because_the_name_still_matches(self):
        """
        There is no floor on the alias count: `PodcastHelper._load` falls back to the
        show's own name, so a show with no alias rows still matches its own title.
        """
        self.cursor.fetchone.side_effect = [{'id': 1, 'name': 'Pure Hardstyle'}, {'id': 4}]
        self.assertEqual(self.remove('Pure Hardstyle').status_code, 200)

    def test_removing_a_spelling_refreshes_the_tagger_cache(self):
        Cache.reload.reset_mock()
        self.cursor.fetchone.side_effect = [{'id': 1, 'name': 'a'}, {'id': 4}]
        self.remove('KELTEK | Pure Hardstyle |')
        Cache.reload.assert_called_once_with('podcastHelper')


class LabelProposalsTest(ManagementTestCase):
    """
    Releases the importer could not place. Confirming one that carries a catalogue
    number teaches rules_catid_label and the importer moves it on its next cycle;
    confirming one without a catalogue number has no rule to write, so the folder is
    moved here instead.
    """

    def setUp(self):
        super().setUp()
        self.settings = MagicMock(import_folder_path='/import', eps_folder_path='/eps')
        patcher = patch.object(management_router, 'Settings', return_value=self.settings)
        patcher.start()
        self.addCleanup(patcher.stop)

    def confirm(self, proposal_id, label):
        return self.client.post(
            f'/api/label-proposals/{proposal_id}/confirm', json={'label': label}, headers=self.headers
        )

    def test_the_open_proposals_are_listed(self):
        self.cursor.fetchall.return_value = [
            {
                'id': 1,
                'folder': 'BKRP104 - Darwin',
                'catid': 'BKRP',
                'proposed_label': 'Brutal Kuts',
                'source': 'tag:label',
                'confidence': 90,
                'status': 'new',
            }
        ]

        response = self.client.get('/api/label-proposals', headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]['proposed_label'], 'Brutal Kuts')
        self.assertEqual(response.json()[0]['folder'], 'BKRP104 - Darwin')

    def test_confirming_a_proposal_with_a_cat_id_writes_the_label_rule(self):
        self.cursor.fetchone.return_value = {
            'id': 1,
            'folder': 'BKRP104 - Darwin',
            'catid': 'BKRP',
            'proposed_label': 'Brutal Kuts',
        }

        response = self.confirm(1, 'Brutal Kuts')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any('rules_catid_label' in s for s in self.statements()))

    def test_confirming_a_two_option_proposal_records_the_choice_for_the_label(self):
        # #164: the .nfo says Cloud 9 Music, the curator files those under Cloud 9 Dance.
        self.cursor.fetchone.return_value = {
            'id': 3,
            'folder': 'CLDM2025001 - VA-Masters_Of_Hardcore-(CLDM2025001)-2CD-FLAC-2025-OTT',
            'catid': 'CLDM2025001',
            'proposed_label': 'Cloud 9 Music',
            'label_choice_key': 'cloud9',
        }

        response = self.confirm(3, 'Cloud 9 Dance')

        self.assertEqual(response.status_code, 200)
        choice = [c for c in self.cursor.execute.call_args_list if 'rules_label_name_choices' in str(c.args[0])]
        self.assertEqual(1, len(choice))
        self.assertEqual(('Cloud 9 Dance', 'cloud9'), choice[0].args[1])

    def test_confirming_an_ordinary_proposal_records_no_choice(self):
        self.cursor.fetchone.return_value = {
            'id': 1,
            'folder': 'BKRP104 - Darwin',
            'catid': 'BKRP',
            'proposed_label': 'Brutal Kuts',
        }

        self.confirm(1, 'Brutal Kuts')

        self.assertFalse(any('rules_label_name_choices' in s for s in self.statements()))

    def test_confirming_a_proposal_with_a_cat_id_moves_nothing_itself(self):
        self.cursor.fetchone.return_value = {
            'id': 1,
            'folder': 'BKRP104 - Darwin',
            'catid': 'BKRP',
            'proposed_label': 'Brutal Kuts',
        }

        with patch.object(management_router, 'move_release_folder') as move:
            self.confirm(1, 'Brutal Kuts')

        move.assert_not_called()

    def test_confirming_a_proposal_without_a_cat_id_moves_the_folder(self):
        self.cursor.fetchone.return_value = {'id': 2, 'folder': ' - Dewstate', 'catid': None, 'proposed_label': None}

        with (
            patch.object(management_router, 'move_release_folder', return_value=MOVED) as move,
            patch.object(management_router, 'folder_exists', return_value=True),
        ):
            response = self.confirm(2, 'Different Solution Records')

        self.assertEqual(response.status_code, 200)
        move.assert_called_once_with('/import/ - Dewstate', '/eps/Different Solution Records/ - Dewstate')

    def test_a_proposal_whose_destination_is_taken_moves_nothing(self):
        """shutil.move into an existing directory nests instead of failing.

        The importer's mover learned that on 2026-09-04; this endpoint makes the same call
        and never did. It has not bitten here yet -- only one nested folder on production
        ever appeared in this table, and it is still open -- but the call is identical and
        so is the damage: the release ends up inside the folder it collided with.
        """
        self.cursor.fetchone.return_value = {'id': 5, 'folder': 'REL001', 'catid': None, 'proposed_label': None}

        with (
            patch.object(management_router, 'folder_exists', return_value=True),
            patch.object(management_router, 'move_release_folder', return_value=CONFLICT) as move,
        ):
            response = self.confirm(5, 'Some Label')

        move.assert_called_once_with('/import/REL001', '/eps/Some Label/REL001')
        self.assertEqual(response.json()['status'], 'conflict')
        # The proposal stays open: once the collision is resolved by hand it can be
        # confirmed again, and a proposal marked confirmed while nothing moved would
        # leave the folder in import with nothing pointing at it.
        self.assertFalse(any("status = 'confirmed'" in s for s in self.statements()))

    def test_a_proposal_whose_folder_vanished_is_reported_as_stale(self):
        self.cursor.fetchone.return_value = {'id': 3, 'folder': 'gone', 'catid': None, 'proposed_label': None}

        with patch.object(management_router, 'folder_exists', return_value=False):
            response = self.confirm(3, 'Whatever')

        self.assertEqual(response.json()['status'], 'stale')
        self.assertTrue(any("status = 'stale'" in s for s in self.statements()))

    def test_an_unknown_proposal_is_not_found(self):
        self.cursor.fetchone.return_value = None

        self.assertEqual(self.confirm(99, 'Whatever').status_code, 404)

    def test_a_rejected_proposal_is_marked_rejected(self):
        response = self.client.post('/api/label-proposals/4/reject', headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any("status = 'rejected'" in s for s in self.statements()))


class ImportConflictsTest(ManagementTestCase):
    """The standing folder conflicts the importer warns about once (bug report 091)."""

    def test_the_standing_conflicts_are_listed_oldest_first(self):
        self.cursor.fetchall.return_value = [
            {
                'step': 'renamer',
                'source': '/import/Release-(CAT1)',
                'target': '/import/CAT1 - Release-(CAT1)',
                'first_seen': '2026-09-25 17:00:00',
                'last_seen': '2026-09-25 20:00:00',
            }
        ]

        response = self.client.get('/api/import-conflicts', headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]['target'], '/import/CAT1 - Release-(CAT1)')
        statement = self.statements()[0]
        self.assertIn('FROM importer_conflicts', statement)
        self.assertIn('ORDER BY first_seen', statement)
        # Bug report 119: an extractor row is a file, and its reason is what Beheer shows.
        self.assertIn('reason', statement)

    def test_the_list_needs_an_api_key(self):
        response = self.client.get('/api/import-conflicts')

        self.assertIn(response.status_code, (401, 403))


class DecideGenreAtomicityTest(ManagementTestCase):
    """A genre decision's expansions are deleted and re-inserted in one transaction."""

    def decide(self):
        self.cursor.fetchone.side_effect = [{'id': 1, 'name': 'Upterror'}, {'id': 8}, {'id': 9}]
        return self.client.post(
            '/api/rules/genres/1/decide',
            headers=self.headers,
            json={'state': management_router.BLACK, 'canonical_ids': [8, 9]},
        )

    def test_the_update_delete_and_inserts_are_one_transaction_and_the_retag_comes_after(self):
        log = transaction_log(self.conn, self.cursor)
        with patch.object(
            management_router.rescan_invalidator,
            'invalidate_by_genre_id',
            side_effect=lambda *_a: log.append('INVALIDATE'),
        ):
            self.assertEqual(self.decide().json(), {'status': 'ok'})
        assert_atomic(
            self, log, 'UPDATE rules_genres', 'DELETE FROM rules_genre_expansions', 'INSERT INTO rules_genre_expansions'
        )
        self.assertGreater(log.index('INVALIDATE'), log.index('COMMIT'))

    def test_a_failing_insert_rolls_the_decision_back_and_queues_no_retag(self):
        log = transaction_log(self.conn, self.cursor, fail_on='INSERT INTO rules_genre_expansions')
        with (
            patch.object(management_router.rescan_invalidator, 'invalidate_by_genre_id') as invalidate,
            self.assertRaises(RuntimeError),
        ):
            self.decide()
        assert_rolled_back(self, log)
        invalidate.assert_not_called()


class DecidePodcastMergeAtomicityTest(ManagementTestCase):
    """A podcast merge keeps the name, moves the spellings and drops the row in one transaction."""

    def merge(self):
        self.cursor.fetchone.side_effect = [{'id': 1, 'name': 'DJ ISAAC - HARDSTYLE SESSIONS'}, {'id': 9}]
        return self.client.post(
            '/api/rules/podcasts/1/decide',
            headers=self.headers,
            json={'state': management_router.WHITE, 'merge_into_podcast_id': 9},
        )

    def test_the_alias_writes_and_the_row_delete_are_one_transaction(self):
        log = transaction_log(self.conn, self.cursor)
        self.assertEqual(self.merge().json(), {'status': 'ok', 'merged_into': 9})
        assert_atomic(
            self,
            log,
            'INSERT IGNORE INTO rules_podcast_aliases',
            'UPDATE rules_podcast_aliases',
            'DELETE FROM rules_podcasts',
        )

    def test_a_failing_row_delete_rolls_the_moved_spellings_back(self):
        """Without it the show stayed in the queue with its spellings already handed away."""
        log = transaction_log(self.conn, self.cursor, fail_on='DELETE FROM rules_podcasts')
        with self.assertRaises(RuntimeError):
            self.merge()
        assert_rolled_back(self, log)


class ConfirmLabelProposalAtomicityTest(ManagementTestCase):
    """The CAT-ID rule and the proposal's verdict land together (bug report 115)."""

    def setUp(self):
        super().setUp()
        patcher = patch.object(
            management_router, 'Settings', return_value=MagicMock(import_folder_path='/import', eps_folder_path='/eps')
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cursor.fetchone.return_value = {'id': 1, 'folder': 'BKRP104', 'catid': 'BKRP', 'proposed_label': 'X'}

    def confirm(self):
        return self.client.post('/api/label-proposals/1/confirm', json={'label': 'Brutal Kuts'}, headers=self.headers)

    def test_the_rule_and_the_verdict_are_one_transaction(self):
        log = transaction_log(self.conn, self.cursor)
        self.assertEqual(self.confirm().json()['status'], 'confirmed')
        assert_atomic(self, log, 'INSERT INTO rules_catid_label', "SET status = 'confirmed'")

    def test_a_failing_verdict_rolls_the_rule_back(self):
        """Without it the importer acted on a rule whose proposal still read as open."""
        log = transaction_log(self.conn, self.cursor, fail_on="SET status = 'confirmed'")
        with self.assertRaises(RuntimeError):
            self.confirm()
        assert_rolled_back(self, log)

    def test_the_folder_move_happens_before_the_transaction_opens(self):
        """A move on disk cannot be rolled back, so it must not sit inside one."""
        self.cursor.fetchone.return_value = {'id': 2, 'folder': 'REL', 'catid': None, 'proposed_label': None}
        log = transaction_log(self.conn, self.cursor)
        with (
            patch.object(management_router, 'folder_exists', return_value=True),
            patch.object(management_router, 'move_release_folder', side_effect=lambda *_a: log.append('MOVE') or MOVED),
        ):
            self.assertEqual(self.confirm().json()['status'], 'confirmed')
        self.assertLess(log.index('MOVE'), log.index('BEGIN'))
        assert_atomic(self, log, "SET status = 'confirmed'")


class RenamePodcastAtomicityTest(ManagementTestCase):
    """A rename and the old name kept as a spelling land together (bug report 115)."""

    def rename(self):
        self.cursor.fetchone.side_effect = [{'id': 1, 'name': 'KELTEK Presents | Pure Hardstyle |'}, None]
        return self.client.post('/api/rules/podcasts/1/rename', headers=self.headers, json={'name': 'Pure Hardstyle'})

    def test_the_rename_and_the_kept_spelling_are_one_transaction(self):
        log = transaction_log(self.conn, self.cursor)
        self.assertEqual(self.rename().json()['status'], 'ok')
        assert_atomic(self, log, 'UPDATE rules_podcasts', 'INSERT IGNORE INTO rules_podcast_aliases')

    def test_a_failing_alias_insert_rolls_the_rename_back(self):
        """Without it the old spelling was gone for good: a retry keeps the name the row carries."""
        log = transaction_log(self.conn, self.cursor, fail_on='INSERT IGNORE INTO rules_podcast_aliases')
        with self.assertRaises(RuntimeError):
            self.rename()
        assert_rolled_back(self, log)


if __name__ == '__main__':
    unittest.main()


class RuleChangeInvalidationTest(ManagementTestCase):
    """A saved rule schedules the retag of the files it touches.

    The invalidation runs after the commit and never fails the edit: a rule that saved
    without queueing a retag is repaired by the fallback rescan, a rule that refused to
    save is not.
    """

    def test_adding_an_artist_genre_rule_marks_that_artists_files(self):
        with patch.object(rescan_invalidator_module, 'rescan_invalidator') as invalidator:
            response = self.client.post(
                '/api/rules/artist-genres', json={'artist_name': 'Ran-D', 'genre_id': 3}, headers=self.headers
            )
        self.assertEqual(response.status_code, 200)
        invalidator.invalidate_by_term.assert_called_once_with('Ran-D', 'artist_genre_rule')

    def test_deleting_an_artist_genre_rule_uses_the_name_from_before_the_delete(self):
        self.cursor.fetchone.return_value = {'artist_name': 'Ran-D'}
        with patch.object(rescan_invalidator_module, 'rescan_invalidator') as invalidator:
            response = self.client.delete('/api/rules/artist-genres/9', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        invalidator.invalidate_by_term.assert_called_once_with('Ran-D', 'artist_genre_rule')

    def test_deleting_a_rule_that_no_longer_exists_marks_nothing(self):
        self.cursor.fetchone.return_value = None
        with patch.object(rescan_invalidator_module, 'rescan_invalidator') as invalidator:
            response = self.client.delete('/api/rules/artist-genres/9', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        invalidator.invalidate_by_term.assert_not_called()

    def test_adding_a_label_genre_rule_marks_that_labels_files(self):
        with patch.object(rescan_invalidator_module, 'rescan_invalidator') as invalidator:
            response = self.client.post(
                '/api/rules/label-genres', json={'label_name': 'Minus Is More', 'genre_id': 3}, headers=self.headers
            )
        self.assertEqual(response.status_code, 200)
        invalidator.invalidate_by_term.assert_called_once_with('Minus Is More', 'label_genre_rule')

    def test_deleting_a_label_genre_rule_uses_the_name_from_before_the_delete(self):
        self.cursor.fetchone.return_value = {'label_name': 'Minus Is More'}
        with patch.object(rescan_invalidator_module, 'rescan_invalidator') as invalidator:
            response = self.client.delete('/api/rules/label-genres/9', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        invalidator.invalidate_by_term.assert_called_once_with('Minus Is More', 'label_genre_rule')

    def test_a_genre_decision_marks_the_linked_tracks_and_the_name(self):
        self.cursor.fetchone.return_value = {'id': 1, 'name': 'Uptempo'}
        with patch.object(management_router, 'rescan_invalidator') as invalidator:
            response = self.client.post(
                '/api/rules/genres/1/decide', json={'state': management_router.WHITE}, headers=self.headers
            )
        self.assertEqual(response.status_code, 200)
        invalidator.invalidate_by_genre_id.assert_called_once_with(1, 'Uptempo', 'genre_decision')

    def test_a_failing_invalidation_does_not_fail_the_rule_change(self):
        with patch.object(rescan_invalidator_module, 'rescan_invalidator') as invalidator:
            invalidator.invalidate_by_term.side_effect = RuntimeError('database gone')
            response = self.client.post(
                '/api/rules/artist-genres', json={'artist_name': 'Ran-D', 'genre_id': 3}, headers=self.headers
            )
        self.assertEqual(response.status_code, 200)

    def test_a_failing_genre_invalidation_does_not_fail_the_decision(self):
        self.cursor.fetchone.return_value = {'id': 1, 'name': 'Uptempo'}
        with patch.object(management_router, 'rescan_invalidator') as invalidator:
            invalidator.invalidate_by_genre_id.side_effect = RuntimeError('database gone')
            response = self.client.post(
                '/api/rules/genres/1/decide', json={'state': management_router.WHITE}, headers=self.headers
            )
        self.assertEqual(response.status_code, 200)


class ArtistRedirectTest(ManagementTestCase):
    """rules_ignored_artists had no write path at all before this."""

    def test_the_redirects_are_listed(self):
        self.cursor.fetchall.return_value = [{'id': 1, 'name': 'Ran D', 'corrected_name': 'Ran-D'}]
        response = self.client.get('/api/rules/artist-redirects', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]['corrected_name'], 'Ran-D')

    def test_saving_a_redirect_marks_the_old_name_for_retag(self):
        with patch.object(rescan_invalidator_module, 'rescan_invalidator') as invalidator:
            response = self.client.post(
                '/api/rules/artist-redirects', json={'name': 'Ran D', 'corrected_name': 'Ran-D'}, headers=self.headers
            )
        self.assertEqual(response.status_code, 200)
        invalidator.invalidate_by_term.assert_called_once_with('Ran D', 'artist_redirect')

    def test_a_new_name_is_inserted(self):
        self.cursor.fetchone.return_value = None
        self.client.post(
            '/api/rules/artist-redirects', json={'name': 'Ran D', 'corrected_name': 'Ran-D'}, headers=self.headers
        )
        self.assertTrue(any('INSERT INTO rules_ignored_artists' in s for s in self.statements()))

    def test_a_known_name_is_updated_rather_than_duplicated(self):
        self.cursor.fetchone.return_value = {'id': 1}
        self.client.post(
            '/api/rules/artist-redirects', json={'name': 'Ran D', 'corrected_name': 'Ran-D'}, headers=self.headers
        )
        self.assertTrue(any('UPDATE rules_ignored_artists' in s for s in self.statements()))
        self.assertFalse(any('INSERT INTO rules_ignored_artists' in s for s in self.statements()))

    def test_a_redirect_without_a_correction_stores_null(self):
        self.cursor.fetchone.return_value = None
        self.client.post('/api/rules/artist-redirects', json={'name': 'Various Artists'}, headers=self.headers)
        insert = [
            call for call in self.cursor.execute.call_args_list if 'INSERT INTO rules_ignored_artists' in call.args[0]
        ][0]
        self.assertEqual(insert.args[1], ('Various Artists', None))

    def test_a_nameless_redirect_is_rejected(self):
        response = self.client.post('/api/rules/artist-redirects', json={'name': '   '}, headers=self.headers)
        self.assertEqual(response.status_code, 400)

    def test_a_redirect_to_a_rejected_artist_is_refused(self):
        """Bug 080: the Tagger tab could still point a name at one curation had rejected."""
        self.cursor.fetchone.return_value = {'state': 'black'}
        response = self.client.post(
            '/api/rules/artist-redirects', json={'name': 'Ran D', 'corrected_name': 'Premiere'}, headers=self.headers
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(any(s.startswith(('INSERT', 'UPDATE')) for s in self.statements()))

    def test_a_redirect_that_closes_a_loop_is_refused(self):
        self.cursor.fetchone.return_value = None
        self.cursor.fetchall.return_value = [{'name': 'Ran-D', 'corrected_name': 'Ran D'}]
        response = self.client.post(
            '/api/rules/artist-redirects', json={'name': 'Ran D', 'corrected_name': 'Ran-D'}, headers=self.headers
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('loop', response.json()['detail'])

    def test_a_casing_fix_is_not_a_loop(self):
        self.cursor.fetchone.return_value = None
        self.cursor.fetchall.return_value = [{'name': 'Angerfst', 'corrected_name': 'angerfist'}]
        response = self.client.post(
            '/api/rules/artist-redirects',
            json={'name': 'angerfist', 'corrected_name': 'Angerfist'},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)

    def test_deleting_a_redirect_uses_the_name_from_before_the_delete(self):
        self.cursor.fetchone.return_value = {'name': 'Ran D'}
        with patch.object(rescan_invalidator_module, 'rescan_invalidator') as invalidator:
            response = self.client.delete('/api/rules/artist-redirects/4', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        invalidator.invalidate_by_term.assert_called_once_with('Ran D', 'artist_redirect')

    def test_deleting_a_redirect_that_no_longer_exists_marks_nothing(self):
        self.cursor.fetchone.return_value = None
        with patch.object(rescan_invalidator_module, 'rescan_invalidator') as invalidator:
            response = self.client.delete('/api/rules/artist-redirects/4', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        invalidator.invalidate_by_term.assert_not_called()
