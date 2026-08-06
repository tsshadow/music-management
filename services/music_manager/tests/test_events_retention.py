import sys
import unittest
from unittest.mock import MagicMock

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql'):
    sys.modules.setdefault(_mod_name, MagicMock())

from services.music_manager.events_retention import RETENTION_DAYS, purge_once


class PurgeOnceTest(unittest.TestCase):

    def setUp(self):
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = self.cursor

    def test_retention_windows_match_the_spec(self):
        self.assertEqual(RETENTION_DAYS,
                         {'INFO': 14, 'WARNING': 60, 'ERROR': 365, 'CRITICAL': 365})

    def test_deletes_per_level_with_its_own_window(self):
        self.cursor.rowcount = 0

        purge_once(self.conn)

        levels_and_days = [(call[0][1][0], call[0][1][1])
                           for call in self.cursor.execute.call_args_list]
        self.assertIn(('INFO', 14), levels_and_days)
        self.assertIn(('WARNING', 60), levels_and_days)
        self.assertIn(('ERROR', 365), levels_and_days)
        self.assertIn(('CRITICAL', 365), levels_and_days)

    def test_deletes_in_batches_until_exhausted(self):
        self.cursor.rowcount = 0
        info_rowcounts = iter([10000, 10000, 3, 0, 0, 0])

        def execute(_sql, params):
            self.cursor.rowcount = next(info_rowcounts) if params[0] == 'INFO' else 0

        self.cursor.execute.side_effect = execute

        removed = purge_once(self.conn)

        self.assertEqual(removed['INFO'], 20003)
        info_calls = [c for c in self.cursor.execute.call_args_list if c[0][1][0] == 'INFO']
        self.assertEqual(len(info_calls), 3)

    def test_uses_a_batch_limit(self):
        self.cursor.rowcount = 0

        purge_once(self.conn)

        sql = self.cursor.execute.call_args_list[0][0][0]
        self.assertIn('LIMIT', sql)
        self.assertIn('INTERVAL %s DAY', sql)
