import importlib.util
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


class MarkStaleForRescanTest(ProcessedFilesHelperTestCase):
    def test_only_rows_that_are_not_already_queued_are_picked(self):
        self.helper.mark_stale_for_rescan(30, 200)
        query = self.executed()[0]
        self.assertIn('needs_rescan = FALSE', query)
        self.assertIn('last_processed < NOW() - INTERVAL %s DAY', query)

    def test_the_oldest_rows_are_taken_first_and_the_batch_is_bounded(self):
        self.helper.mark_stale_for_rescan(30, 200)
        query = self.executed()[0]
        self.assertIn('ORDER BY last_processed', query)
        self.assertIn('LIMIT %s', query)
        self.assertEqual(self.cursor.execute.call_args.args[1], (30, 200))

    def test_the_number_of_queued_rows_is_returned(self):
        self.cursor.rowcount = 42
        self.assertEqual(self.helper.mark_stale_for_rescan(30, 200), 42)
        self.connection.commit.assert_called_once()

    def test_a_failure_queues_nothing_and_still_closes_the_connection(self):
        self.cursor.execute.side_effect = RuntimeError('database gone')
        self.assertEqual(self.helper.mark_stale_for_rescan(30, 200), 0)
        self.connection.close.assert_called_once()


class CountStaleTest(ProcessedFilesHelperTestCase):
    def test_the_rows_waiting_for_a_deep_run_are_counted(self):
        self.cursor.fetchone.return_value = (17,)
        self.assertEqual(self.helper.count_stale(30), 17)
        query = self.executed()[0]
        self.assertIn('COUNT(*)', query)
        self.assertIn('last_processed < NOW() - INTERVAL %s DAY', query)
        self.assertEqual(self.cursor.execute.call_args.args[1], (30,))

    def test_a_failure_reports_nothing_waiting(self):
        self.cursor.execute.side_effect = RuntimeError('database gone')
        self.assertEqual(self.helper.count_stale(30), 0)
        self.connection.close.assert_called_once()


class RescanReasonTest(ProcessedFilesHelperTestCase):
    """The reason exists so the UI can say what queued the work, nothing more.

    needs_rescan stays the gate the tagger reads; none of this touches that path.
    """

    def test_a_reason_is_stored_when_one_file_is_marked(self):
        self.helper.mark_for_rescan('/music/a.mp3', reason='artist_genre_rule')
        query = self.executed()[0]
        self.assertIn('rescan_reason = %s', query)
        self.assertEqual(
            self.cursor.execute.call_args_list[0].args[1],
            ('artist_genre_rule', '/music/a.mp3'),
        )

    def test_marking_everything_without_a_reason_still_works(self):
        self.helper.mark_for_rescan()
        self.assertIn('SET needs_rescan = TRUE', self.executed()[0])
        self.assertIsNone(self.cursor.execute.call_args_list[0].args[1])

    def test_marking_everything_can_carry_a_reason(self):
        self.helper.mark_for_rescan(None, reason='fallback')
        self.assertEqual(self.cursor.execute.call_args_list[0].args[1], ('fallback',))

    def test_marking_a_batch_of_paths_uses_one_statement(self):
        count = self.helper.mark_paths_for_rescan(['/music/a.mp3', '/music/b.mp3'], 'genre_decision')
        self.assertEqual(count, 2)
        query = self.executed()[0]
        self.assertIn('filepath IN (%s, %s)', query)
        self.assertEqual(
            self.cursor.execute.call_args_list[0].args[1],
            ('genre_decision', '/music/a.mp3', '/music/b.mp3'),
        )

    def test_an_empty_batch_does_not_touch_the_database_at_all(self):
        count = self.helper.mark_paths_for_rescan([], 'genre_decision')
        self.assertEqual(count, 0)
        self.cursor.execute.assert_not_called()

    def test_a_large_batch_is_split_into_chunks(self):
        paths = [f'/music/{i}.mp3' for i in range(1200)]
        self.helper.mark_paths_for_rescan(paths, 'fallback')
        self.assertEqual(self.cursor.execute.call_count, 3)

    def test_a_failing_batch_reports_nothing_marked(self):
        self.cursor.execute.side_effect = RuntimeError('database gone')
        self.assertEqual(self.helper.mark_paths_for_rescan(['/music/a.mp3'], 'fallback'), 0)

    def test_processing_a_file_clears_the_reason(self):
        self.helper.mark_processed('/music/a.mp3', 100.0)
        self.assertIn('rescan_reason = NULL', self.executed()[0])

    def test_the_pending_summary_groups_by_reason(self):
        self.cursor.fetchall.return_value = [('artist_genre_rule', 12), ('genre_decision', 130)]
        summary = self.helper.pending_summary()
        self.assertEqual(summary['total'], 142)
        self.assertEqual(summary['by_reason'][0], {'reason': 'artist_genre_rule', 'count': 12})

    def test_the_pending_summary_survives_a_database_error(self):
        self.cursor.execute.side_effect = RuntimeError('database gone')
        self.assertEqual(self.helper.pending_summary(), {'total': 0, 'by_reason': []})


if __name__ == '__main__':
    unittest.main()
