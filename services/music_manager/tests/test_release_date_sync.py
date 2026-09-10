"""What muma copies back out of the servers' databases about release dates.

The claims that carry this are all about not believing one server too readily. Production runs
two -- `stable`, which people play from, and `alpha`, six weeks stale and 8.500 tracks short --
so "this server has no date for that track" and "that track has no date" are different
sentences, and a sync that confuses them clears tens of thousands of dates every hour.

The rest is about a feed that filters on this column. A wrong date puts a track in the release
radar for a week and nobody can tell it does not belong there; a missing one only makes the
feed smaller. So every rule here fails towards no date.

The server side is a real SQLite file, the way the song-version sync tests do it: what is being
read is somebody else's schema, and a mock would answer SQL the server rejects.
"""

import sqlite3
import unittest
from unittest.mock import MagicMock

from services.music_manager.release_date_sync import MISSING, UNDATED, resolve, sync_release_dates

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
            ids = [row['track_id'] for row in self.files]
            self.rows = [{'low': min(ids), 'high': max(ids)} if ids else {'low': None, 'high': None}]
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


def server(*tracks):
    """A server database holding `(path, original_date, date)` rows."""
    conn = sqlite3.connect(':memory:')
    conn.execute(MIGRATED)
    for path, original_date, date in tracks:
        conn.execute(
            'INSERT INTO track (absolute_file_path, original_date, date) VALUES (?, ?, ?)',
            (path, original_date, date),
        )
    conn.commit()
    return conn


class ResolveTest(unittest.TestCase):
    """The decision itself, without a database on either side."""

    def test_one_agreed_date_wins(self):
        self.assertEqual('2026-09-04', resolve(['2026-09-04', '2026-09-04']))

    def test_a_track_no_server_holds_is_left_alone(self):
        """None, not `''`. A server that has never seen the music has no opinion about it, and

        treating silence as "no date" is what let a stale server clear the whole library.
        """
        self.assertIsNone(resolve([MISSING, MISSING]))

    def test_one_server_holding_it_is_enough_to_have_an_opinion(self):
        self.assertEqual('2026-09-04', resolve([MISSING, '2026-09-04']))

    def test_a_server_without_a_date_does_not_veto_one_that_has_it(self):
        """The stale server has the file but never got the tag. The current one did. Reading

        that as a disagreement would empty the radar every hour on production.
        """
        self.assertEqual('2026-09-04', resolve([UNDATED, '2026-09-04']))

    def test_two_different_days_are_a_contradiction(self):
        self.assertEqual('', resolve(['2026-09-01', '2026-09-05']))

    def test_a_year_beside_a_day_is_precision_not_disagreement(self):
        """A FLAC tagged `2026` and an MP3 tagged `2026-09-04` are one release at two

        precisions. Refusing that pair would drop most multi-format releases out of the feeds.
        """
        self.assertEqual('2026-09-04', resolve(['2026', '2026-09-04']))

    def test_a_different_year_beside_a_day_is_a_contradiction(self):
        """`2019` next to `2026-09-04` is not a coarser reading of the same thing."""
        self.assertEqual('', resolve(['2019', '2026-09-04']))

    def test_a_year_on_its_own_is_not_a_date(self):
        # The column stores day precision; a year would have to be padded to a first of January
        # and would put a few thousand tracks in every radar window.
        self.assertEqual('', resolve(['2026', '2026']))

    def test_a_file_everyone_holds_and_nobody_can_date(self):
        self.assertEqual('', resolve([UNDATED, UNDATED]))


