"""Bug report 117: a value too long for its column, and a file that keeps failing.

On production 28 m4a files failed every hourly scan with MariaDB 1406 on library_tracks.title or
display_artist -- their tags held one value repeated up to 241 times. The scanner now cuts such a
value to the column's character length, stores the file, and queues it for the tagger's repair;
and a file that fails for any reason is parked after SCANNER_PARK_AFTER failures in a row.
"""

import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector')

from services.music_manager.routers import scanner as scanner_router
from services.tagger.Song.BaseSong import BaseSong

CRYPTON_TITLE = ';'.join(["UNTIL IT'S GONE"] * 241 + ['Crypton'])


def a_song(title='Raise Your Fist', display_artist=None, artists=('Angerfist',)):
    """A song stub with the given title, credit and artists, and no genres."""
    song = MagicMock(spec_set=BaseSong)
    song.library_artists.return_value = list(artists)
    song.publisher.return_value = None
    song.title.return_value = title
    song.length.return_value = 300
    song.rules_genres.return_value = []
    song.original_artist.return_value = display_artist
    return song


class FitColumnTest(unittest.TestCase):
    def test_a_short_value_and_none_pass_unchanged(self):
        self.assertEqual(scanner_router.fit_column('Raise Your Fist', 512), 'Raise Your Fist')
        self.assertIsNone(scanner_router.fit_column(None, 512))

    def test_a_long_value_is_cut_to_the_column_length(self):
        self.assertEqual(len(scanner_router.fit_column(CRYPTON_TITLE, 512)), 512)

    def test_the_cut_counts_characters_not_bytes(self):
        # '｜' is 3 bytes and an emoji 4 in utf8mb4; MariaDB's VARCHAR(512) counts characters,
        # so 512 of them fit and none is split.
        value = '｜👽' * 400
        cut = scanner_router.fit_column(value, 512)
        self.assertEqual(len(cut), 512)
        self.assertEqual(cut, value[:512])
        cut.encode('utf-8')  # a split surrogate or code point would raise here

    def test_trailing_whitespace_left_by_the_cut_is_dropped(self):
        self.assertEqual(scanner_router.fit_column('ab cd', 3), 'ab')


class ProcessFileOverlongTest(unittest.TestCase):
    def setUp(self):
        self.manager = scanner_router.ScannerManager()
        self.manager.music_path = '/music'
        self.manager.genre_helper = MagicMock()
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = self.cursor
        self.conn.cursor.return_value.__exit__.return_value = False
        self.cursor.fetchone.side_effect = [None, {'id': 3}, {'id': 5}]
        for p in (
            patch.object(scanner_router.os.path, 'getmtime', return_value=100.0),
            patch.object(scanner_router.os.path, 'getsize', return_value=1024),
            patch.object(self.manager, '_resolve_genre_ids', return_value=[]),
            patch.object(self.manager, '_resolve_channel_id', return_value=None),
        ):
            p.start()
            self.addCleanup(p.stop)

    def scan(self, song):
        with (
            patch.object(scanner_router, 'ReadonlySong', return_value=song),
            patch.object(scanner_router, 'request_retag') as retag,
        ):
            stored = self.manager.process_file(self.conn, '/music/Soundcloud/Crypton/a.m4a')
        return stored, retag

    def params_of(self, fragment):
        return next(call.args[1] for call in self.cursor.execute.call_args_list if fragment in call.args[0])

    def test_an_overlong_title_is_cut_and_the_file_queued_for_a_retag(self):
        with self.assertLogs(scanner_router.logger, level='WARNING') as logs:
            stored, retag = self.scan(a_song(title=CRYPTON_TITLE))
        self.assertTrue(stored)
        params = self.params_of('INSERT INTO library_tracks')
        self.assertEqual(params[1], CRYPTON_TITLE[:512].rstrip())
        self.assertEqual(params[1], params[7])
        retag.assert_called_once_with('/music/Soundcloud/Crypton/a.m4a')
        self.assertEqual(len(logs.records), 1)
        self.assertIn('title', logs.output[0])

    def test_an_overlong_display_artist_is_cut(self):
        credit = ';'.join(['Karma Outdoor 2025'] * 181)
        stored, retag = self.scan(a_song(display_artist=credit))
        self.assertTrue(stored)
        params = self.params_of('INSERT INTO library_tracks')
        self.assertEqual(len(params[4]), 512)
        retag.assert_called_once()

    def test_an_overlong_artist_name_is_cut_in_both_statements(self):
        name = 'A' * 300
        stored, _retag = self.scan(a_song(artists=(name,)))
        self.assertTrue(stored)
        self.assertEqual(self.params_of('INSERT IGNORE INTO library_artists'), ('A' * 255,))
        self.assertEqual(self.params_of('SELECT id FROM library_artists'), ('A' * 255,))

    def test_a_title_that_fits_is_stored_as_it_is_and_queues_nothing(self):
        stored, retag = self.scan(a_song(title='The Sound of Q-dance Chile ｜ Official Q-dance Aftermovie'))
        self.assertTrue(stored)
        self.assertEqual(
            self.params_of('INSERT INTO library_tracks')[1], 'The Sound of Q-dance Chile ｜ Official Q-dance Aftermovie'
        )
        retag.assert_not_called()


