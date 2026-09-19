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


class ChangedOnDiskTest(unittest.TestCase):
    """The stored mtime came out of a FLOAT column for two years; see migrate_v29."""

    def setUp(self):
        self.changed = load_module().changed_on_disk

    def test_a_newer_file_changed(self):
        self.assertTrue(self.changed(1782688928.32, 1782600000.5))

    def test_an_older_or_equal_file_did_not(self):
        self.assertFalse(self.changed(1782688928.32, 1782688928.32))
        self.assertFalse(self.changed(1782688928.32, 1782690000.0))

    def test_a_float32_rounded_stored_value_within_one_step_is_the_old_column_not_an_edit(self):
        # Real prod row: MOTZ/5 O'clock.mp3, mtime 1782688928.32, stored 1782688896.0.
        self.assertFalse(self.changed(1782688928.32, 1782688896.0))

    def test_an_exact_stored_value_still_sees_a_small_edit(self):
        # Once the exact mtime is stored, any later write counts, however soon.
        self.assertTrue(self.changed(1782688930.0, 1782688928.32))

    def test_a_float32_rounded_value_more_than_a_step_behind_is_an_edit(self):
        self.assertTrue(self.changed(1782688896.0 + 129.0, 1782688896.0))


class CreateTableTest(ProcessedFilesHelperTestCase):
    def test_the_table_is_created_if_it_is_missing(self):
        self.helper.create_table()
        self.assertIn('CREATE TABLE IF NOT EXISTS tagger_processed_files', self.executed()[0])
        self.assertIn('CREATE INDEX IF NOT EXISTS', self.executed()[1])
        self.assertIn('(needs_rescan, rescan_reason, filepath)', self.executed()[1])
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


class SnapshotTest(ProcessedFilesHelperTestCase):
    """One SELECT per round instead of one connection per file."""

    def test_the_whole_table_is_read_in_one_query(self):
        self.cursor.fetchall.return_value = [('/music/a.mp3', 100.0, 0), ('/music/b.mp3', 200.0, 1)]
        self.assertTrue(self.helper.load_snapshot())
        self.assertEqual(self.executed(), ['SELECT filepath, mtime, needs_rescan FROM tagger_processed_files'])
        self.connection.close.assert_called_once()

    def test_with_a_snapshot_needs_processing_asks_the_database_nothing(self):
        self.cursor.fetchall.return_value = [('/music/a.mp3', 100.0, 0), ('/music/b.mp3', 200.0, 1)]
        self.helper.load_snapshot()
        self.cursor.execute.reset_mock()
        self.assertFalse(self.helper.needs_processing('/music/a.mp3', 100.0))  # unchanged
        self.assertTrue(self.helper.needs_processing('/music/a.mp3', 101.0))  # changed on disk
        self.assertTrue(self.helper.needs_processing('/music/b.mp3', 200.0))  # flagged
        self.assertTrue(self.helper.needs_processing('/music/new.mp3', 5.0))  # never seen
        self.cursor.execute.assert_not_called()

    def test_marking_a_file_processed_keeps_the_snapshot_current(self):
        self.cursor.fetchall.return_value = [('/music/b.mp3', 200.0, 1)]
        self.helper.load_snapshot()
        self.helper.mark_processed('/music/b.mp3', 200.0)
        self.helper.mark_processed('/music/new.mp3', 5.0)
        self.cursor.execute.reset_mock()
        self.assertFalse(self.helper.needs_processing('/music/b.mp3', 200.0))
        self.assertFalse(self.helper.needs_processing('/music/new.mp3', 5.0))
        self.cursor.execute.assert_not_called()

    def test_dropping_the_snapshot_returns_to_per_file_queries(self):
        self.cursor.fetchall.return_value = [('/music/a.mp3', 100.0, 0)]
        self.helper.load_snapshot()
        self.helper.drop_snapshot()
        self.cursor.execute.reset_mock()
        self.cursor.fetchone.return_value = (100.0, 0)
        self.assertFalse(self.helper.needs_processing('/music/a.mp3', 100.0))
        self.assertIn('WHERE filepath = %s', self.executed()[0])

    def test_a_failed_load_falls_back_to_per_file_queries(self):
        self.cursor.execute.side_effect = RuntimeError('database gone')
        self.assertFalse(self.helper.load_snapshot())
        self.connection.close.assert_called_once()
        self.cursor.execute.side_effect = None
        self.cursor.fetchone.return_value = None
        self.assertTrue(self.helper.needs_processing('/music/a.mp3', 1.0))
        self.assertIn('WHERE filepath = %s', self.executed()[-1])


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
        self.assertEqual(self.cursor.execute.call_args.args[1], ('deep_run', 30, 200))

    def test_the_slice_carries_the_deep_run_reason(self):
        # So the page can tell it from a decision, and the queue serves it last.
        self.helper.mark_stale_for_rescan(30, 200)
        self.assertIn('rescan_reason = %s', self.executed()[0])

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


