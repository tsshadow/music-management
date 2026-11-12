"""The scanner's side of bug report 042: a file moving to a new track row, and stale links.

`process_file` repoints a retagged file at its new track and hands the row it left to
track_relink inside one transaction; `_write_links` recomputes label and channel links from every
file of a track instead of only ever adding. The relink endpoint is admin only.
"""

import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector')


import services.music_manager.routers.users as users_router

users_router.run_lms_db_sync = lambda only_sources=None: None

from fastapi.testclient import TestClient

from services.music_manager import orphan_purge, track_relink
from services.music_manager.main import app
from services.music_manager.routers import scanner as scanner_router
from services.music_manager.tests.scripted_cursor import ScriptedCursor
from services.tagger.Song.BaseSong import BaseSong

API_KEY = users_router.API_KEY


def a_song(publisher=None, title='Raise Your Fist'):
    """A song stub with one artist and no genres."""
    song = MagicMock(spec_set=BaseSong)
    song.library_artists.return_value = ['Angerfist']
    song.publisher.return_value = publisher
    song.title.return_value = title
    song.remixers.return_value = []
    song.length.return_value = 300
    song.rules_genres.return_value = []
    song.original_artist.return_value = None
    return song


class ProcessFileMoveTest(unittest.TestCase):
    """A file whose media row pointed at track 2 and whose tags now hash to track 5."""

    def setUp(self):
        self.manager = scanner_router.ScannerManager()
        self.manager.music_path = '/music'
        self.manager.genre_helper = MagicMock()
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = self.cursor
        self.conn.cursor.return_value.__exit__.return_value = False
        for p in (
            patch.object(scanner_router.os.path, 'getmtime', return_value=100.0),
            patch.object(scanner_router.os.path, 'getsize', return_value=1024),
            patch.object(scanner_router, 'ReadonlySong', return_value=a_song()),
            patch.object(self.manager, '_resolve_genre_ids', return_value=[]),
        ):
            p.start()
            self.addCleanup(p.stop)

    def run_with_previous_track(self, previous):
        self.cursor.fetchone.side_effect = [
            {'id': 1, 'file_mtime': 1.0, 'file_size': 1, 'track_id': previous},
            {'id': 3},  # artist
            {'id': 5},  # track
        ]
        return self.manager.process_file(self.conn, '/music/a.mp3')

    def test_a_file_moving_to_a_new_track_relinks_the_old_one_in_a_transaction(self):
        with patch.object(self.manager, '_settle_previous_track') as settle:
            self.assertTrue(self.run_with_previous_track(2))
        settle.assert_called_once_with(self.cursor, 2, 5, self.manager.get_file_hash('/music/a.mp3'))
        self.conn.begin.assert_called_once()
        self.conn.commit.assert_called_once()
        self.conn.rollback.assert_not_called()

    def test_a_remixer_gets_a_remixer_row_next_to_its_featuring_row(self):
        song = a_song()
        song.library_artists.return_value = ['Angerfist', 'Miss K8']
        song.remixers.return_value = ['Miss K8']
        self.cursor.fetchone.side_effect = [
            {'id': 1, 'file_mtime': 1.0, 'file_size': 1, 'track_id': 5},
            {'id': 3},  # Angerfist
            {'id': 4},  # Miss K8
            {'id': 4},  # Miss K8 again, as remixer
            {'id': 5},  # track
        ]
        with (
            patch.object(scanner_router, 'ReadonlySong', return_value=song),
            patch.object(self.manager, '_settle_previous_track'),
        ):
            self.manager.process_file(self.conn, '/music/a.mp3')
        credits = [
            call.args[1]
            for call in self.cursor.execute.call_args_list
            if 'INSERT IGNORE INTO library_track_artists' in call.args[0]
        ]
        self.assertEqual(credits, [(5, 3, 'primary', 0), (5, 4, 'featuring', 1), (5, 4, 'remixer', 0)])

    def test_a_failed_relink_rolls_the_move_back(self):
        with (
            patch.object(self.manager, '_settle_previous_track', side_effect=RuntimeError('deadlock')),
            self.assertRaises(RuntimeError),
        ):
            self.run_with_previous_track(2)
        self.conn.rollback.assert_called_once()
        self.conn.commit.assert_not_called()

    def test_a_file_that_stays_on_its_track_still_rewrites_its_links_in_one_transaction(self):
        with patch.object(self.manager, '_settle_previous_track') as settle:
            self.run_with_previous_track(5)
        settle.assert_not_called()
        self.conn.begin.assert_called_once()
        self.conn.commit.assert_called_once()
        self.conn.rollback.assert_not_called()

    def test_a_file_seen_for_the_first_time_rewrites_its_links_in_one_transaction(self):
        with patch.object(self.manager, '_settle_previous_track') as settle:
            self.run_with_previous_track(None)
        settle.assert_not_called()
        self.conn.begin.assert_called_once()
        self.conn.commit.assert_called_once()

    def test_the_link_deletes_run_inside_the_transaction(self):
        # Delete-then-insert: the DELETE of the old artist links must come after BEGIN
        # and the last write before COMMIT, or a crash in between strips the track.
        order = []
        self.conn.begin.side_effect = lambda: order.append('begin')
        self.conn.commit.side_effect = lambda: order.append('commit')
        self.cursor.execute.side_effect = lambda sql, *_a: order.append(sql.split()[0])
        self.run_with_previous_track(5)
        self.assertLess(order.index('begin'), order.index('DELETE'))
        self.assertEqual(order[-1], 'commit')

    def test_a_failing_link_write_rolls_back_the_deleted_links(self):
        with (
            patch.object(self.manager, '_write_links', side_effect=RuntimeError('lock wait timeout')),
            self.assertRaises(RuntimeError),
        ):
            self.run_with_previous_track(5)
        self.conn.begin.assert_called_once()
        self.conn.rollback.assert_called_once()
        self.conn.commit.assert_not_called()


