"""Coverage for the scanner/tagger routers."""

import threading
import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector')


import services.music_manager.routers.users as users_router

users_router.run_lms_db_sync = lambda: None

from fastapi.testclient import TestClient

from services.music_manager import thread_registry
from services.music_manager.main import app
from services.music_manager.routers import scanner as scanner_router
from services.music_manager.routers import tagger as tagger_router
from services.tagger.Song.BaseSong import BaseSong

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
        self.assertTrue(body['scanned'])
        scan_single.assert_called_once_with('/music/a.mp3', force=False)

    def test_a_single_file_scan_reports_when_the_scanner_did_not_take_it(self):
        with patch.object(scanner_router.scanner_manager, 'scan_single', return_value=False):
            body = self.client.post('/api/scanner/scan/file?path=/music/a.mp3', headers=self.headers).json()
        self.assertFalse(body['scanned'])

    def test_a_request_without_a_key_is_unauthorized(self):
        self.assertEqual(self.client.post('/api/scanner/scan/all').status_code, 401)

    def test_the_background_loop_scans_and_then_sleeps(self):
        with (
            patch.object(scanner_router.scanner_manager, 'run_full') as run_full,
            patch.object(thread_registry.time, 'sleep', side_effect=[None, KeyboardInterrupt]),
        ):
            with self.assertRaises(KeyboardInterrupt):
                scanner_router.run_scanner_loop(sleeptime=1)
        self.assertEqual(run_full.call_count, 2)

    def test_a_scan_that_raises_does_not_end_the_loop(self):
        """A MariaDB restart mid-scan used to kill the scanner thread for good."""
        with (
            patch.object(
                scanner_router.scanner_manager, 'run_full', side_effect=[OSError('share gone'), None]
            ) as run_full,
            patch.object(thread_registry.time, 'sleep', side_effect=[None, KeyboardInterrupt]) as sleep,
            self.assertLogs('music-manager.threads', 'ERROR') as logs,
        ):
            with self.assertRaises(KeyboardInterrupt):
                scanner_router.run_scanner_loop(sleeptime=3600)
        self.assertEqual(run_full.call_count, 2)
        self.assertIn('share gone', '\n'.join(logs.output))
        # Backed off after the failure, then the normal interval after the success.
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [10.0, 3600])


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
        self.assertEqual(self.manager.get_file_hash('/music/a.mp3'), self.manager.get_file_hash('/music/a.mp3'))
        self.assertNotEqual(self.manager.get_file_hash('/music/a.mp3'), self.manager.get_file_hash('/music/b.mp3'))

    def test_scanning_a_missing_file_reports_failure(self):
        with patch.object(scanner_router.os.path, 'exists', return_value=False):
            self.assertFalse(self.manager.scan_single('/music/gone.mp3'))

    def test_scanning_without_a_database_reports_failure(self):
        with patch.object(scanner_router, 'get_db_connection', return_value=None):
            self.assertFalse(self.manager.scan_single('/music/a.mp3'))

    def test_scanning_a_present_file_delegates_to_the_processor(self):
        with (
            patch.object(scanner_router.os.path, 'exists', return_value=True),
            patch.object(self.manager, '_process_file_safe', return_value=True) as process,
        ):
            self.assertTrue(self.manager.scan_single('/music/a.mp3'))
        process.assert_called_once()

    def test_a_single_file_scan_gives_up_while_a_full_scan_holds_the_lock(self):
        # A full scan holds the lock for hours; a single scan that waited for it kept a
        # thread-pool thread for that long, and forty of them starved every sync endpoint.
        self.manager.SINGLE_SCAN_LOCK_TIMEOUT = 0.05
        self.manager._lock.acquire()
        self.addCleanup(self.manager._lock.release)
        with (
            patch.object(scanner_router.os.path, 'exists', return_value=True),
            patch.object(self.manager, '_process_file_safe') as process,
        ):
            self.assertFalse(self.manager.scan_single('/music/a.mp3'))
        process.assert_not_called()

    def test_a_single_file_scan_releases_the_lock_after_a_failure(self):
        with (
            patch.object(scanner_router.os.path, 'exists', return_value=True),
            patch.object(self.manager, '_process_file_safe', side_effect=RuntimeError('boom')),
        ):
            with self.assertRaises(RuntimeError):
                self.manager.scan_single('/music/a.mp3')
        self.assertFalse(self.manager._lock.locked())

    def test_a_full_run_over_a_missing_music_folder_does_nothing(self):
        self.manager.music_path = None
        with patch.object(self.manager, '_scan_recursive') as scan:
            self.manager.run_full()
        scan.assert_not_called()

    def test_a_full_run_is_skipped_while_another_one_holds_the_lock(self):
        with (
            patch.object(scanner_router.os.path, 'exists', return_value=True),
            patch.object(self.manager, '_lock', MagicMock(locked=lambda: True)),
            patch.object(self.manager, '_scan_recursive') as scan,
        ):
            self.manager.run_full()
        scan.assert_not_called()

    def test_a_single_file_scan_loads_the_curation_rules_first(self):
        with (
            patch.object(self.manager.genre_helper, 'reload') as reload_rules,
            patch.object(scanner_router, 'get_db_connection', return_value=None),
        ):
            self.manager.scan_single('/music/EPs/a.flac')
        reload_rules.assert_called_once()

    def test_a_single_file_scan_that_cannot_get_the_lock_does_not_load_the_rules(self):
        # The reload is a query. It used to run before the lock was tried, so while a full
        # scan held the lock every single scan paid for rules it then never used.
        self.manager.SINGLE_SCAN_LOCK_TIMEOUT = 0.01
        self.manager._lock.acquire()
        self.addCleanup(self.manager._lock.release)
        with patch.object(self.manager.genre_helper, 'reload') as reload_rules:
            self.assertFalse(self.manager.scan_single('/music/a.mp3'))
        reload_rules.assert_not_called()

    def test_a_single_file_scan_loads_the_rules_while_holding_the_lock(self):
        held = []
        with (
            patch.object(
                self.manager.genre_helper, 'reload', side_effect=lambda: held.append(self.manager._lock.locked())
            ),
            patch.object(scanner_router, 'get_db_connection', return_value=None),
        ):
            self.manager.scan_single('/music/a.mp3')
        self.assertEqual(held, [True])

    def test_a_full_run_reloads_the_curation_rules_first(self):
        with (
            patch.object(scanner_router.os.path, 'exists', return_value=True),
            patch.object(self.manager.genre_helper, 'reload') as reload_rules,
            patch.object(self.manager, '_scan_recursive', return_value=0),
        ):
            self.manager.run_full()
        reload_rules.assert_called_once()

    def test_a_full_run_without_a_database_stops_early(self):
        with (
            patch.object(scanner_router.os.path, 'exists', return_value=True),
            patch.object(self.manager.genre_helper, 'reload'),
            patch.object(scanner_router, 'get_db_connection', return_value=None),
            patch.object(self.manager, '_scan_recursive') as scan,
        ):
            self.manager.run_full()
        scan.assert_not_called()

    def test_hidden_files_are_not_scanned(self):
        with (
            patch.object(scanner_router.os, 'walk', return_value=[('/music', [], ['.DS_Store', 'a.mp3'])]),
            patch.object(self.manager, '_process_file_safe', return_value=True) as process,
        ):
            self.assertEqual(self.manager._scan_recursive(self.conn, False), 1)
        process.assert_called_once_with(self.conn, '/music/a.mp3', False)

    def test_the_quarantine_is_not_walked_into(self):
        """What the pipeline parked is exactly what must not come back as library tracks.

        With no quarantine folder configured it lands beside the music root as
        `.quarantine`, and the importer moves duplicate releases and unreadable files
        there. Indexing them would undo the decision that put them there.
        """
        dirs = ['.quarantine', '@eaDir', 'EPs']
        with (
            patch.object(scanner_router.os, 'walk', return_value=[('/music', dirs, [])]),
            patch.object(self.manager, '_process_file_safe', return_value=True),
        ):
            self.manager._scan_recursive(self.conn, False)
        self.assertEqual(['EPs'], dirs)

    def test_an_unsupported_extension_is_skipped_quietly(self):
        with patch.object(
            self.manager, 'process_file', side_effect=scanner_router.ExtensionNotSupportedException('.txt')
        ):
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
        song = MagicMock(spec_set=BaseSong)
        song.rules_genres.return_value = genres
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

    def song(self, artists=('Angerfist',), publisher='Masters of Hardcore', display_artist=None):
        song = MagicMock(spec_set=BaseSong)
        song.library_artists.return_value = list(artists)
        song.publisher.return_value = publisher
        song.title.return_value = 'Raise Your Fist'
        song.length.return_value = 300
        song.rules_genres.return_value = []
        song.original_artist.return_value = display_artist
        return song

    def statements(self):
        return [call.args[0] for call in self.cursor.execute.call_args_list]

    def test_an_unchanged_file_is_skipped(self):
        self.cursor.fetchone.return_value = {'id': 1, 'file_mtime': 100.0, 'file_size': 1024}
        self.assertFalse(self.manager.process_file(self.conn, '/music/a.mp3'))

    def test_force_reprocesses_an_unchanged_file(self):
        self.cursor.fetchone.side_effect = [
            {'id': 1, 'file_mtime': 100.0, 'file_size': 1024},
            {'id': 3},
            {'id': 4},
            {'id': 5},
        ]
        with (
            patch.object(scanner_router, 'ReadonlySong', return_value=self.song()),
            patch.object(self.manager, '_resolve_genre_ids', return_value=[]),
        ):
            self.assertTrue(self.manager.process_file(self.conn, '/music/a.mp3', force=True))

    def test_a_file_that_cannot_be_read_is_skipped(self):
        self.cursor.fetchone.return_value = None
        with patch.object(scanner_router, 'ReadonlySong', side_effect=RuntimeError('bad tags')):
            self.assertFalse(self.manager.process_file(self.conn, '/music/a.mp3'))

    def test_a_new_file_creates_its_artist_label_track_and_media_row(self):
        self.cursor.fetchone.side_effect = [None, {'id': 3}, {'id': 4}, {'id': 5}]
        with (
            patch.object(scanner_router, 'ReadonlySong', return_value=self.song()),
            patch.object(self.manager, '_resolve_genre_ids', return_value=[9]),
        ):
            self.assertTrue(self.manager.process_file(self.conn, '/music/a.mp3'))
        statements = self.statements()
        self.assertTrue(any('INSERT IGNORE INTO library_artists' in s for s in statements))
        self.assertTrue(any('INSERT IGNORE INTO library_labels' in s for s in statements))
        self.assertTrue(any('INSERT INTO library_tracks' in s for s in statements))
        self.assertTrue(any('INSERT IGNORE INTO library_track_labels' in s for s in statements))
        self.assertTrue(any('INSERT INTO library_media_files' in s for s in statements))

    def test_a_captured_display_artist_is_written_to_the_track_row(self):
        self.cursor.fetchone.side_effect = [None, {'id': 3}, {'id': 4}, {'id': 5}]
        with (
            patch.object(scanner_router, 'ReadonlySong', return_value=self.song(display_artist='Henk feat Kees')),
            patch.object(self.manager, '_resolve_genre_ids', return_value=[]),
        ):
            self.manager.process_file(self.conn, '/music/a.mp3')
        sql, params = next(
            (call.args[0], call.args[1])
            for call in self.cursor.execute.call_args_list
            if 'INSERT INTO library_tracks' in call.args[0]
        )
        self.assertIn('display_artist', sql)
        self.assertIn('Henk feat Kees', params)

    def test_a_file_with_nothing_captured_writes_no_display_artist(self):
        self.cursor.fetchone.side_effect = [None, {'id': 3}, {'id': 4}, {'id': 5}]
        with (
            patch.object(scanner_router, 'ReadonlySong', return_value=self.song()),
            patch.object(self.manager, '_resolve_genre_ids', return_value=[]),
        ):
            self.manager.process_file(self.conn, '/music/a.mp3')
        _sql, params = next(
            (call.args[0], call.args[1])
            for call in self.cursor.execute.call_args_list
            if 'INSERT INTO library_tracks' in call.args[0]
        )
        self.assertIsNone(params[4])

    def test_a_null_display_artist_never_overwrites_one_a_sibling_copy_already_captured(self):
        """Two media files can resolve to the same track_uid. Scanning the copy that has not
        been retagged yet must not erase a display_artist a previously-scanned sibling copy
        already wrote -- COALESCE in the UPDATE clause, not a bare overwrite."""
        self.cursor.fetchone.side_effect = [None, {'id': 3}, {'id': 4}, {'id': 5}]
        with (
            patch.object(scanner_router, 'ReadonlySong', return_value=self.song()),
            patch.object(self.manager, '_resolve_genre_ids', return_value=[]),
        ):
            self.manager.process_file(self.conn, '/music/a.mp3')
        sql = next(
            call.args[0] for call in self.cursor.execute.call_args_list if 'INSERT INTO library_tracks' in call.args[0]
        )
        self.assertIn('COALESCE', sql)

    def test_the_first_artist_becomes_the_primary_and_the_rest_featuring(self):
        self.cursor.fetchone.side_effect = [None, {'id': 3}, {'id': 4}, {'id': 5}, {'id': 6}]
        with (
            patch.object(
                scanner_router,
                'ReadonlySong',
                return_value=self.song(artists=('Angerfist', 'Outsiders'), publisher=None),
            ),
            patch.object(self.manager, '_resolve_genre_ids', return_value=[]),
        ):
            self.manager.process_file(self.conn, '/music/a.mp3')
        roles = [
            call.args[1][2]
            for call in self.cursor.execute.call_args_list
            if 'library_track_artists' in call.args[0] and 'DELETE' not in call.args[0]
        ]
        self.assertEqual(roles, ['primary', 'featuring'])

    def test_a_file_without_a_publisher_gets_no_label_row(self):
        self.cursor.fetchone.side_effect = [None, {'id': 3}, {'id': 5}]
        with (
            patch.object(scanner_router, 'ReadonlySong', return_value=self.song(publisher=None)),
            patch.object(self.manager, '_resolve_genre_ids', return_value=[]),
        ):
            self.manager.process_file(self.conn, '/music/a.mp3')
        self.assertFalse(any('INSERT IGNORE INTO library_track_labels' in s for s in self.statements()))
        # The link a previous publisher left behind is cleared rather than kept for good.
        self.assertTrue(any('DELETE FROM library_track_labels' in s for s in self.statements()))

    def test_empty_artist_names_are_ignored(self):
        self.cursor.fetchone.side_effect = [None, {'id': 5}]
        with (
            patch.object(scanner_router, 'ReadonlySong', return_value=self.song(artists=('', None), publisher=None)),
            patch.object(self.manager, '_resolve_genre_ids', return_value=[]),
        ):
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
        # "All" means the folders too, whatever the schedule says.
        run_full.assert_called_once_with(True)

    def test_a_second_run_is_refused_while_one_is_in_progress(self):
        with patch.object(tagger_router.tagger_manager, '_lock', MagicMock(locked=lambda: True)):
            response = self.client.post('/api/tagger/tag/all', headers=self.headers)
        self.assertEqual(response.status_code, 409)

    def test_stopping_an_idle_tagger_reports_that_nothing_runs(self):
        body = self.client.post('/api/tagger/tag/stop', headers=self.headers).json()
        self.assertIn('No tagging operation', body['message'])

    def test_stopping_a_running_tagger_forwards_the_request(self):
        with (
            patch.object(tagger_router.tagger_manager, '_lock', MagicMock(locked=lambda: True)),
            patch.object(tagger_router.tagger_manager, 'stop') as stop,
        ):
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
        self.schedule = MagicMock()
        self.schedule.due.return_value = False
        patcher = patch.object(tagger_router, 'WalkSchedule', return_value=self.schedule)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_full_run_delegates_to_the_tagger(self):
        self.manager.run_full()
        self.manager.tagger.run.assert_called_once()

    def test_the_loops_round_walks_only_when_the_schedule_says_so(self):
        self.manager.run_full()
        self.manager.tagger.run.assert_called_once_with(walk=False)
        self.schedule.record.assert_not_called()
        self.manager.tagger.run.reset_mock()
        self.schedule.due.return_value = True
        self.manager.tagger.stop_requested = False
        self.manager.run_full()
        self.manager.tagger.run.assert_called_once_with(walk=True)
        self.schedule.record.assert_called_once()

    def test_an_interrupted_walk_is_not_recorded_as_done(self):
        self.schedule.due.return_value = True
        self.manager.tagger.stop_requested = True
        self.manager.run_full()
        self.schedule.record.assert_not_called()

    def test_the_caller_can_insist_either_way(self):
        self.manager.run_full(walk=True)
        self.manager.tagger.run.assert_called_once_with(walk=True)
        self.schedule.due.assert_not_called()
        self.manager.tagger.run.reset_mock()
        self.schedule.due.return_value = True
        self.manager.run_full(walk=False)
        self.manager.tagger.run.assert_called_once_with(walk=False)

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
        with (
            patch.object(tagger_router.tagger_manager, 'run_full') as run_full,
            patch.object(tagger_router, 'deep_run_tick'),
            patch.object(tagger_router.time, 'sleep', side_effect=[None, KeyboardInterrupt]),
        ):
            with self.assertRaises(KeyboardInterrupt):
                tagger_router.run_tagger_loop(sleeptime=1)
        self.assertEqual(run_full.call_count, 2)

    def test_every_round_first_queues_a_slice_of_the_deep_run(self):
        with (
            patch.object(tagger_router.tagger_manager, 'run_full'),
            patch.object(tagger_router, 'deep_run_tick') as deep_run,
            patch.object(tagger_router.time, 'sleep', side_effect=[None, KeyboardInterrupt]),
        ):
            with self.assertRaises(KeyboardInterrupt):
                tagger_router.run_tagger_loop(sleeptime=1)
        self.assertEqual(deep_run.call_count, 2)

    def test_a_broken_deep_run_never_stops_the_tagging_round(self):
        with (
            patch.object(tagger_router.tagger_manager, 'run_full') as run_full,
            patch.object(tagger_router, 'deep_run_tick', side_effect=RuntimeError('database gone')),
            patch.object(tagger_router.time, 'sleep', side_effect=KeyboardInterrupt),
        ):
            with self.assertRaises(KeyboardInterrupt):
                tagger_router.run_tagger_loop(sleeptime=1)
        run_full.assert_called_once()

    def test_a_round_that_raises_does_not_end_the_loop(self):
        """`run_full` raising (database gone, CIFS hiccup) is logged and the next round runs."""
        with (
            patch.object(
                tagger_router.tagger_manager, 'run_full', side_effect=[RuntimeError('database gone'), None]
            ) as run_full,
            patch.object(tagger_router, 'deep_run_tick'),
            patch.object(thread_registry.time, 'sleep', side_effect=[None, KeyboardInterrupt]),
            self.assertLogs('music-manager.threads', 'ERROR') as logs,
        ):
            with self.assertRaises(KeyboardInterrupt):
                tagger_router.run_tagger_loop(sleeptime=300)
        self.assertEqual(run_full.call_count, 2)
        self.assertIn('database gone', '\n'.join(logs.output))


