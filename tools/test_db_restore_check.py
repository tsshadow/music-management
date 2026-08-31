import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools import db_restore_check


class TargetDatabaseTest(unittest.TestCase):

    def test_defaults_to_a_suffixed_name(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('RESTORE_CHECK_DB', None)
            self.assertEqual(db_restore_check.target_database('music-management'),
                             'music-management_restore_check')

    def test_refuses_to_restore_over_the_live_database(self):
        """The whole point of naming the target is that this cannot happen."""
        with patch.dict(os.environ, {'RESTORE_CHECK_DB': 'music-management'}):
            with self.assertRaises(db_restore_check.RestoreCheckError) as caught:
                db_restore_check.target_database('music-management')
            self.assertIn('refusing to restore over it', str(caught.exception))


class CompareTest(unittest.TestCase):

    def test_matching_counts_produce_no_problems(self):
        recorded = {'tracks': 1000, 'events': 500}
        self.assertEqual(db_restore_check.compare(recorded, dict(recorded)), [])

    def test_a_missing_table_is_reported(self):
        problems = db_restore_check.compare({'tracks': 10, 'events': 5}, {'tracks': 10})
        self.assertEqual(len(problems), 1)
        self.assertIn('tables missing after restore: events', problems[0])

    def test_an_unexpected_table_is_reported(self):
        problems = db_restore_check.compare({'tracks': 10}, {'tracks': 10, 'stray': 1})
        self.assertIn('tables present that were not dumped: stray', problems[0])

    def test_an_emptied_table_is_reported(self):
        problems = db_restore_check.compare({'tracks': 1000}, {'tracks': 0})
        self.assertEqual(len(problems), 1)
        self.assertIn('tracks: 0 rows restored, 1000 recorded', problems[0])

    def test_small_drift_on_a_large_table_is_accepted(self):
        """The snapshot is taken before the counts, so a few rows short is arithmetic."""
        problems = db_restore_check.compare({'events': 1_000_000}, {'events': 995_000})
        self.assertEqual(problems, [])

    def test_a_large_shortfall_is_still_caught(self):
        problems = db_restore_check.compare({'events': 1_000_000}, {'events': 500_000})
        self.assertEqual(len(problems), 1)

    def test_small_tables_are_compared_exactly(self):
        """Two percent of five rows rounds to zero, which would accept any loss."""
        problems = db_restore_check.compare({'settings': 5}, {'settings': 4})
        self.assertEqual(len(problems), 1)
        self.assertIn('settings: 4 rows restored, 5 recorded', problems[0])

    def test_a_table_recorded_as_empty_is_not_compared(self):
        self.assertEqual(db_restore_check.compare({'unused': 0}, {'unused': 0}), [])


class MainTest(unittest.TestCase):

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dest = Path(self.tmp.name)
        dump = self.dest / 'muma_db_20260831_030000.sql.gz'
        dump.write_bytes(b'irrelevant, the restore is mocked')
        (self.dest / 'latest.json').write_text(json.dumps({
            'file': dump.name,
            'finished_at': '2026-08-31T03:10:00+00:00',
            'row_counts': {'tracks': 1000},
        }))
        env = {'BACKUP_PATH': str(self.dest), 'DB_DB': 'music-management',
               'DB_USER': 'u', 'DB_PASS': 'p', 'DB_HOST': 'db'}
        patcher = patch.dict(os.environ, env, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop('RESTORE_CHECK_DB', None)

    def test_a_matching_restore_passes_quietly(self):
        with patch.object(db_restore_check, '_run_sql', return_value=''), \
                patch.object(db_restore_check, 'restore'), \
                patch.object(db_restore_check, 'restored_counts',
                             return_value={'tracks': 1000}), \
                patch.object(db_restore_check, 'alert') as alert:
            self.assertEqual(db_restore_check.main([]), 0)
        alert.assert_not_called()

    def test_a_mismatch_alerts_with_the_detail(self):
        with patch.object(db_restore_check, '_run_sql', return_value=''), \
                patch.object(db_restore_check, 'restore'), \
                patch.object(db_restore_check, 'restored_counts',
                             return_value={'tracks': 3}), \
                patch.object(db_restore_check, 'alert') as alert:
            self.assertEqual(db_restore_check.main([]), 1)
        alert.assert_called_once()
        self.assertIn('tracks: 3 rows restored, 1000 recorded', alert.call_args[0][1])

    def test_the_throwaway_database_is_dropped_even_when_the_restore_fails(self):
        """Leaving a 7 GB copy behind twice fills the disk the database is on."""
        statements = []

        def record(_defaults, _creds, sql, database=None):
            statements.append(sql)
            return ''

        with patch.object(db_restore_check, '_run_sql', record), \
                patch.object(db_restore_check, 'restore',
                             side_effect=db_restore_check.RestoreCheckError('boom')), \
                patch.object(db_restore_check, 'alert'):
            self.assertEqual(db_restore_check.main([]), 1)
        drops = [s for s in statements if s.startswith('DROP DATABASE')]
        self.assertEqual(len(drops), 2, 'expected a drop before and after the restore')
        self.assertIn('music-management_restore_check', drops[-1])

    def test_a_dump_named_in_latest_json_but_absent_is_an_error(self):
        (self.dest / 'muma_db_20260831_030000.sql.gz').unlink()
        with patch.object(db_restore_check, 'alert') as alert:
            self.assertEqual(db_restore_check.main([]), 1)
        self.assertIn('is not on disk', alert.call_args[0][1])


if __name__ == '__main__':
    unittest.main()
