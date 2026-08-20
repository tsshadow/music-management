"""Coverage for the /api management router: rules, accounts, system info and proxies."""
import sys
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.easyid3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())


import services.music_manager.routers.users as users_router
from services.music_manager.api_key import resolve_system_api_key

users_router.run_lms_db_sync = lambda: None

from fastapi.testclient import TestClient

from services.music_manager.main import app
from services.music_manager.routers import management as management_router

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
        with patch.object(users_router, 'verify_token', return_value={'status': 'ok', 'type': 'user'}), \
             patch.object(management_router, 'get_db_connection', return_value=None):
            response = TestClient(app).get('/api/artists', headers={'x-api-key': 'user-key'})
        self.assertEqual(response.status_code, 500)

    def test_a_key_that_does_not_verify_is_rejected(self):
        with patch.object(users_router, 'verify_token', side_effect=Exception('nope')):
            response = TestClient(app).get('/api/artists', headers={'x-api-key': 'bad'})
        self.assertEqual(response.status_code, 401)


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
        with patch.object(management_router.os.path, 'exists', return_value=True), \
             patch('builtins.open', unittest.mock.mock_open(read_data='# Title')), \
             patch.object(management_router, 'markdown') as md:
            md.markdown.return_value = '<h1>Title</h1>'
            response = self.client.get('/api/about', headers=self.headers)
        self.assertIn('<h1>Title</h1>', response.text)

    def test_a_missing_readme_still_renders_a_page(self):
        with patch.object(management_router.os.path, 'exists', return_value=False), \
             patch.object(management_router, 'markdown') as md:
            md.markdown.return_value = '<h1>Music Manager</h1>'
            response = self.client.get('/api/about', headers=self.headers)
        self.assertEqual(response.status_code, 200)

    def test_the_release_notes_and_changelog_are_served(self):
        with patch.object(management_router, 'get_release_notes', return_value='notes'), \
             patch.object(management_router, 'get_changelog', return_value='log'):
            body = self.client.get('/api/notes', headers=self.headers).json()
        self.assertEqual(body, {'release_notes': 'notes', 'changelog': 'log'})

    def test_the_all_notes_alias_serves_the_same_payload(self):
        with patch.object(management_router, 'get_release_notes', return_value='notes'), \
             patch.object(management_router, 'get_changelog', return_value='log'):
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
                self.make_container('muma-manager'), self.make_container('unrelated-nginx')]
            body = self.client.get('/api/system/containers', headers=self.headers).json()
        self.assertEqual([c['name'] for c in body], ['muma-manager'])

    def test_a_container_without_an_image_tag_is_reported_as_unknown(self):
        with patch.object(management_router, 'docker') as docker:
            docker.from_env.return_value.containers.list.return_value = [
                self.make_container('muma-manager', image_tags=())]
            body = self.client.get('/api/system/containers', headers=self.headers).json()
        self.assertEqual(body[0]['image'], 'unknown')

    def test_an_unreachable_docker_daemon_is_a_server_error(self):
        with patch.object(management_router, 'docker') as docker:
            docker.from_env.side_effect = RuntimeError('no socket')
            self.assertEqual(self.client.get('/api/system/containers', headers=self.headers).status_code, 500)

    def test_container_logs_are_decoded(self):
        with patch.object(management_router, 'docker') as docker:
            docker.from_env.return_value.containers.get.return_value.logs.return_value = b'hello'
            body = self.client.get('/api/system/logs/muma-manager', headers=self.headers).json()
        self.assertEqual(body['logs'], 'hello')

    def test_logs_of_an_unknown_container_are_a_server_error(self):
        with patch.object(management_router, 'docker') as docker:
            docker.from_env.return_value.containers.get.side_effect = RuntimeError('not found')
            self.assertEqual(self.client.get('/api/system/logs/nope', headers=self.headers).status_code, 500)

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
        response = self.client.post('/api/soundcloud', headers=self.headers,
                                    json={'name': 'artist', 'soundcloud_id': 7})
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
        response = self.client.post('/api/youtube', headers=self.headers,
                                    json={'name': '@qdance', 'download_type': 'video'})
        self.assertEqual(response.json()['status'], 'ok')
        self.assertEqual(self.cursor.execute.call_args.args[1], ('@qdance', 'video', 1200))

    def test_an_unknown_youtube_download_type_is_rejected(self):
        response = self.client.post('/api/youtube', headers=self.headers,
                                    json={'name': 'channel', 'download_type': 'hologram'})
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
            [{'genre_id': 1, 'target_id': 9, 'target_name': 'Uptempo Hardcore'},
             {'genre_id': 1, 'target_id': 8, 'target_name': 'Terror'}],
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
        inserts = [call.args[1] for call in self.cursor.execute.call_args_list
                   if 'INSERT INTO rules_genre_expansions' in call.args[0]]
        self.assertEqual(inserts, [(1, 8, 0), (1, 9, 1)])

    def test_the_previous_targets_are_replaced_not_merged(self):
        self.cursor.fetchone.return_value = {'id': 1}
        self.decide({'state': management_router.WHITE})
        self.assertTrue(any('DELETE FROM rules_genre_expansions' in s for s in self.statements()))

    def test_a_system_decision_is_attributed_to_the_system(self):
        self.cursor.fetchone.return_value = {'id': 1}
        self.decide({'state': management_router.WHITE})
        update = [call for call in self.cursor.execute.call_args_list
                  if 'UPDATE rules_genres' in call.args[0]][0]
        self.assertEqual(update.args[1][2], 'system')

    def test_a_user_decision_is_attributed_to_that_user(self):
        self.cursor.fetchone.return_value = {'id': 1}
        with patch.object(users_router, 'verify_token',
                          return_value={'status': 'ok', 'type': 'user', 'user': {'username': 'user'}}):
            self.client.post('/api/rules/genres/1/decide', headers={'x-api-key': 'user-key'},
                             json={'state': management_router.WHITE})
        update = [call for call in self.cursor.execute.call_args_list
                  if 'UPDATE rules_genres' in call.args[0]][0]
        self.assertEqual(update.args[1][2], 'user')

    def test_duplicate_targets_are_stored_once(self):
        self.cursor.fetchone.side_effect = [{'id': 1}, {'id': 8}]
        self.decide({'state': management_router.BLACK, 'canonical_ids': [8, 8]})
        inserts = [call.args[1] for call in self.cursor.execute.call_args_list
                   if 'INSERT INTO rules_genre_expansions' in call.args[0]]
        self.assertEqual(inserts, [(1, 8, 0)])


