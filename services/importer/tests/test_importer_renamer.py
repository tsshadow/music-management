import errno
import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from services.common.Helpers import Quarantine as quarantine_module
from services.importer import renamer
from services.importer.renamer import Renamer, find_cat_id, has_numbers, is_parsed


class FolderNameHelpersTest(unittest.TestCase):
    def test_has_numbers_spots_a_digit_anywhere(self):
        self.assertTrue(has_numbers('SCAN123'))
        self.assertTrue(has_numbers('a1'))
        self.assertFalse(has_numbers('Scantraxx'))
        self.assertFalse(has_numbers(''))

    def test_a_folder_is_considered_parsed_once_it_carries_the_separator(self):
        self.assertTrue(is_parsed('SCAN123 - Some Release'))
        self.assertFalse(is_parsed('Some Release'))

    def test_the_last_bracketed_group_with_digits_becomes_the_catalog_number(self):
        self.assertEqual(find_cat_id('Some Release (SCAN123)'), 'SCAN123 - Some Release (SCAN123)')

    def test_brackets_are_searched_from_the_back(self):
        self.assertEqual(find_cat_id('Release (Remix) (CAT99)'), 'CAT99 - Release (Remix) (CAT99)')

    def test_a_folder_without_brackets_only_gets_the_separator(self):
        self.assertEqual(find_cat_id('Some Release'), ' - Some Release')

    def test_brackets_without_digits_do_not_count_as_a_catalog_number(self):
        self.assertEqual(find_cat_id('Release (Extended Mix)'), ' - Release (Extended Mix)')


class RenamerTest(unittest.TestCase):
    def setUp(self):
        settings = MagicMock(import_folder_path='/import', delimiter='/')
        patcher = patch.object(renamer, 'Settings', return_value=settings)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.renamer = Renamer()

    def run_with(self, entries, dry_run=False):
        with (
            patch.object(renamer, 'listdir', return_value=entries),
            patch.object(renamer, 'isfile', return_value=False),
            patch.object(renamer.os, 'rename') as rename,
        ):
            self.renamer.run(dry_run=dry_run)
        return rename

    def test_an_unparsed_folder_is_renamed_with_its_catalog_number(self):
        rename = self.run_with(['Some Release (SCAN123)'])
        rename.assert_called_once_with('/import/Some Release (SCAN123)', '/import/SCAN123 - Some Release (SCAN123)')

    def test_an_already_parsed_folder_is_left_alone(self):
        rename = self.run_with(['SCAN123 - Some Release'])
        rename.assert_not_called()

    def test_synology_metadata_folders_are_skipped(self):
        rename = self.run_with(['@eaDir'])
        rename.assert_not_called()

    def test_a_dry_run_only_reports_what_it_would_do(self):
        rename = self.run_with(['Some Release (SCAN123)'], dry_run=True)
        rename.assert_not_called()

    def test_plain_files_are_not_considered(self):
        with (
            patch.object(renamer, 'listdir', return_value=['archive.zip']),
            patch.object(renamer, 'isfile', return_value=True),
            patch.object(renamer.os, 'rename') as rename,
        ):
            self.renamer.run()
        rename.assert_not_called()

    def test_an_unexpected_rename_failure_does_not_stop_the_run(self):
        with (
            patch.object(renamer, 'listdir', return_value=['A (1)', 'B (2)']),
            patch.object(renamer, 'isfile', return_value=False),
            patch.object(renamer.os, 'rename', side_effect=OSError('disk error')) as rename,
        ):
            self.renamer.run()
        self.assertEqual(rename.call_count, 2)


