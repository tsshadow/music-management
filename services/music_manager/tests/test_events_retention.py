import importlib.util
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.music_manager import events_retention
from services.music_manager.events_retention import (
    LEVELS,
    RETRY_SOONER_SECONDS,
    max_rows,
    purge_once,
    retention_days,
    retention_tick,
    run_events_retention,
)
from services.tests.stop_after import StopAfter


def _real_config_store():
    """The real config_store module: services/conftest.py mocks it for the whole session."""
    path = Path(__file__).resolve().parents[2] / 'common' / 'config_store.py'
    spec = importlib.util.spec_from_file_location('real_config_store_for_retention', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_REAL_CONFIG = _real_config_store()
EVENTS_RETENTION_DEFAULT_DAYS = _REAL_CONFIG.EVENTS_RETENTION_DEFAULT_DAYS


class _FakeCursor:
    """Just enough of a DictCursor to run the retention SQL against a list of rows in memory."""

    def __init__(self, conn):
        self.conn = conn
        self.rowcount = 0
        self._result = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        self.conn.statements.append((sql, params))
        rows = self.conn.rows
        if sql.startswith('SET STATEMENT'):
            ids = set(params)
            before = len(rows)
            rows[:] = [r for r in rows if r['id'] not in ids]
            self.rowcount = before - len(rows)
            self.conn.batches.append(self.rowcount)
        elif 'information_schema' in sql:
            self._result = [{'n': self.conn.estimate if self.conn.estimate is not None else len(rows)}]
        elif sql.startswith('SELECT COUNT(*)'):
            self._result = [{'n': len(rows)}]
        elif 'INTERVAL' in sql:
            level, days, limit = params
            hits = sorted((r for r in rows if r['level'] == level and r['age'] > days), key=lambda r: -r['age'])
            self._result = [{'id': r['id']} for r in hits[:limit]]
        else:
            level, limit = params
            hits = sorted((r for r in rows if r['level'] == level), key=lambda r: -r['age'])
            self._result = [{'id': r['id']} for r in hits[:limit]]

    def fetchall(self):
        return self._result

    def fetchone(self):
        return self._result[0] if self._result else None


class _FakeConn:
    """An `events` table in memory: rows of id, level and age in days."""

    def __init__(self, rows, estimate=None):
        self.rows = [{'id': i, 'level': level, 'age': age} for i, (level, age) in enumerate(rows, start=1)]
        self.estimate = estimate
        self.statements = []
        self.batches = []
        self.commits = 0

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        self.commits += 1

    def levels(self):
        return sorted(r['level'] for r in self.rows)


class _Clock:
    """A monotonic clock that advances a fixed step every time it is read."""

    def __init__(self, step=0.0):
        self.now = 0.0
        self.step = step

    def __call__(self):
        self.now += self.step
        return self.now


DAYS = {'DEBUG': 3, 'INFO': 14, 'WARNING': 30, 'ERROR': 90, 'CRITICAL': 365}


class PurgeOnceTest(unittest.TestCase):
    def purge(self, conn, days=None, cap=0, **kwargs):
        kwargs.setdefault('clock', _Clock())
        kwargs.setdefault('sleep', lambda _s: None)
        return purge_once(conn, DAYS if days is None else days, cap, **kwargs)

    def test_default_windows_are_short_for_noise_and_long_for_critical(self):
        self.assertEqual(EVENTS_RETENTION_DEFAULT_DAYS, DAYS)
        self.assertEqual(set(LEVELS), set(DAYS))

    def test_each_level_keeps_its_own_window(self):
        conn = _FakeConn(
            [
                ('DEBUG', 2),
                ('DEBUG', 4),
                ('INFO', 13),
                ('INFO', 15),
                ('WARNING', 29),
                ('WARNING', 31),
                ('ERROR', 89),
                ('ERROR', 91),
                ('CRITICAL', 364),
                ('CRITICAL', 366),
            ]
        )

        result = self.purge(conn)

        self.assertEqual(
            sorted((r['level'], r['age']) for r in conn.rows),
            sorted([('DEBUG', 2), ('INFO', 13), ('WARNING', 29), ('ERROR', 89), ('CRITICAL', 364)]),
        )
        self.assertEqual(result.by_age, dict.fromkeys(LEVELS, 1))
        self.assertTrue(result.complete)

    def test_deletes_in_bounded_batches_by_primary_key(self):
        conn = _FakeConn([('INFO', 20)] * 25)

        with patch.object(events_retention, 'BATCH_SIZE', 10):
            result = self.purge(conn)

        self.assertEqual(conn.batches, [10, 10, 5])
        self.assertEqual(result.by_age['INFO'], 25)
        self.assertEqual(conn.rows, [])
        deletes = [sql for sql, _ in conn.statements if 'DELETE' in sql]
        self.assertTrue(all(re.search(r'WHERE id IN \(', sql) for sql in deletes))
        self.assertTrue(all('max_statement_time=' in sql for sql in deletes))
        self.assertEqual(conn.commits, 3)

    def test_pauses_between_full_batches(self):
        conn = _FakeConn([('INFO', 20)] * 25)
        pauses = []

        with patch.object(events_retention, 'BATCH_SIZE', 10):
            self.purge(conn, sleep=pauses.append)

        self.assertEqual(len(pauses), 2)

    def test_stops_at_the_time_bound_and_reports_incomplete(self):
        conn = _FakeConn([('INFO', 20)] * 100 + [('WARNING', 40)] * 10)

        with patch.object(events_retention, 'BATCH_SIZE', 10):
            # Every clock read costs a second, the pass may take ten.
            result = self.purge(conn, clock=_Clock(step=1.0), max_seconds=10)

        self.assertFalse(result.complete)
        self.assertLess(result.by_age['INFO'], 100)
        self.assertNotIn('WARNING', result.by_age)
        self.assertEqual(conn.levels().count('WARNING'), 10)

    def test_size_cap_removes_the_oldest_noise_first_and_never_critical(self):
        conn = _FakeConn([('INFO', 5)] * 3 + [('WARNING', 10)] * 3 + [('ERROR', 20)] * 3 + [('CRITICAL', 30)] * 3)

        with self.assertLogs('music-manager.events-retention', 'INFO') as logs:
            result = self.purge(conn, cap=4)

        self.assertEqual(result.by_size, {'INFO': 3, 'WARNING': 3, 'ERROR': 2})
        self.assertEqual(conn.levels(), ['CRITICAL', 'CRITICAL', 'CRITICAL', 'ERROR'])
        self.assertTrue(any('WARNING' in line and 'over its cap' in line for line in logs.output))

    def test_size_cap_counts_exactly_before_acting_on_a_stale_estimate(self):
        # InnoDB still reports the rows the age pass just removed.
        conn = _FakeConn([('INFO', 5)] * 3, estimate=1_000)

        result = self.purge(conn, cap=10)

        self.assertEqual(result.by_size, {})
        self.assertEqual(len(conn.rows), 3)
        self.assertTrue(any(sql.startswith('SELECT COUNT(*)') for sql, _ in conn.statements))

    def test_size_cap_skips_the_exact_count_when_the_estimate_is_under(self):
        conn = _FakeConn([('INFO', 5)] * 3)

        self.purge(conn, cap=10)

        self.assertFalse(any(sql.startswith('SELECT COUNT(*)') for sql, _ in conn.statements))

    def test_logs_one_summary_line_per_pass(self):
        conn = _FakeConn([('INFO', 20)] * 3 + [('WARNING', 40)])

        with self.assertLogs('music-manager.events-retention', 'INFO') as logs:
            self.purge(conn)

        self.assertEqual(len(logs.output), 1)
        self.assertIn('removed 4 row(s)', logs.output[0])
        self.assertIn('INFO 3, WARNING 1', logs.output[0])
        self.assertIn('done', logs.output[0])

    def test_summary_says_when_the_bound_stopped_it(self):
        conn = _FakeConn([('INFO', 20)] * 50)

        with (
            patch.object(events_retention, 'BATCH_SIZE', 10),
            self.assertLogs('music-manager.events-retention', 'INFO') as logs,
        ):
            self.purge(conn, clock=_Clock(step=1.0), max_seconds=5)

        self.assertEqual(len(logs.output), 1)
        self.assertIn('stopped at the', logs.output[0])


@patch.object(events_retention, 'EVENTS_RETENTION_DEFAULT_DAYS', EVENTS_RETENTION_DEFAULT_DAYS)
class SettingsTest(unittest.TestCase):
    def test_configured_windows_override_the_defaults(self):
        settings = {'events_retention_info_days': 7, 'events_retention_warning_days': '10'}

        days = retention_days(settings)

        self.assertEqual(days['INFO'], 7)
        self.assertEqual(days['WARNING'], 10)
        self.assertEqual(days['CRITICAL'], EVENTS_RETENTION_DEFAULT_DAYS['CRITICAL'])

    def test_zero_or_garbage_falls_back_to_the_default(self):
        days = retention_days({'events_retention_info_days': 0, 'events_retention_error_days': 'x'})

        self.assertEqual(days['INFO'], EVENTS_RETENTION_DEFAULT_DAYS['INFO'])
        self.assertEqual(days['ERROR'], EVENTS_RETENTION_DEFAULT_DAYS['ERROR'])

    def test_size_cap_zero_switches_it_off(self):
        self.assertEqual(max_rows({'events_max_rows': 0}), 0)
        self.assertEqual(max_rows({'events_max_rows': None}), 0)
        self.assertEqual(max_rows({'events_max_rows': 123}), 123)

    def test_every_setting_is_in_the_config_schema(self):
        keys = {f.key for f in _REAL_CONFIG._config_fields()}
        for level in LEVELS:
            self.assertIn(f'events_retention_{level.lower()}_days', keys)
        self.assertIn('events_max_rows', keys)


class RetentionTickTest(unittest.TestCase):
    def test_an_incomplete_pass_asks_to_come_back_within_the_hour(self):
        conn = MagicMock()
        with (
            patch.object(events_retention, 'get_db_connection', return_value=conn),
            patch.object(events_retention, 'purge_once', return_value=MagicMock(complete=False)),
            patch.object(events_retention, 'purge_refresh_tokens'),
        ):
            self.assertEqual(retention_tick(), RETRY_SOONER_SECONDS)
        conn.close.assert_called_once()

    def test_a_complete_pass_keeps_the_daily_interval(self):
        with (
            patch.object(events_retention, 'get_db_connection', return_value=MagicMock()),
            patch.object(events_retention, 'purge_once', return_value=MagicMock(complete=True)),
            patch.object(events_retention, 'purge_refresh_tokens'),
        ):
            self.assertIsNone(retention_tick())


class PruneWrappedRangesTest(unittest.TestCase):
    def test_the_tick_prunes_stored_wrapped_ranges(self):
        conn = MagicMock()
        with (
            patch.object(events_retention, 'get_db_connection', return_value=conn),
            patch.object(events_retention, 'purge_once', return_value=MagicMock(complete=True)),
            patch.object(events_retention, 'purge_refresh_tokens'),
            patch.object(events_retention, 'prune_wrapped_ranges') as prune,
        ):
            retention_tick()
        prune.assert_called_once_with(conn)

    def test_a_failed_prune_is_a_warning_not_an_error(self):
        with (
            patch('services.music_manager.wrapped.snapshots.prune', side_effect=RuntimeError('gone')),
            self.assertLogs(events_retention.logger, 'WARNING') as logs,
        ):
            events_retention.prune_wrapped_ranges(MagicMock())
        self.assertIn('gone', logs.output[0])


class RunEventsRetentionTest(unittest.TestCase):
    """run_events_retention must never die: every path through the loop body
    must be caught, logged as an ERROR, and followed by a pause.

    The loop runs through thread_registry.run_forever. Each test hands it a StopAfter event,
    which ends it after an exact number of rounds without touching `time.sleep` -- the
    process-wide function a patched side_effect list used to share with the event writer
    thread (bug report 099). The failure is asserted on the `music-manager.threads` logger,
    which reaches the events pipeline.
    """

    def test_purge_once_raising_is_caught_and_loop_continues(self):
        conn = MagicMock()
        stop = StopAfter(2)
        with (
            patch('services.music_manager.events_retention.get_db_connection', return_value=conn),
            patch('services.music_manager.events_retention.purge_once', side_effect=RuntimeError('boom')),
            self.assertLogs('music-manager.threads', 'ERROR') as logs,
        ):
            run_events_retention(stop=stop)

        self.assertEqual(len(stop.delays), 2)
        self.assertIn('boom', '\n'.join(logs.output))
        conn.close.assert_called()

    def test_get_db_connection_raising_is_caught_and_loop_continues(self):
        stop = StopAfter(2)
        with (
            patch('services.music_manager.events_retention.get_db_connection', side_effect=RuntimeError('db down')),
            patch('services.music_manager.events_retention.purge_once') as mock_purge,
            self.assertLogs('music-manager.threads', 'ERROR') as logs,
        ):
            run_events_retention(stop=stop)

        self.assertEqual(len(stop.delays), 2)
        mock_purge.assert_not_called()
        self.assertIn('db down', '\n'.join(logs.output))

    def test_conn_close_raising_is_caught_and_loop_continues(self):
        conn = MagicMock()
        conn.close.side_effect = RuntimeError('close failed')
        stop = StopAfter(2)
        with (
            patch('services.music_manager.events_retention.get_db_connection', return_value=conn),
            patch('services.music_manager.events_retention.purge_once') as mock_purge,
            self.assertLogs('music-manager.threads', 'ERROR') as logs,
        ):
            run_events_retention(stop=stop)

        self.assertEqual(len(stop.delays), 2)
        mock_purge.assert_called_with(conn)
        self.assertIn('close failed', '\n'.join(logs.output))

    def test_none_connection_skips_purge_and_still_sleeps(self):
        stop = StopAfter(2)
        with (
            patch('services.music_manager.events_retention.get_db_connection', return_value=None),
            patch('services.music_manager.events_retention.purge_once') as mock_purge,
        ):
            run_events_retention(stop=stop)

        mock_purge.assert_not_called()
        # A pass without a connection is not a failure: the full day's interval follows.
        self.assertEqual(stop.delays, [86400, 86400])
