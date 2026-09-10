"""What muma copies back out of the server's database about release dates.

Three claims carry this: a track only gets a date its files agree on, a date that has
gone away is written back as NULL rather than left standing, and a server that does not
have the file at all leaves the track alone rather than blanking it.

All three are about a feed that filters on this column. A wrong date puts a track in the
release radar for a week and nobody can tell it does not belong there; a missing one only
makes the feed smaller. So the rules here fail towards no date.

The server side is a real SQLite file, the way the song-version sync tests do it: what is
being read is somebody else's schema, and a mock would answer SQL the server rejects.
"""

import sqlite3
import unittest
from unittest.mock import MagicMock

from services.music_manager.release_date_sync import sync_release_dates_from_server

MIGRATED = """
    CREATE TABLE track (
        id INTEGER PRIMARY KEY,
        absolute_file_path TEXT,
        original_date TEXT,
        date TEXT
    )
"""

UNMIGRATED = 'CREATE TABLE track (id INTEGER PRIMARY KEY, absolute_file_path TEXT)'


class FakeMumaCursor:
    """Answers the two statements the sync reads, and records what it was asked to write."""

    def __init__(self, files):
        self.files = files
        self.rows: list = []
        self.written: list = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        if 'MIN(id)' in sql:
            ids = [row['track_id'] for row in self.files] or [None]
            self.rows = [{'low': min(ids) if ids[0] is not None else None, 'high': max(ids) if ids[0] else None}]
            return
        low, high = params
        self.rows = [row for row in self.files if low <= row['track_id'] < high]

    def executemany(self, _sql, params):
        self.written.extend(params)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


def muma_with(files):
    cursor = FakeMumaCursor(files)
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


def file_row(track_id, path, current=None):
    return {'track_id': track_id, 'file_path': path, 'current': current}


class ReleaseDateSyncTest(unittest.TestCase):
    def setUp(self):
        self.server = sqlite3.connect(':memory:')
        self.server.execute(MIGRATED)
        self.server.commit()

    def tearDown(self):
        self.server.close()

    def add_track(self, path, original_date=None, date=None):
        self.server.execute(
            'INSERT INTO track (absolute_file_path, original_date, date) VALUES (?, ?, ?)',
            (path, original_date, date),
        )
        self.server.commit()

    def test_the_original_date_wins_over_the_edition_date(self):
        """ORIGINALDATE is the release, DATE is this edition -- the same order the server's

        own queries use. Reading the edition date of a re-release would date a 2019 track
        to whenever the label put it out again.
        """
        self.add_track('/music/EPs/x/01.mp3', original_date='2026-09-04', date='2026-09-09')
        conn, cursor = muma_with([file_row(1, '/mnt/music/EPs/x/01.mp3')])

        stats = sync_release_dates_from_server(conn, self.server, 'test')

        self.assertEqual([('2026-09-04', 1)], cursor.written)
        self.assertEqual(1, stats['written'])

    def test_an_upload_date_is_used_when_there_is_no_release_date(self):
        """A SoundCloud or YouTube rip has no ORIGINALDATE; yt-dlp's upload date is in DATE,

        and for those two sources that is the honest "new".
        """
        self.add_track('/music/Soundcloud/Undivided/x.mp3', original_date=None, date='2026-09-10')
        conn, cursor = muma_with([file_row(7, '/mnt/music/Soundcloud/Undivided/x.mp3')])

        sync_release_dates_from_server(conn, self.server, 'test')

        self.assertEqual([('2026-09-10', 7)], cursor.written)

    def test_a_year_is_not_a_date(self):
        """`date` is a year for most of the library. Padded to a first of January it would

        put a few thousand tracks in every radar window; length is the precision here.
        """
        self.add_track('/music/EPs/y/01.mp3', date='2026')
        conn, cursor = muma_with([file_row(2, '/mnt/music/EPs/y/01.mp3')])

        sync_release_dates_from_server(conn, self.server, 'test')

        self.assertEqual([], cursor.written)

    def test_two_files_that_disagree_leave_the_track_without_a_date(self):
        """A FLAC and an MP3 of one recording can carry different dates, and there is no

        honest way to pick. The audio-features subquery in feeds/queries.py applies the
        same rule and the two have to keep agreeing.
        """
        self.add_track('/music/EPs/z/01.flac', original_date='2026-09-01')
        self.add_track('/music/EPs/z/01.mp3', original_date='2026-09-05')
        conn, cursor = muma_with(
            [
                file_row(3, '/mnt/music/EPs/z/01.flac'),
                file_row(3, '/mnt/music/EPs/z/01.mp3'),
            ]
        )

        sync_release_dates_from_server(conn, self.server, 'test')

        self.assertEqual([], cursor.written)

    def test_two_files_that_agree_still_get_the_date(self):
        self.add_track('/music/EPs/z/01.flac', original_date='2026-09-05')
        self.add_track('/music/EPs/z/01.mp3', original_date='2026-09-05')
        conn, cursor = muma_with(
            [
                file_row(4, '/mnt/music/EPs/z/01.flac'),
                file_row(4, '/mnt/music/EPs/z/01.mp3'),
            ]
        )

        sync_release_dates_from_server(conn, self.server, 'test')

        self.assertEqual([('2026-09-05', 4)], cursor.written)

    def test_a_date_that_went_away_is_cleared(self):
        """Left standing, a corrected tag would keep the track in the radar forever. The

        sync writes NULL rather than skipping the row.
        """
        self.add_track('/music/EPs/w/01.mp3', original_date='')
        conn, cursor = muma_with([file_row(5, '/mnt/music/EPs/w/01.mp3', current='2026-01-01')])

        stats = sync_release_dates_from_server(conn, self.server, 'test')

        self.assertEqual([(None, 5)], cursor.written)
        self.assertEqual(1, stats['cleared'])

    def test_an_unchanged_date_is_not_written_again(self):
        self.add_track('/music/EPs/v/01.mp3', original_date='2026-09-04')
        conn, cursor = muma_with([file_row(6, '/mnt/music/EPs/v/01.mp3', current='2026-09-04')])

        sync_release_dates_from_server(conn, self.server, 'test')

        self.assertEqual([], cursor.written)

    def test_a_server_without_the_columns_is_skipped_not_failed(self):
        server = sqlite3.connect(':memory:')
        server.execute(UNMIGRATED)
        conn, cursor = muma_with([file_row(8, '/mnt/music/EPs/u/01.mp3')])

        stats = sync_release_dates_from_server(conn, server, 'test')

        self.assertEqual(1, stats['skipped_no_columns'])
        self.assertEqual([], cursor.written)
        server.close()

    def test_a_server_mid_rebuild_clears_nothing(self):
        """A server whose track table is empty is one that is rebuilding, not one where every

        release date vanished. Clearing on that reading would empty both feeds for an hour --
        the exact failure this column was added to end.
        """
        conn, cursor = muma_with([file_row(9, '/mnt/music/EPs/t/01.mp3', current='2026-09-04')])

        sync_release_dates_from_server(conn, self.server, 'test')

        self.assertEqual([], cursor.written)

    def test_an_empty_library_asks_the_server_nothing(self):
        self.add_track('/music/EPs/s/01.mp3', original_date='2026-09-04')
        conn, cursor = muma_with([])

        stats = sync_release_dates_from_server(conn, self.server, 'test')

        self.assertEqual(0, stats['considered'])
        self.assertEqual([], cursor.written)


if __name__ == '__main__':
    unittest.main()
