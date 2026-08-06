"""Coverage for the /api/library, /api/jobs and /api/scrobble routers."""
import asyncio
import sys
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.easyid3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())

import services.music_manager.routers.users as users_router

users_router.run_lms_db_sync = lambda: None

from fastapi.testclient import TestClient

from services.music_manager.main import app
from services.music_manager.routers import jobs as jobs_router
from services.music_manager.routers import library as library_router
from services.music_manager.routers import scrobbler as scrobbler_router

API_KEY = library_router.API_KEY


class RouterTestCase(unittest.TestCase):
    module = None

    def setUp(self):
        self.client = TestClient(app)
        self.headers = {'x-api-key': API_KEY}
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = self.cursor
        self.conn.cursor.return_value.__exit__.return_value = False
        patcher = patch.object(self.module, 'get_db_connection', return_value=self.conn)
        patcher.start()
        self.addCleanup(patcher.stop)

    def statements(self):
        return [call.args[0] for call in self.cursor.execute.call_args_list]


class LibraryAuthTest(unittest.TestCase):

    def test_a_request_without_a_key_is_unauthorized(self):
        self.assertEqual(TestClient(app).get('/api/library/genres').status_code, 401)

    def test_a_user_key_that_verifies_is_accepted(self):
        with patch.object(users_router, 'verify_token', return_value={'status': 'ok', 'type': 'user'}), \
             patch.object(library_router, 'get_db_connection', return_value=None):
            response = TestClient(app).get('/api/library/genres', headers={'x-api-key': 'user-key'})
        self.assertEqual(response.status_code, 500)

    def test_a_key_that_does_not_verify_is_rejected(self):
        with patch.object(users_router, 'verify_token', side_effect=Exception('nope')):
            response = TestClient(app).get('/api/library/genres', headers={'x-api-key': 'bad'})
        self.assertEqual(response.status_code, 401)

    def test_a_key_that_verifies_without_an_ok_status_is_rejected(self):
        with patch.object(users_router, 'verify_token', return_value={'status': 'nope'}):
            response = TestClient(app).get('/api/library/genres', headers={'x-api-key': 'bad'})
        self.assertEqual(response.status_code, 401)


class LibraryTracksTest(RouterTestCase):
    module = library_router

    def test_tracks_are_returned_with_their_total(self):
        self.cursor.fetchall.return_value = [{'id': 1, 'title': 'Track'}]
        self.cursor.fetchone.return_value = {'total': 1}
        response = self.client.get('/api/library/tracks', headers=self.headers)
        body = response.json()
        self.assertEqual(body['total'], 1)
        self.assertEqual(body['page'], 1)

    def test_the_search_term_is_applied_to_title_artist_and_label(self):
        self.cursor.fetchall.return_value = []
        self.cursor.fetchone.return_value = {'total': 0}
        self.client.get('/api/library/tracks?q=anger', headers=self.headers)
        params = self.cursor.execute.call_args_list[0].args[1]
        self.assertEqual(params[:3], ('%anger%', '%anger%', '%anger%'))

    def test_paging_translates_into_an_offset(self):
        self.cursor.fetchall.return_value = []
        self.cursor.fetchone.return_value = {'total': 0}
        self.client.get('/api/library/tracks?page=3&limit=10', headers=self.headers)
        params = self.cursor.execute.call_args_list[0].args[1]
        self.assertEqual(params[-2:], (10, 20))

    def test_a_database_outage_is_reported_as_a_server_error(self):
        with patch.object(library_router, 'get_db_connection', return_value=None):
            response = self.client.get('/api/library/tracks', headers=self.headers)
        self.assertEqual(response.status_code, 500)


