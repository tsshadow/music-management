import os
import shutil
import sqlite3
import tempfile
import unittest

from services.tests.mock_base import setup_mocks

setup_mocks()

from services.downloader.cookie_profile import snapshot_cookie_profile


class CookieProfileSnapshotTest(unittest.TestCase):
    """yt-dlp copies cookies.sqlite and nothing else.

    Firefox runs in write-ahead-log mode, so a cookie it wrote minutes ago can
    still live only in cookies.sqlite-wal. yt-dlp's copy silently misses it and
    the downloader authenticates with a stale jar. Snapshotting checkpoints the
    log first, so the file yt-dlp copies is complete.
    """

    def setUp(self):
        self.profile = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.profile, True)
        self.database = os.path.join(self.profile, 'cookies.sqlite')
        self.connection = sqlite3.connect(self.database)
        self.addCleanup(self.connection.close)
        self.connection.execute('PRAGMA journal_mode=WAL')
        self.connection.execute('CREATE TABLE moz_cookies (name TEXT, value TEXT)')
        self.connection.commit()
        # Firefox does checkpoint eventually, so the schema and older cookies have
        # long since landed in the database file. What a copy misses is whatever was
        # written since -- which is exactly where the freshest cookies are.
        self.connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        self.connection.commit()

    def _write_cookie(self, name, value):
        self.connection.execute('INSERT INTO moz_cookies VALUES (?, ?)', (name, value))
        self.connection.commit()

    def _names_in(self, database_path):
        """Read a bare copy of the database, the way yt-dlp does."""
        target = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, target, True)
        copy = os.path.join(target, 'temporary.sqlite')
        shutil.copy(database_path, copy)
        connection = sqlite3.connect(copy)
        try:
            return sorted(row[0] for row in connection.execute('SELECT name FROM moz_cookies'))
        finally:
            connection.close()

    def test_the_bare_copy_really_does_miss_the_unflushed_cookie(self):
        """Guards the premise: without this, the fix below would prove nothing."""
        self._write_cookie('datadome', 'fresh')
        self.assertEqual(self._names_in(self.database), [])

    def test_the_snapshot_sees_the_unflushed_cookie(self):
        self._write_cookie('datadome', 'fresh')
        snapshot = snapshot_cookie_profile(self.profile)
        self.addCleanup(shutil.rmtree, snapshot, True)
        self.assertEqual(self._names_in(os.path.join(snapshot, 'cookies.sqlite')), ['datadome'])

    def test_the_snapshot_sees_every_cookie(self):
        self._write_cookie('datadome', 'fresh')
        self._write_cookie('oauth_token', 'secret')
        snapshot = snapshot_cookie_profile(self.profile)
        self.addCleanup(shutil.rmtree, snapshot, True)
        self.assertEqual(self._names_in(os.path.join(snapshot, 'cookies.sqlite')), ['datadome', 'oauth_token'])

    def test_the_live_profile_is_left_alone(self):
        self._write_cookie('datadome', 'fresh')
        before = sorted(os.listdir(self.profile))
        snapshot = snapshot_cookie_profile(self.profile)
        self.addCleanup(shutil.rmtree, snapshot, True)
        self.assertEqual(sorted(os.listdir(self.profile)), before)

    def test_a_profile_without_a_cookie_database_is_reported_as_missing(self):
        empty = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, empty, True)
        self.assertIsNone(snapshot_cookie_profile(empty))

    def test_a_profile_that_does_not_exist_is_reported_as_missing(self):
        self.assertIsNone(snapshot_cookie_profile('/nonexistent/profile'))


if __name__ == '__main__':
    unittest.main()