if __name__ == '__main__':
    unittest.main()


class RetagEndpointsTest(unittest.TestCase):
    """The pending count is the brake: you see what you are about to do first."""

    def setUp(self):
        self.client = TestClient(app)
        self.headers = {'x-api-key': API_KEY}

    def test_the_pending_summary_is_returned(self):
        with patch.object(tagger_router, 'ProcessedFilesHelper') as helper:
            helper.return_value.pending_summary.return_value = {
                'total': 142,
                'by_reason': [{'reason': 'genre_decision', 'count': 142}],
            }
            response = self.client.get('/api/tagger/retag/pending', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['total'], 142)

    def test_starting_a_retag_schedules_the_run_in_the_background(self):
        with patch.object(tagger_router, 'run_retag') as run_retag:
            response = self.client.post('/api/tagger/retag/run', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        run_retag.assert_called_once()

    def test_a_retag_is_refused_while_the_tagger_is_busy(self):
        with patch.object(tagger_router.tagger_manager, '_lock', MagicMock(locked=lambda: True)):
            response = self.client.post('/api/tagger/retag/run', headers=self.headers)
        self.assertEqual(response.status_code, 409)

    def test_the_pending_summary_carries_the_tagger_state(self):
        # The page polls this one endpoint, so the state rides along with the count.
        with patch.object(tagger_router, 'ProcessedFilesHelper') as helper:
            helper.return_value.pending_summary.return_value = {'total': 0, 'by_reason': []}
            idle = self.client.get('/api/tagger/retag/pending', headers=self.headers).json()
            with (
                patch.object(tagger_router.tagger_manager, '_lock', MagicMock(locked=lambda: True)),
                patch.object(tagger_router.tagger_manager.tagger, 'stop_requested', True),
            ):
                halting = self.client.get('/api/tagger/retag/pending', headers=self.headers).json()
        self.assertEqual((idle['busy'], idle['stopping']), (False, False))
        self.assertEqual((halting['busy'], halting['stopping']), (True, True))

    def test_a_restart_is_accepted_while_the_tagger_is_busy(self):
        # Being busy is the whole reason to ask for one, so no 409 here.
        with (
            patch.object(tagger_router.tagger_manager, '_lock', MagicMock(locked=lambda: True)),
            patch.object(tagger_router, 'restart_retag') as restart_retag,
        ):
            response = self.client.post('/api/tagger/retag/restart', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        restart_retag.assert_called_once()

    def test_a_restart_cuts_the_round_short_and_starts_over(self):
        manager = tagger_router.TaggerManager.__new__(tagger_router.TaggerManager)
        manager.tagger = MagicMock(stop_requested=False)
        manager._lock = threading.Lock()
        rounds = []
        schedule = patch.object(tagger_router, 'WalkSchedule', return_value=MagicMock(**{'due.return_value': False}))
        schedule.start()
        self.addCleanup(schedule.stop)
        started = threading.Event()

        def a_round_that_waits_for_the_stop(**_):
            rounds.append('first')
            started.set()
            while not manager.tagger.stop_requested:
                pass
            rounds.append('first stopped')

        def a_fresh_round(**_):
            rounds.append('second')

        manager.tagger.run.side_effect = a_round_that_waits_for_the_stop
        first = threading.Thread(target=manager.run_full)
        first.start()
        # Wait for the round itself, not for the lock: the lock is taken a moment before
        # run() is entered, and swapping the side effect in that moment fakes a restart.
        self.assertTrue(started.wait(timeout=5))

        manager.tagger.run.side_effect = a_fresh_round
        manager.restart()
        first.join(timeout=5)

        self.assertEqual(rounds, ['first', 'first stopped', 'second'])

    def test_a_restart_gives_up_when_the_round_never_lets_go(self):
        manager = tagger_router.TaggerManager.__new__(tagger_router.TaggerManager)
        manager.tagger = MagicMock(stop_requested=False)
        manager._lock = MagicMock(locked=lambda: True)
        with patch.object(tagger_router.TaggerManager, 'RESTART_WAIT_SECONDS', 0):
            manager.restart()
        manager.tagger.run.assert_not_called()

    def test_a_restart_retag_restarts_and_then_indexes(self):
        with (
            patch.object(tagger_router.tagger_manager, 'restart') as restart,
            patch.object(scanner_router.scanner_manager, 'run_full') as scan_full,
        ):
            tagger_router.restart_retag()
        restart.assert_called_once()
        scan_full.assert_called_once()

    def test_a_retag_run_tags_and_then_indexes(self):
        # No dedicated execution path: Tagger.run skips unmarked files by itself, so a
        # full run is the retag.
        with (
            patch.object(tagger_router.tagger_manager, 'run_full') as run_full,
            patch.object(scanner_router.scanner_manager, 'run_full') as scan_full,
        ):
            tagger_router.run_retag()
        # The queue, not the folders: a retag is what a decision queued.
        run_full.assert_called_once_with(walk=False)
        scan_full.assert_called_once()


class LmsTriggerTest(unittest.TestCase):
    def test_tagging_a_single_file_tells_lms(self):
        with patch.object(tagger_router, 'lms_scan_trigger') as trigger, patch.object(tagger_router, 'TagSingleFile'):
            tagger_router.tagger_manager.tag_single('/music/a.mp3')
        trigger.trigger.assert_called_once()

    def test_a_finished_scan_tells_lms_once(self):
        manager = scanner_router.scanner_manager
        with (
            patch.object(scanner_router, 'lms_scan_trigger') as trigger,
            patch.object(manager, '_scan_recursive', return_value=0),
            patch.object(scanner_router, 'get_db_connection', return_value=MagicMock()),
            patch.object(manager, 'music_path', '/'),
            patch.object(manager, 'genre_helper', MagicMock()),
        ):
            manager.run_full()
        trigger.trigger.assert_called_once()
