"""Moving the portrait rows muma wrote under its own mount onto LMS's spelling (bug report 138).

Against a real SQLite file in WAL mode, with a second connection standing in for LMS's scanner
where the lock matters, because the claims are about what ends up in LMS's tables: which rows
are renamed, which artists are moved, what is left for LMS, and that a busy server loses nothing.
"""

import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from services.music_manager import lms_portrait_paths
from services.music_manager.lms_portrait_paths import repair_portrait_paths

SCHEMA = """
CREATE TABLE image (id INTEGER PRIMARY KEY, version INTEGER, absolute_file_path TEXT, stem TEXT);
CREATE INDEX image_path_idx ON image(absolute_file_path);
CREATE TABLE artwork (id INTEGER PRIMARY KEY, version INTEGER, image_id INTEGER);
CREATE TABLE artist (id INTEGER PRIMARY KEY, name TEXT, preferred_artwork_id INTEGER);
"""


class RepairPortraitPathsTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.mkdtemp()
        self.path = os.path.join(directory, 'lms.db')
        setup = sqlite3.connect(self.path)
        setup.execute('PRAGMA journal_mode=WAL')
        setup.executescript(SCHEMA)
        setup.close()
        self.lms = sqlite3.connect(self.path, isolation_level=None)
        self.ours = sqlite3.connect(self.path)
        self.addCleanup(self.lms.close)
        self.addCleanup(self.ours.close)
        # Ten seconds of patience is right on production and wrong in a test.
        patcher = patch.object(lms_portrait_paths, 'BUSY_TIMEOUT_STATEMENT', 'PRAGMA busy_timeout = 50')
        patcher.start()
        self.addCleanup(patcher.stop)

    def given(self, sql):
        self.lms.executescript(sql)

    def path_of(self, image_id):
        return self.lms.execute('SELECT absolute_file_path FROM image WHERE id = ?', (image_id,)).fetchone()[0]

    def artwork_of(self, artist_id):
        return self.lms.execute('SELECT preferred_artwork_id FROM artist WHERE id = ?', (artist_id,)).fetchone()[0]

    def repair(self):
        return repair_portrait_paths(self.ours, 'stable')

    def test_a_row_lms_has_no_twin_for_is_renamed_in_place(self):
        # Same image id, same artwork, same artist pointer: nothing a client holds changes.
        self.given(
            """
            INSERT INTO image VALUES (1, 1, '/mnt/music/artists/9/spotify-abc.jpg', 'spotify-abc');
            INSERT INTO artwork VALUES (10, 1, 1);
            INSERT INTO artist VALUES (100, 'Angerfist', 10);
            """
        )
        stats = self.repair()
        self.assertEqual(self.path_of(1), '/music/artists/9/spotify-abc.jpg')
        self.assertEqual(self.artwork_of(100), 10)
        self.assertEqual(stats['renamed'], 1)
        self.assertEqual(stats['left_for_lms'], 0)

    def test_an_artist_on_a_file_lms_indexed_itself_is_moved_onto_lms_row(self):
        # Renaming would give one path two rows; LMS's Image::find(path) expects one.
        self.given(
            """
            INSERT INTO image VALUES (1, 1, '/mnt/music/artists/9/spotify-abc.jpg', 'spotify-abc');
            INSERT INTO image VALUES (2, 1, '/music/artists/9/spotify-abc.jpg', 'spotify-abc');
            INSERT INTO artwork VALUES (10, 1, 1), (20, 1, 2);
            INSERT INTO artist VALUES (100, 'Angerfist', 10);
            """
        )
        stats = self.repair()
        self.assertEqual(self.artwork_of(100), 20)
        self.assertEqual(self.path_of(1), '/mnt/music/artists/9/spotify-abc.jpg', 'left for LMS to remove')
        self.assertEqual(
            self.lms.execute("SELECT count(*) FROM image WHERE absolute_file_path LIKE '/music/%'").fetchone()[0], 1
        )
        self.assertEqual(stats, {'renamed': 0, 'artists_moved': 1, 'left_for_lms': 1, 'deferred': False})

    def test_two_old_rows_for_one_file_do_not_both_take_its_path(self):
        self.given(
            """
            INSERT INTO image VALUES (1, 1, '/mnt/music/artists/9/a.jpg', 'a'), (2, 1, '/mnt/music/artists/9/a.jpg', 'a');
            """
        )
        self.repair()
        self.assertEqual(
            self.lms.execute(
                "SELECT count(*) FROM image WHERE absolute_file_path = '/music/artists/9/a.jpg'"
            ).fetchone()[0],
            1,
        )

    def test_a_second_pass_writes_nothing(self):
        self.given(
            """
            INSERT INTO image VALUES (1, 1, '/mnt/music/artists/9/a.jpg', 'a'), (2, 1, '/music/artists/8/b.jpg', 'b'),
                                     (3, 1, '/mnt/music/artists/8/b.jpg', 'b');
            INSERT INTO artwork VALUES (10, 1, 1), (20, 1, 2), (30, 1, 3);
            INSERT INTO artist VALUES (100, 'A', 10), (200, 'B', 30);
            """
        )
        self.repair()
        with patch.object(lms_portrait_paths, '_write') as write:
            stats = self.repair()
        write.assert_not_called()
        self.assertEqual(stats['renamed'] + stats['artists_moved'], 0)
        self.assertEqual(stats['left_for_lms'], 1, 'the old twin of b.jpg waits for LMS')

    def test_rows_already_under_the_server_root_are_not_touched(self):
        self.given("INSERT INTO image VALUES (1, 1, '/music/EPs/x/cover.jpg', 'cover');")
        with patch.object(lms_portrait_paths, '_write') as write:
            stats = self.repair()
        write.assert_not_called()
        self.assertEqual(stats['left_for_lms'], 0)

    def test_a_busy_server_ends_the_pass_and_loses_nothing(self):
        self.given("INSERT INTO image VALUES (1, 1, '/mnt/music/artists/9/a.jpg', 'a');")
        self.lms.execute('BEGIN IMMEDIATE')
        stats = self.repair()
        self.assertTrue(stats['deferred'])
        self.assertFalse(self.ours.in_transaction, 'a refused batch leaves no transaction behind')
        self.lms.execute('COMMIT')
        self.assertEqual(self.path_of(1), '/mnt/music/artists/9/a.jpg')
        self.assertEqual(self.repair()['renamed'], 1)
        self.assertEqual(self.path_of(1), '/music/artists/9/a.jpg')

    def test_batches_are_short(self):
        self.given(
            ''.join(f"INSERT INTO image VALUES ({i}, 1, '/mnt/music/artists/{i}/a.jpg', 'a');" for i in range(1, 251))
        )
        with patch.object(lms_portrait_paths, '_write', wraps=lms_portrait_paths._write) as write:
            stats = self.repair()
        self.assertEqual(stats['renamed'], 250)
        self.assertEqual(write.call_count, 3)
        self.assertTrue(all(len(call.args[2]) <= lms_portrait_paths.WRITE_BATCH for call in write.call_args_list))

    def test_a_non_lock_error_is_raised(self):
        # Waiting on a broken schema helps nobody and would bury the real message.
        broken = sqlite3.connect(':memory:')
        self.addCleanup(broken.close)
        with self.assertRaises(sqlite3.OperationalError):
            lms_portrait_paths._write(broken, broken.cursor(), [('/music/a', 1)], [])


if __name__ == '__main__':
    unittest.main()