class PendingReasonsTest(ProcessedFilesHelperTestCase):
    def test_decisions_come_before_new_files_before_bulk_before_the_unexplained(self):
        self.cursor.fetchall.return_value = [
            (None,),
            ('rescan_all',),
            ('genre_decision',),
            ('new_in_library',),
            ('deep_run',),
            ('artist_decision',),
            ('rerun_parse',),
        ]
        self.assertEqual(
            self.helper.pending_reasons(),
            ['artist_decision', 'genre_decision', 'rerun_parse', 'new_in_library', 'deep_run', 'rescan_all', None],
        )
        self.assertIn('DISTINCT rescan_reason', self.executed()[0])
        self.connection.close.assert_called_once()

    def test_a_failure_reads_as_nothing_queued(self):
        self.cursor.execute.side_effect = RuntimeError('database gone')
        self.assertEqual(self.helper.pending_reasons(), [])


class PendingPathsTest(ProcessedFilesHelperTestCase):
    def test_a_page_of_queued_paths_is_read_in_key_order_past_the_cursor(self):
        self.cursor.fetchall.return_value = [('/music/b.mp3',), ('/music/c.mp3',)]
        paths = self.helper.pending_paths(2, after='/music/a.mp3', reason='genre_decision')
        self.assertEqual(paths, ['/music/b.mp3', '/music/c.mp3'])
        query, args = self.cursor.execute.call_args.args
        self.assertIn('needs_rescan = TRUE AND rescan_reason = %s AND filepath > %s', query)
        self.assertIn('ORDER BY filepath LIMIT %s', query)
        self.assertEqual(args, ('genre_decision', '/music/a.mp3', 2))
        self.connection.close.assert_called_once()

    def test_rows_without_a_reason_are_their_own_page(self):
        self.cursor.fetchall.return_value = []
        self.helper.pending_paths(500, reason=None)
        query, args = self.cursor.execute.call_args.args
        self.assertIn('rescan_reason IS NULL AND filepath > %s', query)
        self.assertEqual(args, ('', 500))

    def test_the_first_page_starts_before_every_path(self):
        self.cursor.fetchall.return_value = []
        self.helper.pending_paths(500, reason='deep_run')
        self.assertEqual(self.cursor.execute.call_args.args[1], ('deep_run', '', 500))


class QueueNewLibraryFilesTest(ProcessedFilesHelperTestCase):
    def test_the_anti_join_is_limited_to_the_walks_roots_and_extensions(self):
        self.cursor.rowcount = 7
        added = self.helper.queue_new_library_files(['/mnt/music/EPs', '/mnt/music/Top 100/'], ('mp3', 'm4a'))
        self.assertEqual(added, 7)
        query, args = self.cursor.execute.call_args.args
        self.assertIn('INSERT IGNORE INTO tagger_processed_files', query)
        self.assertIn('LEFT JOIN tagger_processed_files t ON t.filepath = mf.file_path', query)
        self.assertIn('WHERE t.filepath IS NULL', query)
        self.assertEqual(args, ('new_in_library', '/mnt/music/EPs/%', '/mnt/music/Top 100/%', '%.mp3', '%.m4a'))
        self.connection.commit.assert_called_once()

    def test_like_wildcards_in_a_root_are_taken_literally(self):
        self.cursor.rowcount = 0
        self.helper.queue_new_library_files(['/mnt/music/Warm_Up 100%'], ('mp3',))
        self.assertEqual(self.cursor.execute.call_args.args[1][1], '/mnt/music/Warm\\_Up 100\\%/%')

    def test_nothing_to_match_queues_nothing(self):
        self.assertEqual(self.helper.queue_new_library_files([], ('mp3',)), 0)
        self.assertEqual(self.helper.queue_new_library_files(['/mnt/music/EPs'], ()), 0)
        self.cursor.execute.assert_not_called()

    def test_a_failure_queues_nothing_and_still_closes_the_connection(self):
        self.cursor.execute.side_effect = RuntimeError('database gone')
        self.assertEqual(self.helper.queue_new_library_files(['/mnt/music/EPs'], ('mp3',)), 0)
        self.connection.close.assert_called_once()

    def test_a_failure_reads_as_an_empty_queue_and_still_closes_the_connection(self):
        self.cursor.execute.side_effect = RuntimeError('database gone')
        self.assertEqual(self.helper.pending_paths(500), [])
        self.connection.close.assert_called_once()


class ForgetTest(ProcessedFilesHelperTestCase):
    def test_the_row_of_a_vanished_file_is_deleted(self):
        self.helper.forget('/music/gone.mp3')
        query, args = self.cursor.execute.call_args.args
        self.assertIn('DELETE FROM tagger_processed_files WHERE filepath = %s', query)
        self.assertEqual(args, ('/music/gone.mp3',))
        self.connection.commit.assert_called_once()

    def test_a_failure_still_closes_the_connection(self):
        self.cursor.execute.side_effect = RuntimeError('database gone')
        self.helper.forget('/music/gone.mp3')
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