class ArtistAndLabelRulesTest(ManagementTestCase):

    def test_the_artist_genre_rules_are_listed(self):
        self.cursor.fetchall.return_value = [{'id': 1, 'artist_name': 'Angerfist'}]
        response = self.client.get('/api/rules/artist-genres', headers=self.headers)
        self.assertEqual(response.json()[0]['artist_name'], 'Angerfist')

    def test_an_artist_genre_rule_can_be_added(self):
        response = self.client.post('/api/rules/artist-genres', headers=self.headers,
                                    json={'artist_name': 'Angerfist', 'genre_id': 3})
        self.assertEqual(response.json(), {'status': 'ok'})
        self.assertEqual(self.cursor.execute.call_args.args[1], ('Angerfist', 3))

    def test_an_artist_genre_rule_can_be_removed(self):
        response = self.client.delete('/api/rules/artist-genres/5', headers=self.headers)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_the_label_genre_rules_are_listed(self):
        self.cursor.fetchall.return_value = [{'id': 1, 'label_name': 'Scantraxx'}]
        response = self.client.get('/api/rules/label-genres', headers=self.headers)
        self.assertEqual(response.json()[0]['label_name'], 'Scantraxx')

    def test_a_label_genre_rule_can_be_added(self):
        response = self.client.post('/api/rules/label-genres', headers=self.headers,
                                    json={'label_name': 'Scantraxx', 'genre_id': 3})
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
        with patch('services.music_manager.routers.scrobbler.trigger_lb_import',
                   return_value={'status': 'ok'}) as proxied:
            result = management_router.trigger_lb_import_proxy(MagicMock(), {'username': 'user'},
                                                               {'type': 'system'})
        self.assertEqual(result, {'status': 'ok'})
        proxied.assert_called_once()

    def test_the_whole_library_can_be_flagged_for_a_retag(self):
        with patch.object(management_router, 'ProcessedFilesHelper') as helper:
            body = self.client.post('/api/tagger/rescan', headers=self.headers).json()
        self.assertEqual(body['status'], 'ok')
        helper.return_value.mark_for_rescan.assert_called_once_with()

    def test_a_single_file_can_be_flagged_for_a_retag(self):
        with patch.object(management_router, 'ProcessedFilesHelper') as helper:
            body = self.client.post('/api/tagger/rescan/file', headers=self.headers,
                                    json={'filepath': '/music/a.mp3'}).json()
        self.assertEqual(body['status'], 'ok')
        helper.return_value.mark_for_rescan.assert_called_once_with('/music/a.mp3')


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
            [{'podcast_id': 1, 'alias': "Isaac's Hardstyle Sessions"},
             {'podcast_id': 1, 'alias': 'DJ ISAAC - HARDSTYLE SESSIONS'}],
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
        moves = [call.args[1] for call in self.cursor.execute.call_args_list
                 if 'UPDATE rules_podcast_aliases' in call.args[0]]
        self.assertEqual(moves, [(9, 1)])
        self.assertTrue(any('DELETE FROM rules_podcasts' in s for s in self.statements()))

    def test_a_merge_does_not_also_write_a_state(self):
        self.cursor.fetchone.side_effect = [{'id': 1, 'name': 'x'}, {'id': 9}]
        self.decide({'state': management_router.WHITE, 'merge_into_podcast_id': 9})
        self.assertFalse(any('UPDATE rules_podcasts' in s for s in self.statements()))

    def test_a_system_decision_is_attributed_to_the_system(self):
        self.cursor.fetchone.return_value = {'id': 1, 'name': 'x'}
        self.decide({'state': management_router.WHITE})
        update = [call for call in self.cursor.execute.call_args_list
                  if 'UPDATE rules_podcasts' in call.args[0]][0]
        self.assertEqual(update.args[1][3], 'system')

    def test_the_host_and_station_are_stored_when_given(self):
        self.cursor.fetchone.return_value = {'id': 1, 'name': 'x'}
        self.decide({'state': management_router.WHITE, 'host': 'DJ Isaac', 'station': 'Q-dance'})
        update = [call for call in self.cursor.execute.call_args_list
                  if 'UPDATE rules_podcasts' in call.args[0]][0]
        self.assertEqual(update.args[1][1:3], ('DJ Isaac', 'Q-dance'))


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
        return self.client.post(f'/api/label-proposals/{proposal_id}/confirm', json={'label': label}, headers=self.headers)

    def test_the_open_proposals_are_listed(self):
        self.cursor.fetchall.return_value = [
            {'id': 1, 'folder': 'BKRP104 - Darwin', 'catid': 'BKRP', 'proposed_label': 'Brutal Kuts',
             'source': 'tag:label', 'confidence': 90, 'status': 'new'}
        ]

        response = self.client.get('/api/label-proposals', headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]['proposed_label'], 'Brutal Kuts')
        self.assertEqual(response.json()[0]['folder'], 'BKRP104 - Darwin')

    def test_confirming_a_proposal_with_a_cat_id_writes_the_label_rule(self):
        self.cursor.fetchone.return_value = {'id': 1, 'folder': 'BKRP104 - Darwin', 'catid': 'BKRP', 'proposed_label': 'Brutal Kuts'}

        response = self.confirm(1, 'Brutal Kuts')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any('rules_catid_label' in s for s in self.statements()))

    def test_confirming_a_proposal_with_a_cat_id_moves_nothing_itself(self):
        self.cursor.fetchone.return_value = {'id': 1, 'folder': 'BKRP104 - Darwin', 'catid': 'BKRP', 'proposed_label': 'Brutal Kuts'}

        with patch.object(management_router, 'shutil') as shutil_module:
            self.confirm(1, 'Brutal Kuts')

        shutil_module.move.assert_not_called()

    def test_confirming_a_proposal_without_a_cat_id_moves_the_folder(self):
        self.cursor.fetchone.return_value = {'id': 2, 'folder': ' - Dewstate', 'catid': None, 'proposed_label': None}

        with patch.object(management_router, 'shutil') as shutil_module, \
             patch.object(management_router, 'folder_exists', return_value=True):
            response = self.confirm(2, 'Different Solution Records')

        self.assertEqual(response.status_code, 200)
        shutil_module.move.assert_called_once_with('/import/ - Dewstate', '/eps/Different Solution Records/ - Dewstate')

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


if __name__ == '__main__':
    unittest.main()
