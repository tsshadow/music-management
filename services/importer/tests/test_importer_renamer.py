import unittest
from unittest.mock import MagicMock, patch

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
        with patch.object(renamer, 'listdir', return_value=entries), \
             patch.object(renamer, 'isfile', return_value=False), \
             patch.object(renamer.os, 'rename') as rename:
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
        with patch.object(renamer, 'listdir', return_value=['archive.zip']), \
             patch.object(renamer, 'isfile', return_value=True), \
             patch.object(renamer.os, 'rename') as rename:
            self.renamer.run()
        rename.assert_not_called()

    def test_a_clashing_target_makes_the_source_folder_go_away(self):
        with patch.object(renamer, 'listdir', return_value=['Some Release (SCAN123)']), \
             patch.object(renamer, 'isfile', return_value=False), \
             patch.object(renamer.os, 'rename', side_effect=FileExistsError), \
             patch.object(renamer.shutil, 'rmtree') as rmtree:
            self.renamer.run()
        rmtree.assert_called_once_with('/import/Some Release (SCAN123)')

    def test_a_clashing_target_that_cannot_be_cleaned_up_does_not_stop_the_run(self):
        with patch.object(renamer, 'listdir', return_value=['A (1)', 'B (2)']), \
             patch.object(renamer, 'isfile', return_value=False), \
             patch.object(renamer.os, 'rename', side_effect=FileExistsError), \
             patch.object(renamer.shutil, 'rmtree', side_effect=PermissionError('read only')) as rmtree:
            self.renamer.run()
        self.assertEqual(rmtree.call_count, 2)

    def test_an_unexpected_rename_failure_does_not_stop_the_run(self):
        with patch.object(renamer, 'listdir', return_value=['A (1)', 'B (2)']), \
             patch.object(renamer, 'isfile', return_value=False), \
             patch.object(renamer.os, 'rename', side_effect=OSError('disk error')) as rename:
            self.renamer.run()
        self.assertEqual(rename.call_count, 2)


if __name__ == '__main__':
    unittest.main()