class SettlePreviousTrackTest(unittest.TestCase):
    def setUp(self):
        self.manager = scanner_router.ScannerManager()
        self.manager.music_path = '/music'

    def test_a_track_with_files_left_keeps_its_row_but_has_its_links_refreshed(self):
        cursor = MagicMock()
        with (
            patch.object(scanner_router, 'track_has_media_file', return_value=True),
            patch.object(scanner_router, 'relink_track') as relink,
            patch.object(self.manager, '_write_links') as write_links,
        ):
            self.assertIsNone(self.manager._settle_previous_track(cursor, 2, 5, 'hash'))
        relink.assert_not_called()
        write_links.assert_called_once_with(cursor, 2, 'hash')

    def test_a_track_left_without_files_is_relinked(self):
        cursor = MagicMock()
        counts = {'ratings_moved': 1, 'ratings_merged': 0, 'listens_moved': 0, 'listens_dropped': 0}
        with (
            patch.object(scanner_router, 'track_has_media_file', return_value=False),
            patch.object(scanner_router, 'relink_track', return_value=counts) as relink,
        ):
            self.assertEqual(self.manager._settle_previous_track(cursor, 2, 5, 'hash'), counts)
        relink.assert_called_once_with(cursor, 2, 5)


class WriteLinksTest(unittest.TestCase):
    def setUp(self):
        self.manager = scanner_router.ScannerManager()
        self.manager.music_path = '/music'

    def test_a_single_file_track_has_its_label_and_channel_replaced(self):
        cursor = ScriptedCursor()
        self.manager._write_links(cursor, 5, 'hash', label_id=8, channel_id=None)

        statements = [sql for sql, _p in cursor.executed]
        self.assertIn('DELETE FROM library_track_labels WHERE track_id = %s', statements)
        self.assertIn('DELETE FROM library_track_channels WHERE track_id = %s', statements)
        self.assertEqual(cursor.statements_matching('INSERT IGNORE INTO library_track_labels')[0][1], (5, 8))
        self.assertEqual(cursor.statements_matching('INSERT IGNORE INTO library_track_channels'), [])

    def test_a_sibling_file_keeps_its_own_label(self):
        cursor = ScriptedCursor(
            [
                ('SELECT file_path FROM library_media_files', None, [{'file_path': '/music/EPs/b.flac'}]),
                ('SELECT id FROM library_labels', None, {'id': 9}),
            ]
        )
        with (
            patch.object(scanner_router.os.path, 'exists', return_value=True),
            patch.object(scanner_router, 'ReadonlySong', return_value=a_song(publisher='Masters of Hardcore')),
        ):
            self.manager._write_links(cursor, 5, 'hash', label_id=8)
        inserted = sorted(p for _sql, p in cursor.statements_matching('INSERT IGNORE INTO library_track_labels'))
        self.assertEqual(inserted, [(5, 8), (5, 9)])

    def test_a_sibling_gone_from_disk_supports_nothing(self):
        cursor = ScriptedCursor(
            [('SELECT file_path FROM library_media_files', None, [{'file_path': '/music/Soundcloud/Gone/b.mp3'}])]
        )
        with patch.object(scanner_router.os.path, 'exists', return_value=False):
            self.manager._write_links(cursor, 5, 'hash', label_id=None)
        self.assertTrue(cursor.statements_matching('DELETE FROM library_track_labels'))
        self.assertEqual(cursor.statements_matching('INSERT IGNORE'), [])

    def test_an_unreadable_sibling_means_no_label_is_removed(self):
        cursor = ScriptedCursor([('SELECT file_path FROM library_media_files', None, [{'file_path': '/music/b.mp3'}])])
        with (
            patch.object(scanner_router.os.path, 'exists', return_value=True),
            patch.object(scanner_router, 'ReadonlySong', side_effect=RuntimeError('bad tags')),
        ):
            self.manager._write_links(cursor, 5, 'hash', label_id=8)
        self.assertEqual(cursor.statements_matching('DELETE FROM library_track_labels'), [])
        self.assertEqual(cursor.statements_matching('INSERT IGNORE INTO library_track_labels')[0][1], (5, 8))


class RelinkEndpointTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        scanner_router.relink_state.update({'running': False, 'last': None, 'progress': None})
        scanner_router.purge_state.update({'running': False, 'last': None, 'progress': None})
        self.addCleanup(scanner_router.relink_state.update, {'running': False, 'last': None, 'progress': None})
        self.addCleanup(scanner_router.purge_state.update, {'running': False, 'last': None, 'progress': None})

    def test_without_a_key_the_relink_is_unauthorized(self):
        self.assertEqual(self.client.post('/api/scanner/relink-orphans').status_code, 401)

    def test_a_user_without_the_admin_role_is_refused(self):
        user = {'type': 'user', 'user': {'id': 4, 'username': 'anna', 'role_name': 'user', 'permissions': []}}
        with (
            patch.object(users_router, 'verify_api_key', return_value=user),
            patch.object(scanner_router, 'run_orphan_relink') as run,
        ):
            post = self.client.post('/api/scanner/relink-orphans', headers={'x-api-key': 'anna-key'})
            get = self.client.get('/api/scanner/relink-orphans', headers={'x-api-key': 'anna-key'})
        self.assertEqual(post.status_code, 403)
        self.assertEqual(get.status_code, 403)
        run.assert_not_called()

    def test_an_admin_starts_it_in_the_background(self):
        with patch.object(scanner_router, 'run_orphan_relink') as run:
            response = self.client.post('/api/scanner/relink-orphans', headers={'x-api-key': API_KEY})
        self.assertEqual(response.status_code, 200)
        self.assertIn('started', response.json()['message'])
        run.assert_called_once_with(False)

    def test_dry_run_is_passed_to_the_background_task(self):
        with patch.object(scanner_router, 'run_orphan_relink') as run:
            response = self.client.post('/api/scanner/relink-orphans?dry_run=1', headers={'x-api-key': API_KEY})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['dry_run'])
        run.assert_called_once_with(True)

    def test_a_relink_is_refused_while_a_purge_runs(self):
        scanner_router.purge_state['running'] = True
        with patch.object(scanner_router, 'run_orphan_relink') as run:
            response = self.client.post('/api/scanner/relink-orphans', headers={'x-api-key': API_KEY})
        self.assertEqual(response.status_code, 409)
        run.assert_not_called()

    def test_an_admin_starts_a_purge_dry_run(self):
        with patch.object(scanner_router, 'run_orphan_purge') as run:
            response = self.client.post('/api/scanner/purge-orphans?dry_run=true', headers={'x-api-key': API_KEY})
        self.assertEqual(response.status_code, 200)
        run.assert_called_once_with(True)

    def test_a_purge_is_refused_while_a_relink_runs(self):
        scanner_router.relink_state['running'] = True
        with patch.object(scanner_router, 'run_orphan_purge') as run:
            response = self.client.post('/api/scanner/purge-orphans', headers={'x-api-key': API_KEY})
        self.assertEqual(response.status_code, 409)
        run.assert_not_called()

    def test_the_purge_is_admin_only(self):
        user = {'type': 'user', 'user': {'id': 4, 'username': 'anna', 'role_name': 'user', 'permissions': []}}
        with (
            patch.object(users_router, 'verify_api_key', return_value=user),
            patch.object(scanner_router, 'run_orphan_purge') as run,
        ):
            post = self.client.post('/api/scanner/purge-orphans', headers={'x-api-key': 'anna-key'})
            get = self.client.get('/api/scanner/purge-orphans', headers={'x-api-key': 'anna-key'})
        self.assertEqual((post.status_code, get.status_code), (403, 403))
        run.assert_not_called()

    def test_the_purge_status_reports_the_last_totals(self):
        scanner_router.purge_state['last'] = {'purged': 3}
        body = self.client.get('/api/scanner/purge-orphans', headers={'x-api-key': API_KEY}).json()
        self.assertEqual(body, {'running': False, 'progress': None, 'last': {'purged': 3}})

    def test_a_second_relink_is_refused_while_one_runs(self):
        scanner_router.relink_state['running'] = True
        with patch.object(scanner_router, 'run_orphan_relink') as run:
            response = self.client.post('/api/scanner/relink-orphans', headers={'x-api-key': API_KEY})
        self.assertEqual(response.status_code, 409)
        run.assert_not_called()

    def test_the_status_reports_the_last_totals(self):
        scanner_router.relink_state['last'] = {'relinked': 3}
        body = self.client.get('/api/scanner/relink-orphans', headers={'x-api-key': API_KEY}).json()
        self.assertEqual(
            body,
            {
                'running': False,
                'keys': ['metadata', 'file_name'],
                'dry_run_supported': True,
                'progress': None,
                'last': {'relinked': 3},
            },
        )