class RequestRetagTest(unittest.TestCase):
    def test_the_file_is_marked_with_its_reason(self):
        with patch.object(scanner_router, 'ProcessedFilesHelper') as helper:
            scanner_router.request_retag('/music/a.m4a')
        helper.return_value.mark_for_rescan.assert_called_once_with(
            '/music/a.m4a', reason=scanner_router.OVERLONG_TAG_REASON
        )

    def test_a_queue_that_cannot_be_reached_does_not_fail_the_scan(self):
        with patch.object(scanner_router, 'ProcessedFilesHelper', side_effect=RuntimeError('db down')):
            scanner_router.request_retag('/music/a.m4a')


class ParkingTest(unittest.TestCase):
    PATH = '/music/a.m4a'

    def setUp(self):
        self.manager = scanner_router.ScannerManager()
        self.version = (100.0, 1024)
        patcher = patch.object(self.manager, '_file_version', side_effect=lambda _path: self.version)
        patcher.start()
        self.addCleanup(patcher.stop)

    def attempt(self, process, force=False):
        with patch.object(self.manager, 'process_file', process):
            return self.manager._process_file_safe(MagicMock(), self.PATH, force)

    def test_a_file_that_keeps_failing_is_parked_after_the_limit(self):
        failing = MagicMock(side_effect=RuntimeError('(1406, "Data too long")'))
        with self.assertLogs(scanner_router.logger, level='ERROR') as errors:
            for _ in range(scanner_router.SCANNER_PARK_AFTER - 1):
                self.assertFalse(self.attempt(failing))
        self.assertEqual(len(errors.records), scanner_router.SCANNER_PARK_AFTER - 1)
        with self.assertLogs(scanner_router.logger, level='WARNING') as parked:
            self.attempt(failing)
        self.assertEqual([r.levelname for r in parked.records], ['WARNING'])
        self.assertIn('Parked', parked.output[0])
        failing.reset_mock()
        with self.assertNoLogs(scanner_router.logger, level='WARNING'):
            self.assertFalse(self.attempt(failing))
        failing.assert_not_called()

    def test_a_parked_file_that_changes_is_scanned_again(self):
        failing = MagicMock(side_effect=RuntimeError('boom'))
        with self.assertLogs(scanner_router.logger, level='ERROR'):
            for _ in range(scanner_router.SCANNER_PARK_AFTER):
                self.attempt(failing)
        self.version = (200.0, 2048)
        succeeding = MagicMock(return_value=True)
        self.assertTrue(self.attempt(succeeding))
        succeeding.assert_called_once()
        self.assertNotIn(self.PATH, self.manager._failures)

    def test_a_forced_scan_ignores_the_parking(self):
        failing = MagicMock(side_effect=RuntimeError('boom'))
        with self.assertLogs(scanner_router.logger, level='ERROR'):
            for _ in range(scanner_router.SCANNER_PARK_AFTER):
                self.attempt(failing)
        succeeding = MagicMock(return_value=True)
        self.assertTrue(self.attempt(succeeding, force=True))

    def test_a_success_clears_the_count(self):
        failing = MagicMock(side_effect=RuntimeError('boom'))
        with self.assertLogs(scanner_router.logger, level='ERROR'):
            self.attempt(failing)
        self.attempt(MagicMock(return_value=False))
        self.assertNotIn(self.PATH, self.manager._failures)

    def test_an_unsupported_extension_is_not_counted(self):
        unsupported = MagicMock(side_effect=scanner_router.ExtensionNotSupportedException('x'))
        self.assertFalse(self.attempt(unsupported))
        self.assertNotIn(self.PATH, self.manager._failures)


if __name__ == '__main__':
    unittest.main()
