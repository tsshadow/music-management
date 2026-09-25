"""Tests for lms_schema: stale lms.db files are dropped from lms_db_targets(), warned about once."""

import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from services.music_manager import lms_schema  # noqa: E402
from services.music_manager.routers import users as users_router  # noqa: E402


def make_db(path, tables):
    """Create an SQLite file at `path` holding the given empty tables."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    for table in tables:
        conn.execute(f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY)')
    conn.commit()
    conn.close()
    return path


class LmsSchemaTest(unittest.TestCase):
    """usable_lms_targets keeps real LMS databases and drops files without the core tables."""

    def setUp(self):
        lms_schema._warned_paths.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_missing_tables_names_what_is_absent(self):
        conn = sqlite3.connect(':memory:')
        conn.execute('CREATE TABLE listen (id INTEGER)')
        try:
            self.assertEqual(lms_schema.missing_lms_tables(conn), {'user', 'track'})
        finally:
            conn.close()

    def test_lms_db_targets_drops_a_stale_file_and_warns_once_across_calls(self):
        """Production's alpha/lms.db: schema 114, no `user` table, no server behind it."""
        good = make_db(os.path.join(self.tmp.name, 'stable', 'lms.db'), ['listen', 'user', 'track'])
        make_db(os.path.join(self.tmp.name, 'alpha', 'lms.db'), ['listen', 'track', 'user_starred_artists'])
        env = {'MUMA_SERVER_DB_ROOT': self.tmp.name, 'MUMA_SERVER_DB_PATH': '', 'LMS_DB_PATH': ''}
        with patch.dict(os.environ, env), self.assertLogs('music-manager.lms-schema', level='WARNING') as logs:
            first = users_router.lms_db_targets()
            second = users_router.lms_db_targets()
        self.assertEqual(first, [(good, 'server-stable')])
        self.assertEqual(second, first)
        self.assertEqual(len(logs.output), 1)
        self.assertIn('alpha', logs.output[0])
        self.assertIn('user', logs.output[0])

    def test_every_complete_database_is_kept_without_a_warning(self):
        a = make_db(os.path.join(self.tmp.name, 'a.db'), ['listen', 'user', 'track'])
        b = make_db(os.path.join(self.tmp.name, 'b.db'), ['listen', 'user', 'track', 'extra'])
        with self.assertNoLogs('music-manager.lms-schema', level='WARNING'):
            self.assertEqual(lms_schema.usable_lms_targets([(a, 'a'), (b, 'b')]), [(a, 'a'), (b, 'b')])

    def test_an_unreadable_file_is_kept_for_the_consumer_to_handle(self):
        """A missing or locked file is transient; only a readable file lacking a table is dropped."""
        gone = os.path.join(self.tmp.name, 'nowhere', 'lms.db')
        self.assertEqual(lms_schema.usable_lms_targets([(gone, 'x')]), [(gone, 'x')])

    def test_a_file_that_gains_the_schema_is_picked_up_later(self):
        path = make_db(os.path.join(self.tmp.name, 'late.db'), ['listen'])
        with self.assertLogs('music-manager.lms-schema', level='WARNING'):
            self.assertEqual(lms_schema.usable_lms_targets([(path, 'late')]), [])
        make_db(path, ['user', 'track'])
        self.assertEqual(lms_schema.usable_lms_targets([(path, 'late')]), [(path, 'late')])


if __name__ == '__main__':
    unittest.main()