class RunOrphanRelinkTest(unittest.TestCase):
    def setUp(self):
        scanner_router.relink_state.update({'running': True, 'last': None, 'progress': None})
        self.addCleanup(scanner_router.relink_state.update, {'running': False, 'last': None, 'progress': None})

    def test_the_totals_are_recorded_as_an_info_event(self):
        totals = track_relink.empty_relink_totals() | {
            'orphans': 4,
            'relinked': 3,
            'relinked_metadata': 1,
            'relinked_file_name': 2,
            'ambiguous_file_name': 1,
            'unmatched': 1,
            'failed': 0,
            'ratings_moved': 2,
            'ratings_merged': 1,
            'listens_moved': 7,
            'listens_dropped': 0,
            'tracks_deleted': 3,
        }
        conn = MagicMock()
        with (
            patch.object(scanner_router, 'get_db_connection', return_value=conn),
            patch.object(scanner_router, 'relink_orphaned_tracks', return_value=totals),
            patch('services.common.Helpers.EventService.event_service') as events,
        ):
            self.assertEqual(scanner_router.run_orphan_relink(), totals)
        conn.close.assert_called_once()
        kwargs = events.emit.call_args.kwargs
        self.assertEqual(kwargs['level'], 'INFO')
        self.assertEqual(kwargs['context'], totals)
        self.assertIn('3 of 4', kwargs['message'])
        self.assertIn('1 on metadata, 2 on file name', kwargs['message'])
        self.assertIn('1 of them named like several files', kwargs['message'])
        self.assertEqual(scanner_router.relink_state, {'running': False, 'last': totals, 'progress': None})

    def test_a_dry_run_is_kept_for_get_but_writes_no_event(self):
        totals = track_relink.empty_relink_totals(dry_run=True) | {'orphans': 2, 'relinked': 1}
        with (
            patch.object(scanner_router, 'get_db_connection', return_value=MagicMock()),
            patch.object(scanner_router, 'relink_orphaned_tracks', return_value=totals) as relink,
            patch('services.common.Helpers.EventService.event_service') as events,
        ):
            scanner_router.run_orphan_relink(True)
        self.assertTrue(relink.call_args.kwargs['dry_run'])
        events.emit.assert_not_called()
        self.assertEqual(scanner_router.relink_state['last'], totals)

    def test_a_running_scan_skips_the_relink(self):
        lock = MagicMock()
        lock.acquire.return_value = False
        with (
            patch.object(scanner_router.scanner_manager, '_lock', lock),
            patch.object(scanner_router, 'relink_orphaned_tracks') as relink,
        ):
            self.assertIsNone(scanner_router.run_orphan_relink())
        relink.assert_not_called()
        self.assertFalse(scanner_router.relink_state['running'])


