"""What muma writes into the server's database about song versions.

Two claims carry this: a track muma has not grouped stays visible, and a row that
already carries a stale answer is corrected rather than left alone. Both are about
failing towards showing too much -- the filter built on these columns hides music when
they are wrong, and nobody notices music that is missing.

Runs against a real SQLite file rather than a mock: what is being tested is a write to
somebody else's schema, and a mock would happily accept SQL the server rejects.
"""

import sqlite3
import unittest
from unittest.mock import MagicMock

from services.music_manager.song_version_sync import sync_song_versions_to_server

MIGRATED = """
    CREATE TABLE track (
        id INTEGER PRIMARY KEY,
        absolute_file_path TEXT,
        work_id INTEGER,
        is_canonical INTEGER NOT NULL DEFAULT 1,
        version_kind TEXT NOT NULL DEFAULT '',
        version_score INTEGER NOT NULL DEFAULT 0
    )
"""

UNMIGRATED = 'CREATE TABLE track (id INTEGER PRIMARY KEY, absolute_file_path TEXT)'


def muma_with(rows):
    """A muma connection whose cursor yields `rows` once, the way fetchmany is used."""
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    cursor.fetchmany.side_effect = [list(rows), []]
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


def row(path, work_id=None, is_canonical=1, kind='', score=0):
    return {
        'file_path': path,
        'work_id': work_id,
        'is_canonical': is_canonical,
        'version_kind': kind,
        'version_score': score,
    }


class SongVersionSyncTest(unittest.TestCase):
    def setUp(self):
        self.server = sqlite3.connect(':memory:')
        self.server.execute(MIGRATED)
        self.server.commit()

    def tearDown(self):
        self.server.close()

    def add_track(self, track_id, path, **columns):
        defaults = {'work_id': None, 'is_canonical': 1, 'version_kind': '', 'version_score': 0}
        defaults.update(columns)
        self.server.execute(
            'INSERT INTO track (id, absolute_file_path, work_id, is_canonical, version_kind, version_score) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (
                track_id,
                path,
                defaults['work_id'],
                defaults['is_canonical'],
                defaults['version_kind'],
                defaults['version_score'],
            ),
        )
        self.server.commit()

    def stored(self, track_id):
        cursor = self.server.execute(
            'SELECT work_id, is_canonical, version_kind, version_score FROM track WHERE id = ?', (track_id,)
        )
        return cursor.fetchone()

    def test_a_canonical_track_is_marked_as_one(self):
        self.add_track(1, '/mnt/music/EPs/Texcore/01.mp3')
        stats = sync_song_versions_to_server(
            muma_with([row('/mnt/music/EPs/Texcore/01.mp3', work_id=42, is_canonical=1, kind='radio', score=1010000)]),
            self.server,
        )
        self.assertEqual(self.stored(1), (42, 1, 'radio', 1010000))
        self.assertEqual(stats['matched'], 1)

    def test_a_losing_version_is_marked_as_not_canonical(self):
        self.add_track(1, '/mnt/music/Soundcloud/rip.mp3')
        sync_song_versions_to_server(
            muma_with([row('/mnt/music/Soundcloud/rip.mp3', work_id=42, is_canonical=0, kind='extended')]),
            self.server,
        )
        self.assertEqual(self.stored(1)[1], 0)

    def test_a_track_muma_has_not_grouped_stays_visible(self):
        # Half the library sits ungrouped whenever the worker is catching up. Hiding those
        # would empty the browser of music that exists.
        self.add_track(1, '/mnt/music/EPs/Texcore/01.mp3')
        sync_song_versions_to_server(
            muma_with([row('/mnt/music/EPs/Texcore/01.mp3', work_id=None, is_canonical=1)]),
            self.server,
        )
        self.assertEqual(self.stored(1), (None, 1, '', 0))

    def test_a_track_that_left_its_work_stops_being_hidden(self):
        # The split case. Without an active correction the row keeps the 0 it was given and
        # the track is invisible for good.
        self.add_track(1, '/mnt/music/Soundcloud/rip.mp3', work_id=42, is_canonical=0, version_kind='extended')
        sync_song_versions_to_server(
            muma_with([row('/mnt/music/Soundcloud/rip.mp3', work_id=None, is_canonical=1)]),
            self.server,
        )
        self.assertEqual(self.stored(1), (None, 1, '', 0))

    def test_the_server_path_spelling_is_matched_too(self):
        # muma scans /mnt/music; this server was told /music. Same file, two names.
        self.add_track(1, '/music/EPs/Texcore/01.mp3')
        stats = sync_song_versions_to_server(
            muma_with([row('/mnt/music/EPs/Texcore/01.mp3', work_id=7, is_canonical=1)]),
            self.server,
        )
        self.assertEqual(self.stored(1)[0], 7)
        self.assertEqual(stats['matched'], 1)

    def test_a_file_this_server_does_not_have_is_not_an_error(self):
        stats = sync_song_versions_to_server(
            muma_with([row('/mnt/music/EPs/Texcore/absent.mp3', work_id=7)]),
            self.server,
        )
        self.assertEqual((stats['considered'], stats['matched']), (1, 0))

    def test_a_server_without_the_columns_is_left_alone(self):
        # The window between deploying the images and the server migrating itself.
        old = sqlite3.connect(':memory:')
        old.execute(UNMIGRATED)
        old.execute("INSERT INTO track (id, absolute_file_path) VALUES (1, '/mnt/music/a.mp3')")
        old.commit()
        stats = sync_song_versions_to_server(muma_with([row('/mnt/music/a.mp3', work_id=7)]), old)
        self.assertEqual(stats['skipped_no_columns'], 1)
        self.assertEqual(stats['considered'], 0)
        old.close()

    def test_a_locked_database_costs_this_pass_and_nothing_else(self):
        self.add_track(1, '/mnt/music/EPs/Texcore/01.mp3')
        locked = MagicMock()
        locked.cursor.return_value = self.server.cursor()
        locked.execute.side_effect = sqlite3.OperationalError('database is locked')
        # No exception reaches the caller: the lms.db pass has users and playlists to finish.
        stats = sync_song_versions_to_server(muma_with([row('/mnt/music/EPs/Texcore/01.mp3', work_id=7)]), locked)
        self.assertEqual(stats['matched'], 0)


if __name__ == '__main__':
    unittest.main()
