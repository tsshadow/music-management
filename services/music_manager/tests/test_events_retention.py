import sys
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql'):
    sys.modules.setdefault(_mod_name, MagicMock())

from services.music_manager.events_retention import (
    RETENTION_DAYS,
    purge_once,
    run_events_retention,
)


class PurgeOnceTest(unittest.TestCase):
    def setUp(self):
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = self.cursor

    def test_retention_windows_match_the_spec(self):
        self.assertEqual(RETENTION_DAYS, {'INFO': 14, 'WARNING': 60, 'ERROR': 365, 'CRITICAL': 365})

    def test_deletes_per_level_with_its_own_window(self):
        self.cursor.rowcount = 0

        purge_once(self.conn)

        levels_and_days = [(call[0][1][0], call[0][1][1]) for call in self.cursor.execute.call_args_list]
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


class _StopLoop(Exception):
    """Sentinel used to escape run_events_retention's infinite loop in tests."""


class RunEventsRetentionTest(unittest.TestCase):
    """run_events_retention must never die: every path through the loop body
    must be caught, logged as an ERROR, and followed by a sleep.

    The loop now runs through thread_registry.run_forever, so the sleep is patched there
    and the failure is asserted on the `music-manager.threads` logger (which reaches the
    events pipeline) instead of on stderr.
    """

    SLEEP = 'services.music_manager.thread_registry.time.sleep'

    def test_purge_once_raising_is_caught_and_loop_continues(self):
        conn = MagicMock()
        with (
            patch('services.music_manager.events_retention.get_db_connection', return_value=conn),
            patch('services.music_manager.events_retention.purge_once', side_effect=RuntimeError('boom')),
            patch(self.SLEEP, side_effect=[None, _StopLoop()]) as mock_sleep,
            self.assertLogs('music-manager.threads', 'ERROR') as logs,
        ):
            with self.assertRaises(_StopLoop):
                run_events_retention()

        self.assertEqual(mock_sleep.call_count, 2)
        self.assertIn('boom', '\n'.join(logs.output))
        conn.close.assert_called()

    def test_get_db_connection_raising_is_caught_and_loop_continues(self):
        with (
            patch('services.music_manager.events_retention.get_db_connection', side_effect=RuntimeError('db down')),
            patch('services.music_manager.events_retention.purge_once') as mock_purge,
            patch(self.SLEEP, side_effect=[None, _StopLoop()]) as mock_sleep,
            self.assertLogs('music-manager.threads', 'ERROR') as logs,
        ):
            with self.assertRaises(_StopLoop):
                run_events_retention()

        self.assertEqual(mock_sleep.call_count, 2)
        mock_purge.assert_not_called()
        self.assertIn('db down', '\n'.join(logs.output))

    def test_conn_close_raising_is_caught_and_loop_continues(self):
        conn = MagicMock()
        conn.close.side_effect = RuntimeError('close failed')
        with (
            patch('services.music_manager.events_retention.get_db_connection', return_value=conn),
            patch('services.music_manager.events_retention.purge_once') as mock_purge,
            patch(self.SLEEP, side_effect=[None, _StopLoop()]) as mock_sleep,
            self.assertLogs('music-manager.threads', 'ERROR') as logs,
        ):
            with self.assertRaises(_StopLoop):
                run_events_retention()

        self.assertEqual(mock_sleep.call_count, 2)
        mock_purge.assert_called_with(conn)
        self.assertIn('close failed', '\n'.join(logs.output))

    def test_none_connection_skips_purge_and_still_sleeps(self):
        with (
            patch('services.music_manager.events_retention.get_db_connection', return_value=None),
            patch('services.music_manager.events_retention.purge_once') as mock_purge,
            patch(self.SLEEP, side_effect=[None, _StopLoop()]) as mock_sleep,
        ):
            with self.assertRaises(_StopLoop):
                run_events_retention()

        mock_purge.assert_not_called()
        self.assertEqual(mock_sleep.call_count, 2)
        # A pass without a connection is not a failure: the full day's interval follows.
        self.assertEqual(mock_sleep.call_args_list[0].args[0], 86400)
