"""What the scanner does with a file that arrived through a platform.

The scanner stores a song's publisher as a label. SoundCloud, YouTube and Telegram arrive in that
same tag and are not labels, which is how they became the three largest entries in the label chart.
These tests pin down both halves of the fix: the platform no longer becomes a label, and the account
it came from is recorded as a channel instead.
"""

import unittest

import pytest

from services.music_manager.routers.scanner import ScannerManager
from services.music_manager.tests.scripted_cursor import ScriptedCursor

pytestmark = pytest.mark.mock_base('mutagen', 'markdown', 'pymysql', 'dbutils')


def manager(music_path='/mnt/music'):
    """A ScannerManager with a known music root and nothing else touched."""
    scanner = ScannerManager()
    scanner.music_path = music_path
    return scanner


class ResolveChannelTest(unittest.TestCase):
    def test_a_soundcloud_file_creates_its_channel(self):
        cursor = ScriptedCursor(rules=[('SELECT id FROM channels', None, {'id': 7})])
        found = manager()._resolve_channel_id(cursor, '/mnt/music/Soundcloud/Dirty Workz/track.mp3')

        self.assertEqual(found, 7)
        insert = next(sql for sql, _p in cursor.executed if 'INSERT IGNORE INTO channels' in sql)
        params = next(p for sql, p in cursor.executed if 'INSERT IGNORE INTO channels' in sql)
        self.assertIn('channels', insert)
        self.assertEqual(params, ('soundcloud', 'Dirty Workz', 'dirty workz'))

    def test_a_label_release_creates_no_channel(self):
        cursor = ScriptedCursor(rules=[('SELECT id FROM channels', None, {'id': 7})])
        found = manager()._resolve_channel_id(cursor, '/mnt/music/EPs/Dirty Workz/DWX123 Release/track.mp3')

        self.assertIsNone(found)
        self.assertEqual([sql for sql, _p in cursor.executed if 'channels' in sql], [])

    def test_two_platforms_are_two_channels_even_under_one_name(self):
        # Deliberately not merged: which platform a file came from stays answerable. They converge
        # later through the label a channel points at, not by becoming one row.
        platforms = []
        for path in ('/mnt/music/Soundcloud/Dirty Workz/a.mp3', '/mnt/music/Youtube/Dirty Workz/b.m4a'):
            cursor = ScriptedCursor(rules=[('SELECT id FROM channels', None, {'id': 1})])
            manager()._resolve_channel_id(cursor, path)
            params = next(p for sql, p in cursor.executed if 'INSERT IGNORE INTO channels' in sql)
            platforms.append(params[0])

        self.assertEqual(platforms, ['soundcloud', 'youtube'])

    def test_a_channel_that_cannot_be_read_back_is_not_linked(self):
        # No rule for the SELECT, so it reads as "no such row" -- the caller must get None rather
        # than an exception or a bogus id.
        cursor = ScriptedCursor()
        self.assertIsNone(manager()._resolve_channel_id(cursor, '/mnt/music/Soundcloud/Rejecta/track.mp3'))


if __name__ == '__main__':
    unittest.main()
