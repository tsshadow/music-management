"""Coverage for the scanner/tagger routers and the ntfy listener."""
import sys
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.easyid3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())

import services.music_manager.ntfy_listener as ntfy_listener

ntfy_listener.start_ntfy_listener = lambda: None
import services.music_manager.routers.users as users_router

users_router.run_lms_db_sync = lambda: None

from fastapi.testclient import TestClient

from services.music_manager.main import app
from services.music_manager.routers import scanner as scanner_router
from services.music_manager.routers import tagger as tagger_router

API_KEY = users_router.API_KEY


class ScannerEndpointTest(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.headers = {'x-api-key': API_KEY}

    def test_the_health_endpoint_reports_whether_a_scan_is_running(self):
        body = self.client.get('/api/scanner/health').json()
        self.assertEqual(body['status'], 'OK')
        self.assertFalse(body['busy'])

    def test_a_full_scan_is_started_in_the_background(self):
        with patch.object(scanner_router.scanner_manager, 'run_full') as run_full:
            body = self.client.post('/api/scanner/scan/all', headers=self.headers).json()
        self.assertIn('started', body['message'])
        run_full.assert_called_once_with(force=False)

    def test_the_force_flag_reaches_the_scanner(self):
        with patch.object(scanner_router.scanner_manager, 'run_full') as run_full:
            self.client.post('/api/scanner/scan/all?force=true', headers=self.headers)
        run_full.assert_called_once_with(force=True)

    def test_a_second_full_scan_is_refused_while_one_is_running(self):
        with patch.object(scanner_router.scanner_manager, '_lock', MagicMock(locked=lambda: True)):
            response = self.client.post('/api/scanner/scan/all', headers=self.headers)
        self.assertEqual(response.status_code, 409)

    def test_a_single_file_can_be_scanned(self):
        with patch.object(scanner_router.scanner_manager, 'scan_single') as scan_single:
            body = self.client.post('/api/scanner/scan/file?path=/music/a.mp3', headers=self.headers).json()
        self.assertIn('/music/a.mp3', body['message'])
        scan_single.assert_called_once_with('/music/a.mp3', force=False)

    def test_a_request_without_a_key_is_unauthorized(self):
        self.assertEqual(self.client.post('/api/scanner/scan/all').status_code, 401)

    def test_the_background_loop_scans_and_then_sleeps(self):
        with patch.object(scanner_router.scanner_manager, 'run_full') as run_full, \
             patch.object(scanner_router.time, 'sleep', side_effect=[None, KeyboardInterrupt]):
            with self.assertRaises(KeyboardInterrupt):
                scanner_router.run_scanner_loop(sleeptime=1)
        self.assertEqual(run_full.call_count, 2)


class ScannerManagerTest(unittest.TestCase):

    def setUp(self):
        self.manager = scanner_router.ScannerManager()
        self.manager.music_path = '/music'
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = self.cursor
        self.conn.cursor.return_value.__exit__.return_value = False
        patcher = patch.object(scanner_router, 'get_db_connection', return_value=self.conn)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_same_path_always_hashes_the_same(self):
        self.assertEqual(self.manager.get_file_hash('/music/a.mp3'),
                         self.manager.get_file_hash('/music/a.mp3'))
        self.assertNotEqual(self.manager.get_file_hash('/music/a.mp3'),
                            self.manager.get_file_hash('/music/b.mp3'))

    def test_scanning_a_missing_file_reports_failure(self):
        with patch.object(scanner_router.os.path, 'exists', return_value=False):
            self.assertFalse(self.manager.scan_single('/music/gone.mp3'))

    def test_scanning_without_a_database_reports_failure(self):
        with patch.object(scanner_router, 'get_db_connection', return_value=None):
            self.assertFalse(self.manager.scan_single('/music/a.mp3'))

    def test_scanning_a_present_file_delegates_to_the_processor(self):
        with patch.object(scanner_router.os.path, 'exists', return_value=True), \
             patch.object(self.manager, '_process_file_safe', return_value=True) as process:
            self.assertTrue(self.manager.scan_single('/music/a.mp3'))
        process.assert_called_once()

    def test_a_full_run_over_a_missing_music_folder_does_nothing(self):
        self.manager.music_path = None
        with patch.object(self.manager, '_scan_recursive') as scan:
            self.manager.run_full()
        scan.assert_not_called()

    def test_a_full_run_is_skipped_while_another_one_holds_the_lock(self):
        with patch.object(scanner_router.os.path, 'exists', return_value=True), \
             patch.object(self.manager, '_lock', MagicMock(locked=lambda: True)), \
             patch.object(self.manager, '_scan_recursive') as scan:
            self.manager.run_full()
        scan.assert_not_called()

    def test_a_full_run_reloads_the_curation_rules_first(self):
        with patch.object(scanner_router.os.path, 'exists', return_value=True), \
             patch.object(self.manager.genre_helper, 'reload') as reload_rules, \
             patch.object(self.manager, '_scan_recursive', return_value=0):
            self.manager.run_full()
        reload_rules.assert_called_once()

    def test_a_full_run_without_a_database_stops_early(self):
        with patch.object(scanner_router.os.path, 'exists', return_value=True), \
             patch.object(self.manager.genre_helper, 'reload'), \
             patch.object(scanner_router, 'get_db_connection', return_value=None), \
             patch.object(self.manager, '_scan_recursive') as scan:
            self.manager.run_full()
        scan.assert_not_called()

    def test_hidden_files_are_not_scanned(self):
        with patch.object(scanner_router.os, 'walk', return_value=[('/music', [], ['.DS_Store', 'a.mp3'])]), \
             patch.object(self.manager, '_process_file_safe', return_value=True) as process:
            self.assertEqual(self.manager._scan_recursive(self.conn, False), 1)
        process.assert_called_once_with(self.conn, '/music/a.mp3', False)

    def test_an_unsupported_extension_is_skipped_quietly(self):
        with patch.object(self.manager, 'process_file',
                          side_effect=scanner_router.ExtensionNotSupportedException('.txt')):
            self.assertFalse(self.manager._process_file_safe(self.conn, '/music/a.txt', False))

    def test_an_unexpected_processing_error_is_logged_and_skipped(self):
        with patch.object(self.manager, 'process_file', side_effect=RuntimeError('bad tags')):
            self.assertFalse(self.manager._process_file_safe(self.conn, '/music/a.mp3', False))


class ResolveGenreIdsTest(unittest.TestCase):

    def setUp(self):
        self.manager = scanner_router.ScannerManager()
        self.helper = MagicMock()
        self.manager.genre_helper = self.helper
        self.helper.split_composite.side_effect = lambda raw: [raw]

    def song_with(self, genres):
        song = MagicMock()
        song.genres.return_value = genres
        return song

    def decision(self, state, values):
        return MagicMock(state=state, values=values)

    def test_a_curated_genre_resolves_to_its_row_id(self):
        self.helper.resolve.return_value = self.decision('white', ['Uptempo Hardcore'])
        self.helper.get_row.return_value = MagicMock(id=7)
        self.assertEqual(self.manager._resolve_genre_ids(self.song_with(['uptempo'])), [7])

    def test_a_blacklisted_genre_is_dropped(self):
        self.helper.resolve.return_value = self.decision(scanner_router.BLACK, ['Junk'])
        self.assertEqual(self.manager._resolve_genre_ids(self.song_with(['junk'])), [])

    def test_an_expansion_yields_every_target(self):
        self.helper.resolve.return_value = self.decision('white', ['Uptempo Hardcore', 'Terror'])
        self.helper.get_row.side_effect = [MagicMock(id=7), MagicMock(id=8)]
        self.assertEqual(self.manager._resolve_genre_ids(self.song_with(['upterror'])), [7, 8])

    def test_the_same_target_is_not_added_twice(self):
        self.helper.resolve.return_value = self.decision('white', ['Hardcore'])
        self.helper.get_row.return_value = MagicMock(id=7)
        self.assertEqual(self.manager._resolve_genre_ids(self.song_with(['hardcore', 'Hardcore'])), [7])

    def test_a_target_without_a_row_is_skipped(self):
        self.helper.resolve.return_value = self.decision('unknown', ['Brand New'])
        self.helper.get_row.return_value = None
        self.assertEqual(self.manager._resolve_genre_ids(self.song_with(['brand new'])), [])

    def test_empty_genre_tags_are_ignored(self):
        self.assertEqual(self.manager._resolve_genre_ids(self.song_with(['', None])), [])

    def test_a_file_without_genres_yields_nothing(self):
        self.assertEqual(self.manager._resolve_genre_ids(self.song_with(None)), [])


class ProcessFileTest(unittest.TestCase):

    def setUp(self):
        self.manager = scanner_router.ScannerManager()
        self.manager.genre_helper = MagicMock()
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = self.cursor
        self.conn.cursor.return_value.__exit__.return_value = False
        patches = [
            patch.object(scanner_router.os.path, 'getmtime', return_value=100.0),
            patch.object(scanner_router.os.path, 'getsize', return_value=1024),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def song(self, artists=('Angerfist',), publisher='Masters of Hardcore'):
        song = MagicMock()
        song.library_artists.return_value = list(artists)
        song.publisher.return_value = publisher
        song.title.return_value = 'Raise Your Fist'
        song.length.return_value = 300
        song.genres.return_value = []
        return song

    def statements(self):
        return [call.args[0] for call in self.cursor.execute.call_args_list]

    def test_an_unchanged_file_is_skipped(self):
        self.cursor.fetchone.return_value = {'id': 1, 'file_mtime': 100.0, 'file_size': 1024}
        self.assertFalse(self.manager.process_file(self.conn, '/music/a.mp3'))

    def test_force_reprocesses_an_unchanged_file(self):
        self.cursor.fetchone.side_effect = [
            {'id': 1, 'file_mtime': 100.0, 'file_size': 1024}, {'id': 3}, {'id': 4}, {'id': 5}]
        with patch.object(scanner_router, 'ReadonlySong', return_value=self.song()), \
             patch.object(self.manager, '_resolve_genre_ids', return_value=[]):
            self.assertTrue(self.manager.process_file(self.conn, '/music/a.mp3', force=True))

    def test_a_file_that_cannot_be_read_is_skipped(self):
        self.cursor.fetchone.return_value = None
        with patch.object(scanner_router, 'ReadonlySong', side_effect=RuntimeError('bad tags')):
            self.assertFalse(self.manager.process_file(self.conn, '/music/a.mp3'))

    def test_a_new_file_creates_its_artist_label_track_and_media_row(self):
        self.cursor.fetchone.side_effect = [None, {'id': 3}, {'id': 4}, {'id': 5}]
        with patch.object(scanner_router, 'ReadonlySong', return_value=self.song()), \
             patch.object(self.manager, '_resolve_genre_ids', return_value=[9]):
            self.assertTrue(self.manager.process_file(self.conn, '/music/a.mp3'))
        statements = self.statements()
        self.assertTrue(any('INSERT IGNORE INTO library_artists' in s for s in statements))
        self.assertTrue(any('INSERT IGNORE INTO library_labels' in s for s in statements))
        self.assertTrue(any('INSERT INTO library_tracks' in s for s in statements))
        self.assertTrue(any('INSERT IGNORE INTO library_track_labels' in s for s in statements))
        self.assertTrue(any('INSERT INTO library_media_files' in s for s in statements))

    def test_the_first_artist_becomes_the_primary_and_the_rest_featuring(self):
        self.cursor.fetchone.side_effect = [None, {'id': 3}, {'id': 4}, {'id': 5}, {'id': 6}]
        with patch.object(scanner_router, 'ReadonlySong',
                          return_value=self.song(artists=('Angerfist', 'Outsiders'), publisher=None)), \
             patch.object(self.manager, '_resolve_genre_ids', return_value=[]):
            self.manager.process_file(self.conn, '/music/a.mp3')
        roles = [call.args[1][2] for call in self.cursor.execute.call_args_list
                 if 'library_track_artists' in call.args[0] and 'DELETE' not in call.args[0]]
        self.assertEqual(roles, ['primary', 'featuring'])

    def test_a_file_without_a_publisher_gets_no_label_row(self):
        self.cursor.fetchone.side_effect = [None, {'id': 3}, {'id': 5}]
        with patch.object(scanner_router, 'ReadonlySong',
                          return_value=self.song(publisher=None)), \
             patch.object(self.manager, '_resolve_genre_ids', return_value=[]):
            self.manager.process_file(self.conn, '/music/a.mp3')
        self.assertFalse(any('library_track_labels' in s for s in self.statements()))

    def test_empty_artist_names_are_ignored(self):
        self.cursor.fetchone.side_effect = [None, {'id': 5}]
        with patch.object(scanner_router, 'ReadonlySong',
                          return_value=self.song(artists=('', None), publisher=None)), \
             patch.object(self.manager, '_resolve_genre_ids', return_value=[]):
            self.manager.process_file(self.conn, '/music/a.mp3')
        self.assertFalse(any('INSERT IGNORE INTO library_artists' in s for s in self.statements()))

    def test_the_genre_rows_are_replaced_rather_than_merged(self):
        self.cursor.execute.reset_mock()
        self.manager._write_genres(self.cursor, 5, [7, 8])
        statements = self.statements()
        self.assertIn('DELETE FROM library_track_genres', statements[0])
        self.assertEqual(len([s for s in statements if 'INSERT IGNORE INTO library_track_genres' in s]), 2)


class TaggerEndpointTest(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.headers = {'x-api-key': API_KEY}

    def test_the_health_endpoint_reports_whether_tagging_is_running(self):
        body = self.client.get('/api/tagger/health').json()
        self.assertEqual(body['status'], 'OK')
        self.assertFalse(body['busy'])

    def test_a_full_tagging_run_is_started_in_the_background(self):
        with patch.object(tagger_router.tagger_manager, 'run_full') as run_full:
            body = self.client.post('/api/tagger/tag/all', headers=self.headers).json()
        self.assertIn('started', body['message'])
        run_full.assert_called_once()

    def test_a_second_run_is_refused_while_one_is_in_progress(self):
        with patch.object(tagger_router.tagger_manager, '_lock', MagicMock(locked=lambda: True)):
            response = self.client.post('/api/tagger/tag/all', headers=self.headers)
        self.assertEqual(response.status_code, 409)

    def test_stopping_an_idle_tagger_reports_that_nothing_runs(self):
        body = self.client.post('/api/tagger/tag/stop', headers=self.headers).json()
        self.assertIn('No tagging operation', body['message'])

    def test_stopping_a_running_tagger_forwards_the_request(self):
        with patch.object(tagger_router.tagger_manager, '_lock', MagicMock(locked=lambda: True)), \
             patch.object(tagger_router.tagger_manager, 'stop') as stop:
            body = self.client.post('/api/tagger/tag/stop', headers=self.headers).json()
        self.assertIn('Stop request sent', body['message'])
        stop.assert_called_once()

    def test_a_single_file_can_be_tagged(self):
        with patch.object(tagger_router.tagger_manager, 'tag_single') as tag_single:
            body = self.client.post('/api/tagger/tag/file?path=/music/a.mp3', headers=self.headers).json()
        self.assertIn('/music/a.mp3', body['message'])
        tag_single.assert_called_once_with('/music/a.mp3')

    def test_a_request_without_a_key_is_unauthorized(self):
        self.assertEqual(self.client.post('/api/tagger/tag/all').status_code, 401)


class TaggerManagerTest(unittest.TestCase):

    def setUp(self):
        with patch.object(tagger_router, 'Tagger'):
            self.manager = tagger_router.TaggerManager()

    def test_a_full_run_delegates_to_the_tagger(self):
        self.manager.run_full()
        self.manager.tagger.run.assert_called_once()

    def test_a_full_run_is_skipped_while_another_one_holds_the_lock(self):
        with patch.object(self.manager, '_lock', MagicMock(locked=lambda: True)):
            self.manager.run_full()
        self.manager.tagger.run.assert_not_called()

    def test_stopping_sets_the_flag_the_tagger_polls(self):
        self.manager.stop()
        self.assertTrue(self.manager.tagger.stop_requested)

    def test_tagging_a_single_file_delegates_to_the_helper(self):
        with patch.object(tagger_router, 'TagSingleFile', return_value='tagged') as tag_single:
            self.assertEqual(self.manager.tag_single('/music/a.mp3'), 'tagged')
        tag_single.assert_called_once_with('/music/a.mp3', extra_info=None)

    def test_the_background_loop_tags_and_then_sleeps(self):
        with patch.object(tagger_router.tagger_manager, 'run_full') as run_full, \
             patch.object(tagger_router.time, 'sleep', side_effect=[None, KeyboardInterrupt]):
            with self.assertRaises(KeyboardInterrupt):
                tagger_router.run_tagger_loop(sleeptime=1)
        self.assertEqual(run_full.call_count, 2)


class NtfyListenerTest(unittest.TestCase):

    def setUp(self):
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = self.cursor
        self.conn.cursor.return_value.__exit__.return_value = False
        patcher = patch.object(ntfy_listener, 'get_db_connection', return_value=self.conn)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_message_is_stored(self):
        ntfy_listener._handle_notification(
            {'event': 'message', 'title': 'Import', 'message': 'done', 'topic': 'music'})
        self.assertEqual(self.cursor.execute.call_args.args[1], ('Import', 'done', 'music'))
        self.conn.commit.assert_called_once()

    def test_a_message_without_a_title_gets_the_default_one(self):
        ntfy_listener._handle_notification({'event': 'message'})
        self.assertEqual(self.cursor.execute.call_args.args[1], ('Music Management', '', ''))

    def test_a_non_message_event_is_ignored(self):
        ntfy_listener._handle_notification({'event': 'keepalive'})
        self.cursor.execute.assert_not_called()

    def test_a_message_arriving_without_a_database_is_dropped(self):
        with patch.object(ntfy_listener, 'get_db_connection', return_value=None):
            ntfy_listener._handle_notification({'event': 'message'})  # must not raise

    def test_an_unconfigured_listener_waits_and_retries(self):
        config = MagicMock()
        config.get.return_value = None
        with patch.object(ntfy_listener, 'ConfigStore', return_value=config), \
             patch.object(ntfy_listener.time, 'sleep', side_effect=KeyboardInterrupt), \
             patch.object(ntfy_listener, 'requests') as http, self.assertRaises(KeyboardInterrupt):
            ntfy_listener.listen_to_ntfy()
        http.get.assert_not_called()

    def test_every_streamed_line_is_handled(self):
        config = MagicMock()
        config.get.side_effect = lambda key: {'notify_url': 'https://ntfy.test/', 'notify_topic': 'music'}[key]
        response = MagicMock()
        response.__enter__.return_value = response
        response.iter_lines.return_value = [b'', b'{"event": "message"}', b'not json']
        with patch.object(ntfy_listener, 'ConfigStore', return_value=config), \
             patch.object(ntfy_listener, 'requests') as http, \
             patch.object(ntfy_listener, '_handle_notification') as handle, \
             patch.object(ntfy_listener.time, 'sleep', side_effect=KeyboardInterrupt):
            http.get.return_value = response
            # The listener loops forever; the second pass is cut short by the sleep.
            http.get.side_effect = [response, RuntimeError('stream dropped')]
            with self.assertRaises(KeyboardInterrupt):
                ntfy_listener.listen_to_ntfy()
        handle.assert_called_once_with({'event': 'message'})


if __name__ == '__main__':
    unittest.main()
