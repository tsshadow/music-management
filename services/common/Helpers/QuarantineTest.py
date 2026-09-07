"""What the quarantine does with a file, and what it refuses to do.

Against a real filesystem, because the two things worth pinning are both about paths:
where a file ends up, and which configured values are not paths at all. A mocked
`os.makedirs` cannot show that a stubbed setting creates a directory named
`<MagicMock ...>` in the working directory, which is exactly what happened.
"""

import os
import unittest
from datetime import date, timedelta
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from services.common.Helpers import Quarantine


class QuarantineTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext(TemporaryDirectory())
        self.root = os.path.join(self.tmp, 'quarantine')
        self.music = os.path.join(self.tmp, 'music')
        os.makedirs(self.music)
        self.configure(quarantine_folder_path=self.root)

    def configure(self, **values):
        defaults = {'music_folder_path': self.music, 'quarantine_retention_days': 30}
        settings = MagicMock(**{**defaults, **values})
        patcher = patch.object(Quarantine, 'Settings', return_value=settings)
        patcher.start()
        self.addCleanup(patcher.stop)

    def make_file(self, name='track.m4a', content='audio'):
        path = os.path.join(self.music, name)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(content)
        return path

    def day_folder(self, day=None):
        return os.path.join(self.root, (day or date.today()).strftime('%Y-%m-%d'))


class PutTest(QuarantineTestCase):
    def test_a_file_is_moved_under_todays_folder_and_its_category(self):
        path = self.make_file()

        target = Quarantine.put(path, Quarantine.UNREADABLE_FILE)

        self.assertFalse(os.path.exists(path))
        self.assertTrue(os.path.exists(target))
        self.assertEqual(os.path.join(self.day_folder(), Quarantine.UNREADABLE_FILE, 'track.m4a'), target)

    def test_a_folder_is_moved_whole(self):
        folder = os.path.join(self.music, 'SCAN123 - Release')
        os.makedirs(folder)
        with open(os.path.join(folder, '01.mp3'), 'w', encoding='utf-8') as handle:
            handle.write('audio')

        target = Quarantine.put(folder, Quarantine.DUPLICATE_RELEASE)

        self.assertFalse(os.path.exists(folder))
        self.assertTrue(os.path.exists(os.path.join(target, '01.mp3')))

    def test_a_second_file_of_the_same_name_on_the_same_day_does_not_overwrite_the_first(self):
        """Two releases with one name park together more often than it sounds -- that is
        exactly the case the mover calls a duplicate."""
        first = Quarantine.put(self.make_file(content='first'), Quarantine.DUPLICATE_RELEASE)
        second = Quarantine.put(self.make_file(content='second'), Quarantine.DUPLICATE_RELEASE)

        self.assertNotEqual(first, second)
        with open(first, encoding='utf-8') as handle:
            self.assertEqual('first', handle.read())

    def test_a_path_that_is_not_there_is_not_an_error(self):
        self.assertIsNone(Quarantine.put(os.path.join(self.music, 'gone.mp3'), Quarantine.UNREADABLE_FILE))

    def test_a_failed_move_answers_none_and_leaves_the_file(self):
        """Every caller reads None as "your data is still where it was" and stops there,
        rather than falling back to the delete this replaced."""
        path = self.make_file()
        with patch.object(Quarantine.shutil, 'move', side_effect=OSError('read-only')):
            self.assertIsNone(Quarantine.put(path, Quarantine.UNREADABLE_FILE))
        self.assertTrue(os.path.exists(path))


class RootTest(QuarantineTestCase):
    def test_an_unset_folder_falls_back_to_a_hidden_folder_beside_the_music_root(self):
        self.configure(quarantine_folder_path='')
        self.assertEqual(os.path.join(self.music, '.quarantine'), Quarantine.root())

    def test_a_setting_that_is_not_a_string_is_refused(self):
        """A stubbed setting hands back an object whose str() is `<MagicMock ...>`, and
        os.makedirs will happily create a directory by that name. Four of those were
        created in the repository root before this guard existed."""
        self.configure(quarantine_folder_path=MagicMock())
        self.assertEqual(os.path.join(self.music, '.quarantine'), Quarantine.root())

    def test_a_relative_path_is_refused(self):
        """It would put the quarantine wherever the process happens to be running."""
        self.configure(quarantine_folder_path='quarantine')
        self.assertEqual(os.path.join(self.music, '.quarantine'), Quarantine.root())

    def test_no_usable_path_at_all_answers_none(self):
        settings = MagicMock(music_folder_path='', quarantine_folder_path='')
        with patch.object(Quarantine, 'Settings', return_value=settings):
            self.assertIsNone(Quarantine.root())
            self.assertIsNone(Quarantine.put('/tmp', Quarantine.UNREADABLE_FILE))


class SweepTest(QuarantineTestCase):
    def make_day(self, days_ago):
        folder = self.day_folder(date.today() - timedelta(days=days_ago))
        os.makedirs(folder, exist_ok=True)
        return folder

    def test_a_folder_past_the_retention_window_is_removed(self):
        old = self.make_day(31)

        self.assertEqual(1, Quarantine.sweep())

        self.assertFalse(os.path.exists(old))

    def test_a_folder_inside_the_window_is_kept(self):
        recent = self.make_day(1)

        Quarantine.sweep()

        self.assertTrue(os.path.exists(recent))

    def test_something_a_person_put_here_by_hand_is_left_alone(self):
        mine = os.path.join(self.root, 'keep-this')
        os.makedirs(mine)

        Quarantine.sweep()

        self.assertTrue(os.path.exists(mine))

    def test_a_retention_of_zero_does_not_sweep_what_was_parked_seconds_ago(self):
        """Zero would turn the sweep back into the delete this module replaced."""
        self.configure(quarantine_folder_path=self.root, quarantine_retention_days=0)
        today = self.make_day(0)

        Quarantine.sweep()

        self.assertTrue(os.path.exists(today))

    def test_a_root_that_does_not_exist_yet_sweeps_nothing(self):
        self.assertEqual(0, Quarantine.sweep())


if __name__ == '__main__':
    unittest.main()
