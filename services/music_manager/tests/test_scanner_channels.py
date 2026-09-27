"""What the scanner does with a file that arrived through a platform.

The scanner stores a song's publisher as a label. SoundCloud, YouTube and Telegram arrive in that
same tag and are not labels, which is how they became the three largest entries in the label chart.
These tests pin down both halves of the fix: the platform no longer becomes a label, and the account
it came from is recorded as a channel instead.
"""

import unittest

from services.music_manager.routers.scanner import ScannerManager
from services.music_manager.tests.scripted_cursor import ScriptedCursor


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


class Publisher:
    """Just the publisher of a file, which is all _resolve_label_id reads from the song."""

    def __init__(self, value):
        self.value = value

    def publisher(self):
        return self.value


class ChannelLabelTest(unittest.TestCase):
    """docs/designs/channel-links: a platform file carries the label its channel is linked to, and no other."""

    PATH = '/mnt/music/Soundcloud/TRAXTORM/track.mp3'
    LINKED = ('JOIN library_labels l ON l.id = c.label_id', ('soundcloud', 'traxtorm'), {'id': 3, 'name': 'Traxtorm'})

    def resolve(self, publisher, rules=(LINKED,)):
        cursor = ScriptedCursor(rules=list(rules))
        return manager()._resolve_label_id(cursor, Publisher(publisher), self.PATH), cursor

    def test_the_linked_label_is_accepted_in_any_capitals(self):
        found, cursor = self.resolve('TRAXTORM')
        self.assertEqual(found, 3)
        # The label exists already (the link points at it); nothing is inserted.
        self.assertFalse([sql for sql, _p in cursor.executed if sql.startswith('INSERT')])

    def test_any_other_label_on_a_platform_file_is_still_refused(self):
        self.assertIsNone(self.resolve('Dirty Workz')[0])

    def test_the_platform_itself_asks_nothing(self):
        found, cursor = self.resolve('Soundcloud')
        self.assertIsNone(found)
        self.assertEqual(cursor.executed, [])

    def test_an_unlinked_channel_carries_no_label(self):
        self.assertIsNone(self.resolve('Traxtorm', rules=())[0])


if __name__ == '__main__':
    unittest.main()