class RunOrphanPurgeTest(unittest.TestCase):
    def setUp(self):
        scanner_router.purge_state.update({'running': True, 'last': None, 'progress': None})
        self.addCleanup(scanner_router.purge_state.update, {'running': False, 'last': None, 'progress': None})

    def test_the_totals_are_an_event_without_the_kept_list(self):
        totals = orphan_purge.empty_purge_totals() | {
            'orphans': 5,
            'purged': 3,
            'kept': 2,
            'kept_listens': 2,
            'kept_list': [{'id': 1, 'title': 'x', 'listens': 1, 'ratings': 0, 'pinned': 0, 'reviewed_labels': 0}],
        }
        with (
            patch.object(scanner_router, 'get_db_connection', return_value=MagicMock()),
            patch.object(scanner_router, 'purge_orphaned_tracks', return_value=totals),
            patch('services.common.Helpers.EventService.event_service') as events,
        ):
            self.assertEqual(scanner_router.run_orphan_purge(), totals)
        kwargs = events.emit.call_args.kwargs
        self.assertIn('3 of 5', kwargs['message'])
        self.assertNotIn('kept_list', kwargs['context'])
        self.assertFalse(scanner_router.purge_state['running'])
        self.assertEqual(scanner_router.purge_state['last'], totals)

    def test_a_dry_run_writes_no_event(self):
        totals = orphan_purge.empty_purge_totals(dry_run=True)
        with (
            patch.object(scanner_router, 'get_db_connection', return_value=MagicMock()),
            patch.object(scanner_router, 'purge_orphaned_tracks', return_value=totals) as purge,
            patch('services.common.Helpers.EventService.event_service') as events,
        ):
            scanner_router.run_orphan_purge(True)
        self.assertTrue(purge.call_args.kwargs['dry_run'])
        events.emit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