class ReleaseDateSyncTest(unittest.TestCase):
    def test_the_original_date_wins_over_the_edition_date(self):
        """ORIGINALDATE is the release, DATE is this edition -- the same order the server's

        own queries use. Reading the edition date of a re-release would date a 2019 track to
        whenever the label put it out again.
        """
        conn, cursor = muma_with([file_row(1, '/mnt/music/EPs/x/01.mp3')])
        one = server(('/music/EPs/x/01.mp3', '2026-09-04', '2026-09-09'))

        stats = sync_release_dates(conn, [(one, 'stable')])

        self.assertEqual([('2026-09-04', 1)], cursor.written)
        self.assertEqual(1, stats['written'])

    def test_an_upload_date_is_used_when_there_is_no_release_date(self):
        """A SoundCloud or YouTube rip has no ORIGINALDATE; yt-dlp's upload date is in DATE,

        and for those two sources that is the honest "new".
        """
        conn, cursor = muma_with([file_row(7, '/mnt/music/Soundcloud/U/x.mp3')])
        one = server(('/music/Soundcloud/U/x.mp3', None, '2026-09-10'))

        sync_release_dates(conn, [(one, 'stable')])

        self.assertEqual([('2026-09-10', 7)], cursor.written)

    def test_a_stale_server_never_clears_a_track_it_does_not_have(self):
        """The production shape: two servers, one of them six weeks behind and 8.500 tracks

        short. Run per server the way the song-version sync is, the stale one would blank every
        track it has never scanned, every hour.
        """
        conn, cursor = muma_with([file_row(2, '/mnt/music/EPs/new/01.mp3', current='2026-09-04')])
        stable = server(('/music/EPs/new/01.mp3', '2026-09-04', None))
        alpha = server(('/music/EPs/old/01.mp3', '2020-01-01', None))

        sync_release_dates(conn, [(stable, 'stable'), (alpha, 'alpha')])

        self.assertEqual([], cursor.written)

    def test_a_stale_server_without_the_tag_does_not_undo_a_fresh_one(self):
        """Both servers hold the file; only the one that has rescanned has the date."""
        conn, cursor = muma_with([file_row(3, '/mnt/music/EPs/y/01.mp3')])
        stable = server(('/music/EPs/y/01.mp3', '2026-09-04', None))
        alpha = server(('/music/EPs/y/01.mp3', None, None))

        sync_release_dates(conn, [(stable, 'stable'), (alpha, 'alpha')])

        self.assertEqual([('2026-09-04', 3)], cursor.written)

    def test_two_servers_that_disagree_leave_the_track_without_a_date(self):
        conn, cursor = muma_with([file_row(4, '/mnt/music/EPs/z/01.mp3', current='2026-09-01')])
        stable = server(('/music/EPs/z/01.mp3', '2026-09-05', None))
        alpha = server(('/music/EPs/z/01.mp3', '2026-09-01', None))

        stats = sync_release_dates(conn, [(stable, 'stable'), (alpha, 'alpha')])

        self.assertEqual([('', 4)], cursor.written)
        self.assertEqual(1, stats['cleared'])

    def test_two_files_that_disagree_leave_the_track_without_a_date(self):
        """A FLAC and an MP3 of one recording can carry different dates, and there is no honest

        way to pick.
        """
        conn, cursor = muma_with(
            [
                file_row(5, '/mnt/music/EPs/w/01.flac'),
                file_row(5, '/mnt/music/EPs/w/01.mp3'),
            ]
        )
        one = server(
            ('/music/EPs/w/01.flac', '2026-09-01', None),
            ('/music/EPs/w/01.mp3', '2026-09-05', None),
        )

        sync_release_dates(conn, [(one, 'stable')])

        self.assertEqual([('', 5)], cursor.written)

    def test_a_date_that_went_away_is_cleared_as_a_decision(self):
        """Written as `''` rather than NULL, and the difference is what feeds/queries.py reads:

        NULL still falls back to the analyzer's column, the empty string does not. Left as NULL
        this would resurrect the very value the servers just contradicted.
        """
        conn, cursor = muma_with([file_row(6, '/mnt/music/EPs/v/01.mp3', current='2026-01-01')])
        one = server(('/music/EPs/v/01.mp3', '', ''))

        stats = sync_release_dates(conn, [(one, 'stable')])

        self.assertEqual([('', 6)], cursor.written)
        self.assertEqual(1, stats['cleared'])

    def test_an_unchanged_date_is_not_written_again(self):
        conn, cursor = muma_with([file_row(8, '/mnt/music/EPs/u/01.mp3', current='2026-09-04')])
        one = server(('/music/EPs/u/01.mp3', '2026-09-04', None))

        sync_release_dates(conn, [(one, 'stable')])

        self.assertEqual([], cursor.written)

    def test_a_server_without_the_columns_is_left_out_not_failed(self):
        conn, cursor = muma_with([file_row(9, '/mnt/music/EPs/t/01.mp3')])
        unmigrated = sqlite3.connect(':memory:')
        unmigrated.execute(UNMIGRATED)
        stable = server(('/music/EPs/t/01.mp3', '2026-09-04', None))

        stats = sync_release_dates(conn, [(unmigrated, 'alpha'), (stable, 'stable')])

        self.assertEqual(1, stats['skipped_no_columns'])
        self.assertEqual(1, stats['servers'])
        self.assertEqual([('2026-09-04', 9)], cursor.written)

    def test_a_server_mid_rebuild_is_left_out_rather_than_believed(self):
        """An empty track table is a server rebuilding, not one where every date vanished.

        Counted as MISSING for the whole library it would contradict nothing -- but it would
        also make a single-server deployment clear everything, so it is dropped outright.
        """
        conn, cursor = muma_with([file_row(10, '/mnt/music/EPs/s/01.mp3', current='2026-09-04')])
        empty = sqlite3.connect(':memory:')
        empty.execute(MIGRATED)

        stats = sync_release_dates(conn, [(empty, 'alpha')])

        self.assertEqual(1, stats['skipped_empty'])
        self.assertEqual([], cursor.written)

    def test_no_usable_server_writes_nothing_at_all(self):
        conn, cursor = muma_with([file_row(11, '/mnt/music/EPs/r/01.mp3', current='2026-09-04')])

        stats = sync_release_dates(conn, [])

        self.assertEqual(0, stats['servers'])
        self.assertEqual([], cursor.written)

    def test_an_empty_library_asks_the_servers_nothing(self):
        conn, cursor = muma_with([])
        one = server(('/music/EPs/q/01.mp3', '2026-09-04', None))

        stats = sync_release_dates(conn, [(one, 'stable')])

        self.assertEqual(0, stats['considered'])
        self.assertEqual([], cursor.written)


if __name__ == '__main__':
    unittest.main()
