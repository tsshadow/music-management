import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# mock_base replaces this module with a MagicMock so that no test can reach MariaDB.
# Load the real source under a throwaway name and inject a fake DatabaseConnector.
_SOURCE = Path(__file__).resolve().parent / 'ProcessedFilesHelper.py'


def load_module():
    spec = importlib.util.spec_from_file_location('_real_processed_files_helper', _SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProcessedFilesHelperTestCase(unittest.TestCase):

    def setUp(self):
        self.module = load_module()
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.connection.cursor.return_value.__exit__.return_value = False
        connector = MagicMock()
        connector.connect.return_value = self.connection
        patcher = patch.object(self.module, 'DatabaseConnector', return_value=connector)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.helper = self.module.ProcessedFilesHelper()

    def executed(self):
        return [call.args[0] for call in self.cursor.execute.call_args_list]


class CreateTableTest(ProcessedFilesHelperTestCase):

    def test_the_table_is_created_if_it_is_missing(self):
        self.helper.create_table()
        self.assertIn('CREATE TABLE IF NOT EXISTS tagger_processed_files', self.executed()[0])
        self.connection.commit.assert_called_once()
        self.connection.close.assert_called_once()

    def test_a_custom_table_name_is_used(self):
        helper = self.module.ProcessedFilesHelper(table_name='other_table')
        helper.create_table()
        self.assertIn('other_table', self.executed()[0])

    def test_a_failure_still_closes_the_connection(self):
        self.cursor.execute.side_effect = RuntimeError('database gone')
        self.helper.create_table()
        self.connection.close.assert_called_once()


class NeedsProcessingTest(ProcessedFilesHelperTestCase):

    def test_a_song_that_was_never_seen_needs_processing(self):
        self.cursor.fetchone.return_value = None
        self.assertTrue(self.helper.needs_processing('/music/a.mp3', 100.0))

    def test_a_song_that_changed_on_disk_needs_processing(self):
        self.cursor.fetchone.return_value = (100.0, False)
        self.assertTrue(self.helper.needs_processing('/music/a.mp3', 200.0))

    def test_an_unchanged_song_is_skipped(self):
        self.cursor.fetchone.return_value = (200.0, False)
        self.assertFalse(self.helper.needs_processing('/music/a.mp3', 200.0))

    def test_a_song_flagged_for_rescan_needs_processing_regardless_of_its_mtime(self):
        self.cursor.fetchone.return_value = (200.0, True)
        self.assertTrue(self.helper.needs_processing('/music/a.mp3', 100.0))

    def test_a_database_error_errs_on_the_side_of_processing(self):
        self.cursor.execute.side_effect = RuntimeError('database gone')
        self.assertTrue(self.helper.needs_processing('/music/a.mp3', 100.0))
        self.connection.close.assert_called_once()


class MarkProcessedTest(ProcessedFilesHelperTestCase):

    def test_the_song_and_its_mtime_are_stored(self):
        self.helper.mark_processed('/music/a.mp3', 123.0)
        self.assertEqual(self.cursor.execute.call_args.args[1], ('/music/a.mp3', 123.0))
        self.connection.commit.assert_called_once()

    def test_a_failure_still_closes_the_connection(self):
        self.cursor.execute.side_effect = RuntimeError('database gone')
        self.helper.mark_processed('/music/a.mp3', 123.0)
        self.connection.close.assert_called_once()


class MarkForRescanTest(ProcessedFilesHelperTestCase):

    def test_a_single_song_can_be_flagged(self):
        self.helper.mark_for_rescan('/music/a.mp3')
        self.assertIn('WHERE filepath = %s', self.executed()[0])
        self.assertEqual(self.cursor.execute.call_args.args[1], ('/music/a.mp3',))

    def test_the_whole_library_can_be_flagged_at_once(self):
        self.helper.mark_for_rescan()
        self.assertNotIn('WHERE', self.executed()[0])
        self.assertIsNone(self.cursor.execute.call_args.args[1])

    def test_a_failure_still_closes_the_connection(self):
        self.cursor.execute.side_effect = RuntimeError('database gone')
        self.helper.mark_for_rescan()
        self.connection.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
