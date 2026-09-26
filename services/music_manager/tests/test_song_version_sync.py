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
from unittest.mock import MagicMock, patch

from services.music_manager import song_version_sync as sync_module
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


_media_ids = iter(range(1, 1_000_000))
_UNSET = object()


def row(
    path,
    work_id=None,
    is_canonical=1,
    kind='',
    score=0,
    track_id=None,
    canonical_track_id=_UNSET,
    own_row=1,
    media_id=None,
    file_size=7_200_000,
    duration_secs=300.0,
):
    """One muma media-file row as the sync's query returns it.

    `is_canonical` is the old per-file shorthand the first tests speak: a row that says 1 names
    its own track as the work's canonical, a row that says 0 names some other track.
    """
    media_id = media_id if media_id is not None else next(_media_ids)
    track_id = track_id if track_id is not None else 100_000 + media_id
    if canonical_track_id is _UNSET:
        canonical_track_id = None if work_id is None else (track_id if is_canonical else -1)
    return {
        'media_id': media_id,
        'file_path': path,
        'file_size': file_size,
        'duration_secs': duration_secs,
        'own_row': own_row,
        'track_id': track_id,
        'work_id': work_id,
        'version_kind': kind,
        'version_score': score,
        'canonical_track_id': canonical_track_id,
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
        self.add_track(2, '/mnt/music/EPs/Texcore/01.mp3')
        sync_song_versions_to_server(
            muma_with(
                [
                    row('/mnt/music/EPs/Texcore/01.mp3', work_id=42, track_id=10, canonical_track_id=10),
                    row(
                        '/mnt/music/Soundcloud/rip.mp3', work_id=42, track_id=11, canonical_track_id=10, kind='extended'
                    ),
                ]
            ),
            self.server,
        )
        self.assertEqual(self.stored(1)[1], 0)
        self.assertEqual(self.stored(2)[1], 1)

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


class FlakyServer:
    """A server connection whose commit can refuse, the way a busy LMS does.

    sqlite3.Connection is a C object and takes no patched attributes, so the refusal is
    wrapped around a real database rather than mocked onto one -- which also keeps the
    writes real: what is asserted afterwards is what SQLite actually stored.
    """

    def __init__(self, connection, failures: int, error: str = 'database is locked'):
        self._connection = connection
        self._failures = failures
        self._error = error
        self.commits = 0

    def cursor(self):
        return self._connection.cursor()

    def execute(self, *args):
        return self._connection.execute(*args)

    def rollback(self):
        return self._connection.rollback()

    def commit(self):
        self.commits += 1
        if self.commits <= self._failures:
            raise sqlite3.OperationalError(self._error)
        return self._connection.commit()


class LockedServerDatabaseTest(SongVersionSyncTest):
    """A locked database is the server working, not a failure.

    The first version treated it as the end of the pass. On the 0.56.0 deploy LMS was
    running its own startup scan, the sync met a locked database, and it wrote one track out
    of 285.332 -- leaving the server's copy of the version model a day stale. Nothing came
    back either, because the sync only ran at startup.
    """

    def test_a_chunk_that_is_locked_once_is_written_after_the_wait(self):
        self.add_track(1, '/mnt/music/Soundcloud/rip.mp3')
        self.add_track(2, '/mnt/music/EPs/Texcore/01.mp3', work_id=42)
        server = FlakyServer(self.server, failures=1)

        with patch.object(sync_module, 'time') as clock:
            stats = sync_song_versions_to_server(
                muma_with(
                    [
                        row('/mnt/music/EPs/Texcore/01.mp3', work_id=42, track_id=10, canonical_track_id=10),
                        row('/mnt/music/Soundcloud/rip.mp3', work_id=42, track_id=11, canonical_track_id=10),
                    ]
                ),
                server,
            )

        clock.sleep.assert_called_once()
        self.assertEqual(stats['matched'], 1)
        self.assertEqual(self.stored(1)[1], 0)

    def test_a_chunk_that_stays_locked_is_skipped_rather_than_ending_the_pass(self):
        self.add_track(1, '/mnt/music/EPs/Texcore/01.mp3')
        server = FlakyServer(self.server, failures=99)

        with patch.object(sync_module, 'time'), patch.object(sync_module, 'LOCK_RETRIES', 3):
            stats = sync_song_versions_to_server(
                muma_with([row('/mnt/music/EPs/Texcore/01.mp3', work_id=42)]),
                server,
            )

        self.assertEqual(stats['chunks_skipped'], 1)
        self.assertEqual(stats['matched'], 0)
        self.assertEqual(server.commits, 3, 'every retry has to reach the database')

    def test_an_error_that_is_not_a_lock_is_not_waited_out(self):
        # Waiting on a broken schema helps nobody and buries the real message.
        self.add_track(1, '/mnt/music/EPs/Texcore/01.mp3')
        server = FlakyServer(self.server, failures=99, error='no such table: track')

        with patch.object(sync_module, 'time') as clock:
            sync_song_versions_to_server(muma_with([row('/mnt/music/EPs/Texcore/01.mp3', work_id=42)]), server)

        clock.sleep.assert_not_called()

    def test_it_yields_quickly_rather_than_holding_the_player_up(self):
        # This pinned the opposite yesterday, and the opposite was wrong. LMS dies on a
        # locked database with an uncaught exception -- 102 restarts and no music -- so the
        # background job has to let go long before the player asks twice.
        self.assertLessEqual(sync_module.BUSY_TIMEOUT_MS, 5000)

    def test_the_timeout_statement_says_what_the_constant_says(self):
        # The statement is a literal because PRAGMA takes no bound parameter, so nothing but
        # this test stops the two from drifting apart.
        self.assertEqual(
            sync_module.BUSY_TIMEOUT_STATEMENT,
            f'PRAGMA busy_timeout = {sync_module.BUSY_TIMEOUT_MS}',
        )


class OnlyChangedRowsTest(SongVersionSyncTest):
    """Rewriting rows that already say the right thing is what put this job in the way.

    Every hour it walked 285.000 tracks and wrote all of them, holding the write lock the
    player needs. After the first pass almost nothing changes, so almost nothing should be
    written.
    """

    def test_a_row_that_already_agrees_is_not_rewritten(self):
        self.add_track(1, '/mnt/music/EPs/Texcore/01.mp3', work_id=42, is_canonical=1, version_kind='radio')
        stats = sync_song_versions_to_server(
            muma_with([row('/mnt/music/EPs/Texcore/01.mp3', work_id=42, is_canonical=1, kind='radio')]),
            self.server,
        )
        self.assertEqual(stats['considered'], 1)
        self.assertEqual(stats['matched'], 0, 'nothing changed, so nothing was written')

    def test_a_row_that_disagrees_is_written(self):
        self.add_track(1, '/mnt/music/Soundcloud/rip.mp3', work_id=42, is_canonical=1)
        self.add_track(2, '/mnt/music/EPs/Texcore/01.mp3', work_id=42, is_canonical=1)
        stats = sync_song_versions_to_server(
            muma_with(
                [
                    row('/mnt/music/EPs/Texcore/01.mp3', work_id=42, track_id=10, canonical_track_id=10),
                    row('/mnt/music/Soundcloud/rip.mp3', work_id=42, track_id=11, canonical_track_id=10),
                ]
            ),
            self.server,
        )
        self.assertEqual(stats['matched'], 1)
        self.assertEqual(self.stored(1)[1], 0)

    def test_a_file_the_server_does_not_have_costs_no_write(self):
        stats = sync_song_versions_to_server(
            muma_with([row('/mnt/music/EPs/Texcore/absent.mp3', work_id=7)]),
            self.server,
        )
        self.assertEqual((stats['considered'], stats['matched']), (1, 0))

    def test_a_chunk_that_agrees_opens_no_write_transaction(self):
        # The previous guard lived in the UPDATE's WHERE clause, and an UPDATE that matches
        # nothing still takes the write lock from the moment it runs until the commit. The
        # player waits one second for that lock and then aborts the request -- which is how
        # a rating from the app came back as a 500 while this job walked 285.000 rows.
        for i in range(3):
            self.add_track(i, f'/mnt/music/EPs/Texcore/{i}.mp3', work_id=40 + i, is_canonical=1, version_kind='radio')
        statements = []
        self.server.set_trace_callback(statements.append)
        sync_song_versions_to_server(
            muma_with(
                [row(f'/mnt/music/EPs/Texcore/{i}.mp3', work_id=40 + i, is_canonical=1, kind='radio') for i in range(3)]
            ),
            self.server,
        )
        self.server.set_trace_callback(None)
        writes = [s for s in statements if s.lstrip().upper().startswith(('UPDATE', 'BEGIN', 'INSERT'))]
        self.assertEqual(writes, [])

    def test_rows_that_disagree_are_written_in_short_batches(self):
        # One second is all the player waits. A hundred indexed UPDATEs commit well inside
        # it; a first pass over the whole library must not become one long transaction.
        for i in range(5):
            self.add_track(i, f'/mnt/music/Soundcloud/{i}.mp3', work_id=42, is_canonical=1)
        self.add_track(9, '/mnt/music/EPs/Texcore/01.mp3', work_id=42, is_canonical=1)
        server = FlakyServer(self.server, failures=0)
        with patch.object(sync_module, 'WRITE_BATCH', 2):
            stats = sync_song_versions_to_server(
                muma_with(
                    [row('/mnt/music/EPs/Texcore/01.mp3', work_id=42, track_id=10, canonical_track_id=10)]
                    + [
                        row(f'/mnt/music/Soundcloud/{i}.mp3', work_id=42, track_id=20 + i, canonical_track_id=10)
                        for i in range(5)
                    ]
                ),
                server,
            )
        self.assertEqual(stats['matched'], 5)
        self.assertEqual(server.commits, 3, 'five rows in batches of two is three transactions')
        self.assertEqual([self.stored(i)[1] for i in range(5)], [0] * 5)


def muma_in_chunks(*chunks):
    """A muma connection whose cursor yields each chunk in turn, like a real fetchmany."""
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    cursor.fetchmany.side_effect = [list(chunk) for chunk in chunks] + [[]]
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


class OneCanonicalPerWorkTest(SongVersionSyncTest):
    """Bug report 097: exactly one server row per work is canonical.

    On production 5,226 works had more than one canonical row -- every file of a multi-file
    canonical track was marked -- and 1,081 had none at all, because the server lacked the
    canonical track's file and every version it did have was marked 0. With canonical-only
    on (the app's default) the first showed a song twice and the second lost it entirely.
    """

    def canonical_ids(self):
        return [r[0] for r in self.server.execute('SELECT id FROM track WHERE is_canonical = 1 ORDER BY id')]

    def test_a_track_with_several_files_gets_one_canonical_row(self):
        # The FLAC and the MP3 of one release, one muma track: the lossless one is shown.
        self.add_track(1, '/mnt/music/EPs/Texcore/01.flac')
        self.add_track(2, '/mnt/music/EPs/Texcore/01.mp3')
        self.add_track(3, '/mnt/music/Soundcloud/rip.mp3')
        sync_song_versions_to_server(
            muma_with(
                [
                    row(
                        '/mnt/music/EPs/Texcore/01.flac',
                        work_id=42,
                        track_id=10,
                        canonical_track_id=10,
                        file_size=40_000_000,
                    ),
                    row('/mnt/music/EPs/Texcore/01.mp3', work_id=42, track_id=10, canonical_track_id=10),
                    row('/mnt/music/Soundcloud/rip.mp3', work_id=42, track_id=11, canonical_track_id=10),
                ]
            ),
            self.server,
        )
        self.assertEqual(self.canonical_ids(), [1])
        self.assertEqual(self.stored(2), (42, 0, '', 0))

    def test_the_storage_setting_shows_the_mp3_320_instead_of_the_flac(self):
        # docs/designs/song-versions/: the file LMS shows follows the same format order as the
        # ranking that chose the track, so prefer_lossless off picks the MP3 at 320.
        self.add_track(1, '/mnt/music/EPs/Texcore/01.flac')
        self.add_track(2, '/mnt/music/EPs/Texcore/01.mp3')
        files = [
            row('/mnt/music/EPs/Texcore/01.flac', work_id=42, track_id=10, canonical_track_id=10, file_size=40_000_000),
            row('/mnt/music/EPs/Texcore/01.mp3', work_id=42, track_id=10, canonical_track_id=10, file_size=12_000_000),
        ]
        sync_song_versions_to_server(muma_with(files), self.server, prefer_lossless=False)
        self.assertEqual(self.canonical_ids(), [2])
        sync_song_versions_to_server(muma_with(files), self.server, prefer_lossless=True)
        self.assertEqual(self.canonical_ids(), [1])

    def test_between_two_equal_files_the_higher_bitrate_then_the_newest_wins(self):
        self.add_track(1, '/mnt/music/EPs/a/01.mp3')
        self.add_track(2, '/mnt/music/EPs/b/01.mp3')
        self.add_track(3, '/mnt/music/EPs/c/01.mp3')
        sync_song_versions_to_server(
            muma_with(
                [
                    row(
                        '/mnt/music/EPs/a/01.mp3',
                        work_id=42,
                        track_id=10,
                        canonical_track_id=10,
                        media_id=1,
                        file_size=4_800_000,
                    ),
                    row(
                        '/mnt/music/EPs/b/01.mp3',
                        work_id=42,
                        track_id=10,
                        canonical_track_id=10,
                        media_id=2,
                        file_size=4_800_000,
                    ),
                    row(
                        '/mnt/music/EPs/c/01.mp3',
                        work_id=42,
                        track_id=10,
                        canonical_track_id=10,
                        media_id=3,
                        file_size=3_000_000,
                    ),
                ]
            ),
            self.server,
        )
        self.assertEqual(self.canonical_ids(), [2], '128 kbps twice beats 80 kbps; of the two the newer row')

    def test_the_scanners_own_row_beats_a_better_file_on_a_stale_row(self):
        # A row whose hash is not its path's is a leftover (bug report 093), not a better copy.
        self.add_track(1, '/mnt/music/EPs/a/01.flac')
        self.add_track(2, '/mnt/music/EPs/a/01.mp3')
        sync_song_versions_to_server(
            muma_with(
                [
                    row('/mnt/music/EPs/a/01.flac', work_id=42, track_id=10, canonical_track_id=10, own_row=0),
                    row('/mnt/music/EPs/a/01.mp3', work_id=42, track_id=10, canonical_track_id=10, own_row=1),
                ]
            ),
            self.server,
        )
        self.assertEqual(self.canonical_ids(), [2])

    def test_a_canonical_the_server_lacks_falls_back_to_the_best_version_it_has(self):
        # The canonical track's file is not in this server. Without the fallback both
        # remaining versions were 0 and the song disappeared from canonical-only lists.
        self.add_track(1, '/mnt/music/Soundcloud/rip.mp3')
        self.add_track(2, '/mnt/music/Youtube/x/extended.mp3')
        stats = sync_song_versions_to_server(
            muma_with(
                [
                    row(
                        '/mnt/music/EPs/Texcore/absent.flac', work_id=42, track_id=10, canonical_track_id=10, score=900
                    ),
                    row('/mnt/music/Soundcloud/rip.mp3', work_id=42, track_id=11, canonical_track_id=10, score=100),
                    row('/mnt/music/Youtube/x/extended.mp3', work_id=42, track_id=12, canonical_track_id=10, score=300),
                ]
            ),
            self.server,
        )
        self.assertEqual(self.canonical_ids(), [2], 'the higher-scored version the server has')
        self.assertEqual(stats['canonical_fallbacks'], 1)

    def test_a_work_without_a_named_canonical_still_gets_exactly_one(self):
        self.add_track(1, '/mnt/music/Soundcloud/a.mp3')
        self.add_track(2, '/mnt/music/Soundcloud/b.mp3')
        stats = sync_song_versions_to_server(
            muma_with(
                [
                    row('/mnt/music/Soundcloud/a.mp3', work_id=42, track_id=11, canonical_track_id=None, score=5),
                    row('/mnt/music/Soundcloud/b.mp3', work_id=42, track_id=10, canonical_track_id=None, score=5),
                ]
            ),
            self.server,
        )
        # Tie on score and file: the lower track id wins, so the choice never wanders.
        self.assertEqual(self.canonical_ids(), [2])
        self.assertEqual(stats['canonical_fallbacks'], 1)

    def test_a_work_split_across_chunks_is_settled_as_one(self):
        # Rows arrive in path order, so the canonical's file can come chunks after a sibling.
        self.add_track(1, '/mnt/music/A/extended.mp3')
        self.add_track(2, '/mnt/music/Z/radio.mp3')
        sync_song_versions_to_server(
            muma_in_chunks(
                [row('/mnt/music/A/extended.mp3', work_id=42, track_id=11, canonical_track_id=10)],
                [row('/mnt/music/Z/radio.mp3', work_id=42, track_id=10, canonical_track_id=10)],
            ),
            self.server,
        )
        self.assertEqual(self.canonical_ids(), [2])

    def test_two_media_rows_for_one_path_push_only_the_first(self):
        # Bug report 093's stale rows: the stale one points at a stub track in its own work,
        # and must not give the file a second answer.
        self.add_track(1, '/mnt/music/EPs/a/01.mp3')
        stats = sync_song_versions_to_server(
            muma_in_chunks(
                [row('/mnt/music/EPs/a/01.mp3', work_id=42, track_id=10, canonical_track_id=10)],
                [row('/mnt/music/EPs/a/01.mp3', work_id=77, track_id=99, canonical_track_id=-1, own_row=0)],
            ),
            self.server,
        )
        self.assertEqual(self.stored(1), (42, 1, '', 0))
        self.assertEqual(stats['duplicates_skipped'], 1)

    def test_an_ungrouped_track_keeps_every_file_visible(self):
        self.add_track(1, '/mnt/music/EPs/a/01.flac', is_canonical=0)
        self.add_track(2, '/mnt/music/EPs/a/01.mp3', is_canonical=0)
        sync_song_versions_to_server(
            muma_with(
                [
                    row('/mnt/music/EPs/a/01.flac', track_id=10),
                    row('/mnt/music/EPs/a/01.mp3', track_id=10),
                ]
            ),
            self.server,
        )
        self.assertEqual(self.canonical_ids(), [1, 2])

    def test_a_second_run_writes_nothing_and_takes_no_write_lock(self):
        for i, path in enumerate(
            ['/mnt/music/EPs/a/01.flac', '/mnt/music/EPs/a/01.mp3', '/mnt/music/Soundcloud/rip.mp3'], start=1
        ):
            self.add_track(i, path)

        def rows():
            return [
                row(
                    '/mnt/music/EPs/a/01.flac',
                    work_id=42,
                    track_id=10,
                    canonical_track_id=10,
                    media_id=1,
                    file_size=40_000_000,
                ),
                row('/mnt/music/EPs/a/01.mp3', work_id=42, track_id=10, canonical_track_id=10, media_id=2),
                row('/mnt/music/Soundcloud/rip.mp3', work_id=42, track_id=11, canonical_track_id=10, media_id=3),
                row('/mnt/music/EPs/gone.flac', work_id=43, track_id=12, canonical_track_id=12, media_id=4),
            ]

        first = sync_song_versions_to_server(muma_with(rows()), self.server)
        statements = []
        self.server.set_trace_callback(statements.append)
        second = sync_song_versions_to_server(muma_with(rows()), self.server)
        self.server.set_trace_callback(None)

        self.assertEqual(first['matched'], 3)
        self.assertEqual(second['matched'], 0)
        writes = [s for s in statements if s.lstrip().upper().startswith(('UPDATE', 'BEGIN', 'INSERT'))]
        self.assertEqual(writes, [])

    def test_the_update_leaves_a_row_that_already_agrees_alone(self):
        # Compare-before-write in the statement itself: a row another writer settled between
        # the read and the write counts as nothing changed.
        self.add_track(1, '/mnt/music/EPs/a/01.mp3', work_id=42, is_canonical=1)
        cursor = self.server.cursor()
        cursor.execute(sync_module._UPDATE, (42, 1, '', 0, 1))
        self.assertEqual(cursor.rowcount, 0)
        cursor.execute(sync_module._UPDATE, (42, 0, '', 0, 1))
        self.assertEqual(cursor.rowcount, 1)


if __name__ == '__main__':
    unittest.main()