class LibraryAdvancedTest(RouterTestCase):
    module = library_router

    def test_the_concatenated_genres_are_split_into_a_list(self):
        self.cursor.fetchall.return_value = [{'id': 1, 'genres': 'Hardcore,Uptempo'}]
        self.cursor.fetchone.return_value = {'total': 1}
        response = self.client.get('/api/library/advanced', headers=self.headers)
        self.assertEqual(response.json()['tracks'][0]['genres'], ['Hardcore', 'Uptempo'])

    def test_a_track_without_genres_gets_an_empty_list(self):
        self.cursor.fetchall.return_value = [{'id': 1, 'genres': None}]
        self.cursor.fetchone.return_value = {'total': 1}
        response = self.client.get('/api/library/advanced', headers=self.headers)
        self.assertEqual(response.json()['tracks'][0]['genres'], [])

    def test_page_zero_does_not_produce_a_negative_offset(self):
        self.cursor.fetchall.return_value = []
        self.cursor.fetchone.return_value = {'total': 0}
        self.client.get('/api/library/advanced?page=0&limit=10', headers=self.headers)
        self.assertEqual(self.cursor.execute.call_args_list[0].args[1][-1], 0)

    def test_a_database_outage_is_reported_as_a_server_error(self):
        with patch.object(library_router, 'get_db_connection', return_value=None):
            response = self.client.get('/api/library/advanced', headers=self.headers)
        self.assertEqual(response.status_code, 500)


class LibraryGenresTest(RouterTestCase):
    module = library_router

    def test_blacklisted_genres_are_left_out(self):
        self.cursor.fetchall.return_value = [{'genre': 'Hardcore', 'state': 'white', 'count': 3}]
        response = self.client.get('/api/library/genres', headers=self.headers)
        self.assertEqual(response.json()[0]['genre'], 'Hardcore')
        self.assertIn("state <> 'black'", self.statements()[0])


