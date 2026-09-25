"""The hourly form pass and the push of form and performance date into the servers.

The pass must write only what changed and clear a performance date that no longer applies; the
push must write only rows the server disagrees with and skip a server that has not migrated.
The push runs against a real SQLite database, like test_song_version_sync, because what it tests
is a write into somebody else's schema.
"""

import sqlite3
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from services.common.Helpers.FestivalHelper import Festival, FestivalHelper
from services.common.Helpers.PodcastHelper import PodcastHelper
from services.music_manager import track_form_sync

ROOT = '/mnt/music'


def festivals():
    helper = FestivalHelper(preload=False)
    helper.set_festivals([Festival(name='Defqon.1', aliases=['Defqon.1'], editions={2012: date(2012, 6, 23)})])
    return helper


def muma_cursor(fetchall=None, fetchmany=None):
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    cursor.fetchone.return_value = {'low': 1, 'high': 3}
    if fetchall is not None:
        cursor.fetchall.return_value = fetchall
    if fetchmany is not None:
        cursor.fetchmany.side_effect = [fetchmany, []]
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


def track(track_id, path, duration, title, form=None, performance_date=None):
    return {
        'id': track_id,
        'file_path': path,
        'duration_secs': duration,
        'title': title,
        'form': form,
        'performance_date': performance_date,
    }


class ClassifyLibraryTest(unittest.TestCase):
    def run_pass(self, rows):
        conn, cursor = muma_cursor(fetchall=rows)
        stats = track_form_sync.classify_library(conn, ROOT, festivals(), PodcastHelper(preload=False))
        return stats, cursor, conn

    def test_only_rows_that_differ_are_written(self):
        stats, cursor, conn = self.run_pass(
            [
                track(1, f'{ROOT}/EPs/l/c/a.flac', 300, 'Song', form='track'),
                track(2, f'{ROOT}/Youtube/q/a.mp3', 3600, 'X @ Defqon.1 2012'),
                track(3, f'{ROOT}/Warm Up Mixes/a.mp3', 3600, 'Mix', form='set'),
            ]
        )
        cursor.executemany.assert_called_once_with(track_form_sync._UPDATE_MUMA, [('liveset', '2012-06-23', 2)])
        conn.commit.assert_called_once()
        self.assertEqual(stats, {'considered': 3, 'written': 1})

    def test_a_date_that_no_longer_applies_is_cleared(self):
        # The edition was removed: the live set keeps its form and loses its date.
        _stats, cursor, _conn = self.run_pass(
            [track(1, f'{ROOT}/Livesets/x/a.mp3', 3600, 'Qlimax 2019', form='liveset', performance_date='2019-11-23')]
        )
        cursor.executemany.assert_called_once_with(track_form_sync._UPDATE_MUMA, [('liveset', None, 1)])

    def test_nothing_changed_writes_nothing(self):
        _stats, cursor, conn = self.run_pass([track(1, f'{ROOT}/Soundcloud/a/b.mp3', 200, 'Song', form='track')])
        cursor.executemany.assert_not_called()
        conn.commit.assert_not_called()

    def test_an_empty_library_is_no_work(self):
        conn, cursor = muma_cursor(fetchall=[])
        cursor.fetchone.return_value = {'low': None, 'high': None}
        stats = track_form_sync.classify_library(conn, ROOT, None, None)
        self.assertEqual(stats, {'considered': 0, 'written': 0})

    def test_a_database_error_is_logged_not_raised(self):
        conn, cursor = muma_cursor()
        cursor.execute.side_effect = RuntimeError('gone')
        with self.assertLogs(track_form_sync.logger, 'ERROR'):
            track_form_sync.classify_library(conn, ROOT, None, None)

    def test_run_classification_reads_the_current_rules(self):
        with (
            patch('services.common.Helpers.FestivalHelper.FestivalHelper.reload'),
            patch('services.common.Helpers.PodcastHelper.PodcastHelper.reload'),
            patch.object(track_form_sync, 'classify_library', return_value={'written': 0}) as run,
        ):
            track_form_sync.run_classification(MagicMock())
        run.assert_called_once()


MIGRATED = """
    CREATE TABLE track (
        id INTEGER PRIMARY KEY,
        absolute_file_path TEXT,
        form TEXT NOT NULL DEFAULT '',
        performance_date TEXT NOT NULL DEFAULT ''
    )
"""


class PushFormsTest(unittest.TestCase):
    def setUp(self):
        self.server = sqlite3.connect(':memory:')
        self.server.execute(MIGRATED)
        self.server.execute("INSERT INTO track (absolute_file_path) VALUES ('/music/Livesets/a.mp3')")
        self.server.execute("INSERT INTO track (absolute_file_path, form) VALUES ('/music/EPs/b.flac', 'track')")
        self.server.commit()

    def tearDown(self):
        self.server.close()

    def stored(self):
        return self.server.execute(
            'SELECT absolute_file_path, form, performance_date FROM track ORDER BY id'
        ).fetchall()

    def test_writes_the_rows_the_server_disagrees_with(self):
        conn, _cursor = muma_cursor(
            fetchmany=[
                {'file_path': '/mnt/music/Livesets/a.mp3', 'form': 'liveset', 'performance_date': '2012-06-23'},
                {'file_path': '/mnt/music/EPs/b.flac', 'form': 'track', 'performance_date': ''},
                {'file_path': '/mnt/music/unknown.mp3', 'form': 'set', 'performance_date': ''},
            ]
        )
        stats = track_form_sync.push_forms_to_server(conn, self.server, 'test')
        self.assertEqual(
            self.stored(),
            [('/music/Livesets/a.mp3', 'liveset', '2012-06-23'), ('/music/EPs/b.flac', 'track', '')],
        )
        self.assertEqual(stats['considered'], 3)
        self.assertEqual(stats['matched'], 1)

    def test_a_server_without_the_columns_is_skipped(self):
        server = sqlite3.connect(':memory:')
        server.execute('CREATE TABLE track (id INTEGER PRIMARY KEY, absolute_file_path TEXT)')
        conn, cursor = muma_cursor(fetchmany=[])
        stats = track_form_sync.push_forms_to_server(conn, server, 'old')
        self.assertEqual(stats['skipped_no_columns'], 1)
        cursor.execute.assert_not_called()
        server.close()


if __name__ == '__main__':
    unittest.main()