class RenamerCollisionTest(unittest.TestCase):
    """A rename onto an existing folder, against a real filesystem.

    Mocking `os.rename` cannot express "the target holds the same files", which is the
    whole question here, so these build the two directories for real -- and they are the
    only way to reproduce ENOTEMPTY, which is what a non-empty target actually raises.
    """

    UNPARSED = 'Some Release (SCAN123)'
    RENAMED = 'SCAN123 - Some Release (SCAN123)'

    def setUp(self):
        self.tmp = self.enterContext(TemporaryDirectory())
        # A real quarantine root, because a collision no longer deletes the duplicate --
        # it moves it. Without somewhere to move it to, the renamer leaves the folder
        # where it is, which is the safe failure and not what these assert.
        self.quarantine = self.enterContext(TemporaryDirectory())
        settings = MagicMock(
            import_folder_path=self.tmp,
            delimiter='/',
            quarantine_folder_path=self.quarantine,
            quarantine_retention_days=30,
        )
        for module in (renamer, quarantine_module):
            patcher = patch.object(module, 'Settings', return_value=settings)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.renamer = Renamer()

    def parked(self, folder):
        """Whether the folder ended up in quarantine rather than being deleted."""
        return any(folder in dirs for _, dirs, _files in os.walk(self.quarantine))

    def make_release(self, folder, files):
        path = os.path.join(self.tmp, folder)
        os.makedirs(path, exist_ok=True)
        for name, content in files.items():
            full = os.path.join(path, name)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'w') as handle:
                handle.write(content)
        return path

    def exists(self, folder):
        return os.path.isdir(os.path.join(self.tmp, folder))

    def test_a_second_download_of_a_release_that_is_already_renamed_is_parked(self):
        self.make_release(self.UNPARSED, {'01-track.mp3': 'aaa', '00-release.nfo': 'bb'})
        self.make_release(self.RENAMED, {'01-track.mp3': 'aaa', '00-release.nfo': 'bb'})
        self.renamer.run()
        self.assertFalse(self.exists(self.UNPARSED))
        self.assertTrue(self.parked(self.UNPARSED))
        self.assertTrue(self.exists(self.RENAMED))

    def test_a_duplicate_removal_is_logged_as_a_warning_not_as_info(self):
        self.make_release(self.UNPARSED, {'01-track.mp3': 'aaa'})
        self.make_release(self.RENAMED, {'01-track.mp3': 'aaa'})
        with self.assertLogs(level='WARNING') as logs:
            self.renamer.run()
        self.assertIn('Conflict:', '\n'.join(logs.output))

    def test_a_colliding_folder_whose_contents_differ_is_left_alone(self):
        self.make_release(self.UNPARSED, {'01-track.mp3': 'a longer rip'})
        self.make_release(self.RENAMED, {'01-track.mp3': 'aaa'})
        self.renamer.run()
        self.assertTrue(self.exists(self.UNPARSED))
        self.assertTrue(self.exists(self.RENAMED))

    def test_a_colliding_folder_with_an_extra_file_is_left_alone(self):
        self.make_release(self.UNPARSED, {'01-track.mp3': 'aaa', '02-bonus.mp3': 'bbb'})
        self.make_release(self.RENAMED, {'01-track.mp3': 'aaa'})
        self.renamer.run()
        self.assertTrue(self.exists(self.UNPARSED))

    def test_a_collision_says_in_the_log_why_it_left_both_folders(self):
        self.make_release(self.UNPARSED, {'01-track.mp3': 'a longer rip'})
        self.make_release(self.RENAMED, {'01-track.mp3': 'aaa'})
        with self.assertLogs(level='WARNING') as logs:
            self.renamer.run()
        message = '\n'.join(logs.output)
        self.assertIn('differ', message)
        self.assertIn('manual intervention', message)

    def test_a_collision_reported_as_file_exists_is_handled_the_same_way(self):
        self.make_release(self.UNPARSED, {'01-track.mp3': 'aaa'})
        self.make_release(self.RENAMED, {'01-track.mp3': 'aaa'})
        with patch.object(renamer.os, 'rename', side_effect=FileExistsError(errno.EEXIST, 'File exists')):
            self.renamer.run()
        self.assertFalse(self.exists(self.UNPARSED))
        self.assertTrue(self.parked(self.UNPARSED))
        self.assertTrue(self.parked(self.UNPARSED))

    def test_synology_thumbnail_folders_do_not_make_two_copies_look_different(self):
        self.make_release(self.UNPARSED, {'01-track.mp3': 'aaa'})
        self.make_release(self.RENAMED, {'01-track.mp3': 'aaa', os.path.join('@eaDir', 'thumb.jpg'): 'junk'})
        self.renamer.run()
        self.assertFalse(self.exists(self.UNPARSED))
        self.assertTrue(self.parked(self.UNPARSED))

    def test_a_rename_failure_that_is_not_a_collision_is_logged_and_the_run_continues(self):
        self.make_release('A (1)', {'01-track.mp3': 'aaa'})
        self.make_release('B (2)', {'01-track.mp3': 'aaa'})
        with patch.object(renamer.os, 'rename', side_effect=OSError(errno.EACCES, 'denied')) as rename:
            self.renamer.run()
        self.assertEqual(rename.call_count, 2)
        self.assertTrue(self.exists('A (1)'))
        self.assertTrue(self.exists('B (2)'))

    def test_an_unreadable_colliding_folder_is_left_alone(self):
        self.make_release(self.UNPARSED, {'01-track.mp3': 'aaa'})
        self.make_release(self.RENAMED, {'01-track.mp3': 'aaa'})
        with patch.object(renamer.os, 'walk', side_effect=PermissionError('denied')):
            self.renamer.run()
        self.assertTrue(self.exists(self.UNPARSED))
        self.assertTrue(self.exists(self.RENAMED))


if __name__ == '__main__':
    unittest.main()