class RerunParseTest(RouterTestCase):
    module = library_router

    def test_a_track_is_flagged_and_immediately_retagged(self):
        self.cursor.fetchone.return_value = {'file_path': '/music/a.mp3'}
        with patch.object(library_router, 'ProcessedFilesHelper') as helper, \
             patch('services.music_manager.routers.tagger.tagger_manager') as tagger, \
             patch('services.music_manager.routers.scanner.scanner_manager') as scanner:
            response = self.client.post('/api/library/tracks/1/rerun-parse', headers=self.headers)
        self.assertEqual(response.json()['status'], 'ok')
        helper.return_value.mark_for_rescan.assert_called_once_with('/music/a.mp3')
        tagger.tag_single.assert_called_once_with('/music/a.mp3')
        scanner.scan_single.assert_called_once_with('/music/a.mp3')

    def test_a_track_without_a_file_is_a_not_found(self):
        self.cursor.fetchone.return_value = None
        with patch.object(library_router, 'ProcessedFilesHelper'):
            response = self.client.post('/api/library/tracks/1/rerun-parse', headers=self.headers)
        self.assertEqual(response.status_code, 404)

    def test_a_failing_immediate_retag_still_leaves_the_track_flagged(self):
        self.cursor.fetchone.return_value = {'file_path': '/music/a.mp3'}
        with patch.object(library_router, 'ProcessedFilesHelper') as helper, \
             patch('services.music_manager.routers.tagger.tagger_manager') as tagger:
            tagger.tag_single.side_effect = RuntimeError('tagger busy')
            response = self.client.post('/api/library/tracks/1/rerun-parse', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        helper.return_value.mark_for_rescan.assert_called_once()

    def test_a_file_can_also_be_flagged_by_path(self):
        with patch.object(library_router, 'ProcessedFilesHelper') as helper, \
             patch('services.music_manager.routers.tagger.tagger_manager') as tagger, \
             patch('services.music_manager.routers.scanner.scanner_manager') as scanner:
            response = self.client.post('/api/library/tracks/rerun-parse-path?path=/music/b.mp3',
                                        headers=self.headers)
        self.assertEqual(response.json()['status'], 'ok')
        helper.return_value.mark_for_rescan.assert_called_once_with('/music/b.mp3')
        tagger.tag_single.assert_called_once_with('/music/b.mp3')
        scanner.scan_single.assert_called_once_with('/music/b.mp3')

    def test_a_failing_retag_by_path_is_still_reported_as_accepted(self):
        with patch.object(library_router, 'ProcessedFilesHelper'), \
             patch('services.music_manager.routers.tagger.tagger_manager') as tagger:
            tagger.tag_single.side_effect = RuntimeError('tagger busy')
            response = self.client.post('/api/library/tracks/rerun-parse-path?path=/music/b.mp3',
                                        headers=self.headers)
        self.assertEqual(response.status_code, 200)


class RedownloadTest(RouterTestCase):
    module = library_router

    def setUp(self):
        super().setUp()
        # TestClient runs background tasks inline; the real task would reach for yt-dlp.
        patcher = patch.object(library_router, 'run_redownload_task')
        self.redownload_task = patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_soundcloud_track_is_queued_for_redownload(self):
        self.cursor.fetchone.side_effect = [
            {'file_path': '/music/a.mp3'},
            {'url': 'https://soundcloud.com/x/y'},
        ]
        response = self.client.post('/api/library/tracks/1/redownload', headers=self.headers)
        self.assertIn('soundcloud', response.json()['message'])

    def test_a_youtube_track_is_queued_when_soundcloud_has_nothing(self):
        self.cursor.fetchone.side_effect = [
            {'file_path': '/music/a.mp3'},
            None,
            {'url': 'https://youtube.com/watch?v=x'},
        ]
        response = self.client.post('/api/library/tracks/1/redownload', headers=self.headers)
        self.assertIn('youtube', response.json()['message'])

    def test_a_track_without_a_source_url_cannot_be_redownloaded(self):
        self.cursor.fetchone.side_effect = [{'file_path': '/music/a.mp3'}, None, None]
        response = self.client.post('/api/library/tracks/1/redownload', headers=self.headers)
        self.assertEqual(response.status_code, 400)

    def test_a_track_without_a_file_is_a_not_found(self):
        self.cursor.fetchone.return_value = None
        response = self.client.post('/api/library/tracks/1/redownload', headers=self.headers)
        self.assertEqual(response.status_code, 404)


class RedownloadTaskTest(unittest.TestCase):

    def test_a_soundcloud_redownload_uses_the_soundcloud_downloader(self):
        downloader_module = MagicMock()
        with patch.dict(sys.modules, {'services.downloader.soundcloud.soundcloud': downloader_module}):
            library_router.run_redownload_task('https://soundcloud.com/x', 'soundcloud')
        downloader = downloader_module.SoundcloudDownloader.return_value
        downloader.download_url.assert_called_once()
        self.assertTrue(downloader.redownload_mode)

    def test_a_youtube_redownload_uses_the_youtube_downloader(self):
        downloader_module = MagicMock()
        with patch.dict(sys.modules, {'services.downloader.youtube.youtube': downloader_module}):
            library_router.run_redownload_task('https://youtube.com/x', 'youtube')
        downloader_module.YoutubeDownloader.return_value.download_link.assert_called_once()

    def test_an_unknown_source_type_does_nothing(self):
        library_router.run_redownload_task('https://example.test/x', 'bandcamp')  # must not raise

    def test_a_failing_redownload_is_logged_rather_than_raised(self):
        downloader_module = MagicMock()
        downloader_module.SoundcloudDownloader.side_effect = RuntimeError('yt-dlp missing')
        with patch.dict(sys.modules, {'services.downloader.soundcloud.soundcloud': downloader_module}):
            library_router.run_redownload_task('https://soundcloud.com/x', 'soundcloud')  # must not raise


class ScrobbleEventTest(RouterTestCase):
    module = scrobbler_router

    def test_a_listen_for_a_known_track_is_stored_against_that_track(self):
        self.cursor.fetchone.return_value = {'id': 42}
        payload = {'artist_name': 'Angerfist', 'track_title': 'Raise Your Fist', 'username': 'user'}
        response = self.client.post('/api/scrobble/event', headers=self.headers, json=payload)
        self.assertTrue(response.json()['matched'])
        self.assertIn('INSERT INTO scrobble_listens', self.statements()[1])

    def test_a_listen_for_an_unknown_track_is_parked_as_unmatched(self):
        self.cursor.fetchone.return_value = None
        payload = {'artist_name': 'Nobody', 'track_title': 'Nothing', 'username': 'user'}
        response = self.client.post('/api/scrobble/event', headers=self.headers, json=payload)
        self.assertFalse(response.json()['matched'])
        self.assertIn('scrobble_unmatched_listens', self.statements()[1])

    def test_a_supplied_timestamp_is_used(self):
        self.cursor.fetchone.return_value = {'id': 42}
        payload = {'artist_name': 'A', 'track_title': 'B', 'username': 'user', 'listened_at': 1_700_000_000}
        self.client.post('/api/scrobble/event', headers=self.headers, json=payload)
        stored = self.cursor.execute.call_args.args[1][1]
        self.assertEqual(stored.year, 2023)

    def test_a_database_outage_is_reported_as_a_server_error(self):
        with patch.object(scrobbler_router, 'get_db_connection', return_value=None):
            payload = {'artist_name': 'A', 'track_title': 'B', 'username': 'user'}
            response = self.client.post('/api/scrobble/event', headers=self.headers, json=payload)
        self.assertEqual(response.status_code, 500)


class ListenBrainzImportTest(RouterTestCase):
    module = scrobbler_router

    def setUp(self):
        super().setUp()
        # TestClient runs background tasks inline; the real import would call ListenBrainz.
        patcher = patch.object(scrobbler_router, 'run_listenbrainz_import')
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_latest_imports_are_listed(self):
        self.cursor.fetchall.return_value = [{'id': 1, 'status': 'completed'}]
        response = self.client.get('/api/scrobble/import/latest', headers=self.headers)
        self.assertEqual(response.json()[0]['status'], 'completed')

    def test_an_import_is_registered_and_queued(self):
        self.cursor.lastrowid = 7
        response = self.client.post('/api/scrobble/import/listenbrainz', headers=self.headers,
                                    json={'username': 'user', 'lb_username': 'user-lb'})
        self.assertEqual(response.json()['import_id'], 7)
        self.assertEqual(response.json()['lb_username'], 'user-lb')

    def test_without_a_listenbrainz_name_the_local_username_is_used(self):
        self.cursor.lastrowid = 8
        response = self.client.post('/api/scrobble/import/listenbrainz', headers=self.headers,
                                    json={'username': 'user'})
        self.assertEqual(response.json()['lb_username'], 'user')


class ProcessListensPageTest(unittest.TestCase):

    def setUp(self):
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = self.cursor
        self.conn.cursor.return_value.__exit__.return_value = False

    def listen(self, artist='Angerfist', title='Raise Your Fist', ts=1_700_000_000):
        return {'track_metadata': {'artist_name': artist, 'track_name': title, 'release_name': 'Album'},
                'listened_at': ts}

    def test_a_matched_listen_is_stored_against_the_track(self):
        self.cursor.fetchone.return_value = {'id': 42}
        processed, max_ts = scrobbler_router._process_listens_page([self.listen()], self.conn, 'user', 1, 1)
        self.assertEqual(processed, 1)
        self.assertEqual(max_ts, 1_700_000_000)
        self.assertTrue(any('INSERT INTO scrobble_listens' in call.args[0]
                            for call in self.cursor.execute.call_args_list))

    def test_an_unmatched_listen_is_parked(self):
        self.cursor.fetchone.return_value = None
        scrobbler_router._process_listens_page([self.listen()], self.conn, 'user', 1, 1)
        self.assertTrue(any('scrobble_unmatched_listens' in call.args[0]
                            for call in self.cursor.execute.call_args_list))

    def test_an_incomplete_listen_is_skipped(self):
        self.cursor.fetchone.return_value = {'id': 42}
        processed, _ = scrobbler_router._process_listens_page(
            [self.listen(artist=None), self.listen(title=None)], self.conn, 'user', 1, 2)
        self.assertEqual(processed, 0)

    def test_the_oldest_timestamp_of_the_page_is_returned_for_paging(self):
        self.cursor.fetchone.return_value = {'id': 42}
        _, max_ts = scrobbler_router._process_listens_page(
            [self.listen(ts=200), self.listen(ts=100)], self.conn, 'user', 1, 2)
        self.assertEqual(max_ts, 100)

    def test_progress_is_written_back_every_ten_listens(self):
        self.cursor.fetchone.return_value = {'id': 42}
        listens = [self.listen(ts=1000 - i) for i in range(10)]
        scrobbler_router._process_listens_page(listens, self.conn, 'user', 1, 10)
        progress_updates = [call for call in self.cursor.execute.call_args_list
                            if 'SET processed' in call.args[0]]
        self.assertEqual(len(progress_updates), 1)


class RunListenBrainzImportTest(unittest.TestCase):

    def setUp(self):
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = self.cursor
        self.conn.cursor.return_value.__exit__.return_value = False
        patches = [
            patch.object(scrobbler_router, 'get_db_connection', return_value=self.conn),
            patch.object(scrobbler_router.time, 'sleep'),
            patch('builtins.print'),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def page(self, count):
        return {'payload': {'listens': [{'track_metadata': {'artist_name': 'A', 'track_name': 'B'},
                                         'listened_at': 1_700_000_000 - i} for i in range(count)]}}

    def test_an_import_that_finds_nothing_is_still_marked_completed(self):
        with patch.object(scrobbler_router, 'requests') as http:
            http.get.return_value.json.return_value = {'payload': {'listens': []}}
            scrobbler_router.run_listenbrainz_import(1, 'user', 'user-lb')
        self.assertTrue(any("status = 'completed'" in call.args[0]
                            for call in self.cursor.execute.call_args_list))

    def test_a_short_page_ends_the_import(self):
        self.cursor.fetchone.return_value = {'id': 42}
        with patch.object(scrobbler_router, 'requests') as http:
            http.get.return_value.json.return_value = self.page(3)
            scrobbler_router.run_listenbrainz_import(1, 'user', 'user-lb')
        self.assertEqual(http.get.call_count, 1)

    def test_a_full_page_is_followed_by_another_request(self):
        self.cursor.fetchone.return_value = {'id': 42}
        with patch.object(scrobbler_router, 'requests') as http:
            http.get.return_value.json.side_effect = [self.page(100), {'payload': {'listens': []}}]
            scrobbler_router.run_listenbrainz_import(1, 'user', 'user-lb')
        self.assertEqual(http.get.call_count, 2)

    def test_a_token_is_sent_as_an_authorization_header(self):
        with patch.object(scrobbler_router, 'requests') as http:
            http.get.return_value.json.return_value = {'payload': {'listens': []}}
            scrobbler_router.run_listenbrainz_import(1, 'user', 'user-lb', token='tok')
        self.assertEqual(http.get.call_args.kwargs['headers'], {'Authorization': 'Token tok'})

    def test_a_failing_import_is_recorded_as_failed(self):
        with patch.object(scrobbler_router, 'requests') as http:
            http.get.side_effect = RuntimeError('listenbrainz down')
            scrobbler_router.run_listenbrainz_import(1, 'user', 'user-lb')
        self.assertTrue(any("status = 'failed'" in call.args[0]
                            for call in self.cursor.execute.call_args_list))

    def test_an_import_without_a_database_connection_ends_immediately(self):
        with patch.object(scrobbler_router, 'get_db_connection', return_value=None), \
             patch.object(scrobbler_router, 'requests') as http:
            scrobbler_router.run_listenbrainz_import(1, 'user', 'user-lb')
        http.get.assert_not_called()


class JobManagerTest(unittest.TestCase):

    def setUp(self):
        self.manager = jobs_router.JobManager()

    def test_a_pipeline_run_reports_progress_and_finishes(self):
        step = MagicMock()
        step.name = 'Extractor'
        asyncio.run(self.manager.run('job-1', [step], ['all']))
        self.assertEqual(self.manager.jobs['job-1']['status'], 'finished')
        self.assertEqual(self.manager.jobs['job-1']['progress'], 1)
        self.assertEqual(list(self.manager.history), ['job-1'])
        step.run.assert_called_once_with(['all'])

    def test_a_listener_is_sent_the_current_state_on_connect(self):
        websocket = MagicMock()
        websocket.accept = MagicMock(return_value=asyncio.sleep(0))
        sent = []

        async def send_json(payload):
            sent.append(payload)

        websocket.send_json = send_json
        self.manager.jobs['job-1'] = {'status': 'running'}
        asyncio.run(self.manager.connect('job-1', websocket))
        self.assertEqual(sent, [{'status': 'running'}])

    def test_a_listener_for_an_unknown_job_is_only_accepted(self):
        websocket = MagicMock()
        websocket.accept = MagicMock(return_value=asyncio.sleep(0))
        websocket.send_json = MagicMock(side_effect=AssertionError('should not send'))
        asyncio.run(self.manager.connect('unknown', websocket))
        self.assertIn(websocket, self.manager.connections['unknown'])

    def test_a_listener_can_be_disconnected(self):
        websocket = MagicMock()
        self.manager.connections['job-1'].append(websocket)
        self.manager.disconnect('job-1', websocket)
        self.assertEqual(self.manager.connections['job-1'], [])

    def test_disconnecting_an_unknown_job_is_harmless(self):
        self.manager.disconnect('nope', MagicMock())  # must not raise

    def test_a_listener_that_dropped_is_removed_on_the_next_notify(self):
        websocket = MagicMock()

        async def send_json(_payload):
            raise jobs_router.WebSocketDisconnect()

        websocket.send_json = send_json
        self.manager.connections['job-1'].append(websocket)
        self.manager.jobs['job-1'] = {'status': 'running'}
        asyncio.run(self.manager._notify('job-1'))
        self.assertEqual(self.manager.connections['job-1'], [])

    def test_publishing_outside_a_job_does_nothing(self):
        async def publish():
            self.manager.publish({'message': 'hello'})

        asyncio.run(publish())  # must not raise

    def test_publishing_inside_a_job_notifies_its_listeners(self):
        sent = []

        async def send_json(payload):
            sent.append(payload)

        websocket = MagicMock()
        websocket.send_json = send_json
        self.manager.connections['job-1'].append(websocket)

        async def publish():
            token = jobs_router.current_job_id.set('job-1')
            try:
                self.manager.publish({'message': 'hello'})
                await asyncio.sleep(0)
            finally:
                jobs_router.current_job_id.reset(token)

        asyncio.run(publish())
        self.assertEqual(sent, [{'message': 'hello'}])

    def test_creating_a_job_schedules_it_and_hands_back_an_id(self):
        step = MagicMock()
        step.name = 'Extractor'

        async def create():
            job_id = self.manager.create_job([step], ['all'])
            await asyncio.sleep(0.05)
            return job_id

        job_id = asyncio.run(create())
        self.assertIn(job_id, self.manager.results)

    def test_recent_returns_the_finished_jobs_newest_first(self):
        self.manager.results = {'a': {'status': 'finished'}, 'b': {'status': 'finished'}}
        self.manager.history.extend(['a', 'b'])
        self.assertEqual(len(self.manager.recent()), 2)


class JobEndpointTest(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        jobs_router.job_manager.jobs.clear()
        jobs_router.job_manager.results.clear()
        jobs_router.job_manager.history.clear()

    def test_a_running_external_job_is_registered_but_not_archived(self):
        response = self.client.post('/api/jobs/register/ext-1', json={'status': 'running'})
        self.assertEqual(response.json(), {'status': 'ok'})
        self.assertIn('ext-1', jobs_router.job_manager.jobs)
        self.assertNotIn('ext-1', jobs_router.job_manager.results)

    def test_a_finished_external_job_lands_in_the_history(self):
        self.client.post('/api/jobs/register/ext-2', json={'status': 'finished'})
        self.assertIn('ext-2', jobs_router.job_manager.results)
        self.assertIn('ext-2', jobs_router.job_manager.history)

    def test_the_same_finished_job_is_not_archived_twice(self):
        self.client.post('/api/jobs/register/ext-3', json={'status': 'finished'})
        self.client.post('/api/jobs/register/ext-3', json={'status': 'finished'})
        self.assertEqual(list(jobs_router.job_manager.history).count('ext-3'), 1)

    def test_the_active_jobs_are_listed(self):
        self.client.post('/api/jobs/register/ext-4', json={'status': 'running'})
        response = self.client.get('/api/jobs/active')
        self.assertIn('ext-4', response.json()['jobs'])

    def test_the_job_history_is_listed(self):
        self.client.post('/api/jobs/register/ext-5', json={'status': 'completed'})
        response = self.client.get('/api/jobs/history')
        self.assertEqual(len(response.json()['history']), 1)

    def test_a_websocket_listener_receives_the_job_state(self):
        jobs_router.job_manager.jobs['ext-6'] = {'status': 'running'}
        with self.client.websocket_connect('/api/jobs/ws/jobs/ext-6') as websocket:
            self.assertEqual(websocket.receive_json(), {'status': 'running'})


if __name__ == '__main__':
    unittest.main()
