"""The `lms-listen-backfill` loop (bug report 075): windowed backfill, logging, config, /health.

MariaDB is replaced by `FakeMuma`, a small stateful stand-in that answers exactly the queries
`scrobble_reconcile.backfill()` sends, and LMS by an in-memory SQLite, so the real classifier,
window bounds and insert path run. tests/integration/test_scrobble_reconcile.py runs the same
loop against a real MariaDB.
"""

import logging
import os
import sqlite3
import sys
import threading
import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector')


import services.music_manager.routers.users as users_router

users_router.run_lms_db_sync = lambda only_sources=None: None  # type: ignore[assignment]

from fastapi.testclient import TestClient

from services.music_manager import lms_listen_backfill as loop
from services.music_manager import scrobble_reconcile as rec
from services.music_manager import thread_registry
from services.music_manager.main import app


def _full_health():
    """GET /health with the system key, which the full report needs since issue #218."""
    with patch.dict(os.environ, {'API_KEY': 'backfill-test-system-key'}):
        return TestClient(app).get('/health', headers={'X-API-Key': 'backfill-test-system-key'})


NOW = 1_790_000_000  # 2026-09-21, the moment every test runs "at"
HOUR = 3600
LOGGER = 'music-manager.lms-listen-backfill'


class DuplicateEntry(Exception):
    """Stands in for pymysql's IntegrityError 1062, which the unit suite has stubbed out."""


def lms_text(seconds):
    """Unix seconds as Wt::Dbo writes an LMS `date_time`."""
    return datetime.fromtimestamp(seconds, tz=UTC).strftime('%Y-%m-%dT%H:%M:%S.123')


class FakeMuma:
    """Just enough of muma's MariaDB for `backfill()`: listens, unmatched listens, users, files."""

    def __init__(self, files, users=('user',)):
        self.files = files
        self.users = list(users)
        self.listens = []  # dicts: id, username, track_id, at, created, source
        self.unmatched = []  # dicts: username, at, created
        self.queries = []
        self.process_offset = int(datetime.now().astimezone().utcoffset().total_seconds())

    def add_listen(self, track_id, at, username='user', source='lms', created=None):
        """Seed a `scrobble_listens` row."""
        self.listens.append(
            {
                'id': len(self.listens) + 1,
                'username': username,
                'track_id': track_id,
                'at': at,
                'created': at if created is None else created,
                'source': source,
            }
        )

    def connection(self):
        """A connection object whose cursors run against this fake."""
        conn = MagicMock()
        conn.cursor.side_effect = lambda: _FakeCursorContext(self)
        return conn

    def execute(self, sql, params):
        """Answer one statement; returns the rows a following fetch sees."""
        self.queries.append((sql, tuple(params)))
        if 'TIMESTAMPDIFF' in sql:
            return [{'offset_seconds': self.process_offset, 'zone': 'SYSTEM'}]
        if sql.startswith('SELECT @@session.time_zone'):
            return [{'zone': 'SYSTEM'}]
        if sql.startswith('SET time_zone'):
            return []
        if 'FROM library_media_files' in sql:
            return [{'file_path': p, 'track_id': self.files[p]} for p in params if p in self.files]
        if sql.startswith('SELECT username FROM users'):
            return [{'username': name} for name in self.users]
        since = params[-1] if 'FROM_UNIXTIME' in sql else None
        if 'FROM scrobble_listens' in sql:
            return [
                {
                    'id': row['id'],
                    'username': row['username'],
                    'track_id': row['track_id'],
                    'at': row['at'],
                    'created': row['created'],
                    'source': row['source'],
                }
                for row in self.listens
                if since is None or row['at'] >= since or row['created'] >= since
            ]
        if 'FROM scrobble_unmatched_listens' in sql:
            return [
                {'username': row['username'], 'at': row['at'], 'created': row['created']}
                for row in self.unmatched
                if since is None or row['at'] >= since or row['created'] >= since
            ]
        if sql.startswith('INSERT INTO scrobble_listens'):
            track_id, at, username, source = params
            key = (username.casefold(), at, track_id)
            if any((r['username'].casefold(), r['at'], r['track_id']) == key for r in self.listens):
                raise DuplicateEntry(1062, 'Duplicate entry')
            self.add_listen(track_id, at, username, source, created=NOW)
            return []
        raise AssertionError(f'unexpected statement: {sql}')


class _FakeCursorContext:
    """`with conn.cursor() as cursor:` over a FakeMuma."""

    def __init__(self, db):
        self.db = db
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        """Run the statement against the fake and keep its rows."""
        self.rows = self.db.execute(sql, params)
        return len(self.rows)

    def fetchall(self):
        """Every row of the last statement."""
        return self.rows

    def fetchone(self):
        """The first row of the last statement, or None."""
        return self.rows[0] if self.rows else None


def lms_server(listens):
    """An in-memory LMS database holding `listens`: (unix seconds, LMS track id) for user user."""
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE user (id INTEGER PRIMARY KEY, login_name TEXT)')
    conn.execute('CREATE TABLE track (id INTEGER PRIMARY KEY, absolute_file_path TEXT)')
    conn.execute(
        'CREATE TABLE listen (id INTEGER PRIMARY KEY, date_time TEXT, backend INTEGER, '
        'sync_state INTEGER, user_id INTEGER, track_id INTEGER)'
    )
    conn.execute("INSERT INTO user (login_name) VALUES ('user')")
    for track in (1, 2, 3):
        conn.execute('INSERT INTO track (id, absolute_file_path) VALUES (?, ?)', (track, f'/music/t{track}.mp3'))
    conn.executemany(
        'INSERT INTO listen (date_time, backend, sync_state, user_id, track_id) VALUES (?, 0, 1, 1, ?)',
        [(lms_text(at), track) for at, track in listens],
    )
    return conn


FILES = {f'/mnt/music/t{track}.mp3': 100 + track for track in (1, 2, 3)}


class BackfillTest(unittest.TestCase):
    """`scrobble_reconcile.backfill`: insert once, only inside the window, never repair shifted."""

    def setUp(self):
        self.db = FakeMuma(FILES)

    def run_backfill(self, lms_listens, window=48 * HOUR):
        """One loop round over the given LMS listens, at NOW."""
        server = lms_server(lms_listens)
        try:
            return rec.backfill(
                self.db.connection(), [(server, 'server-a')], since=NOW - window, until=NOW - loop.SETTLE_SECONDS
            )
        finally:
            server.close()

    def inserted(self):
        """(track id, at, source) of every row the backfill wrote."""
        return [(r['track_id'], r['at'], r['source']) for r in self.db.listens if r['source'] == 'lms-backfill']

    def test_a_lost_recent_listen_is_inserted_once_and_the_next_run_is_a_no_op(self):
        lost = NOW - 5 * HOUR
        first = self.run_backfill([(lost, 1)])
        self.assertEqual(first['written'], {'lms_only_inserted': 1, 'collisions': 0})
        self.assertEqual(first['users'], {'user': {'lms_only_inserted': 1, 'collisions': 0}})
        self.assertEqual(self.inserted(), [(101, lost, 'lms-backfill')])

        second = self.run_backfill([(lost, 1)])
        self.assertEqual(second['written'], {'lms_only_inserted': 0, 'collisions': 0})
        self.assertEqual(second['found']['exact'], 1)
        self.assertEqual(len(self.db.listens), 1)

    def test_an_lms_only_listen_older_than_the_window_is_not_touched(self):
        old = NOW - 72 * HOUR
        result = self.run_backfill([(old, 1), (NOW - 2 * HOUR, 2)])
        self.assertEqual(self.inserted(), [(102, NOW - 2 * HOUR, 'lms-backfill')])
        self.assertEqual(result['found']['lms_only'], 1)
        # The bound reached both sides: LMS by its own filter, muma from a margin before `since`.
        muma_reads = [params for sql, params in self.db.queries if 'FROM scrobble_listens' in sql]
        self.assertEqual(muma_reads, [(NOW - 48 * HOUR - rec.CONTEXT_MARGIN_SECONDS,) * 2])

    def test_a_listen_lms_recorded_moments_ago_waits_for_the_settle_period(self):
        result = self.run_backfill([(NOW - 60, 1)])
        self.assertEqual(result['written']['lms_only_inserted'], 0)
        self.assertEqual(result['found']['lms_only_insertable'], 0)
        self.assertEqual(self.db.listens, [])

    def test_a_shifted_listen_is_never_repaired(self):
        played = NOW - 10 * HOUR
        # Rewritten by bug 039: created when LMS relayed it, listened_at moved three hours later.
        self.db.add_listen(101, played + 3 * HOUR, created=played)
        result = self.run_backfill([(played, 1)])
        self.assertEqual(result['found']['shifted'], 1)
        self.assertEqual(result['written'], {'lms_only_inserted': 0, 'collisions': 0})
        self.assertEqual([r['at'] for r in self.db.listens], [played + 3 * HOUR])
        self.assertFalse(any(sql.startswith('UPDATE') for sql, _ in self.db.queries))

    def test_a_listen_the_app_scrobbled_a_minute_later_is_not_counted_twice(self):
        played = NOW - 4 * HOUR
        self.db.add_listen(102, played + 55, source='mobile')  # same play, matched to another track
        result = self.run_backfill([(played, 1)])
        self.assertEqual(result['written']['lms_only_inserted'], 0)

    def test_a_muma_listen_just_before_the_window_still_guards_a_listen_just_inside_it(self):
        since = NOW - 48 * HOUR
        self.db.add_listen(102, since - 120, source='mobile')
        self.run_backfill([(since + 60, 1)])
        self.assertEqual(self.inserted(), [])

    def test_an_insert_carries_the_account_s_own_spelling(self):
        """LMS says `user`, the account is `User`: the row goes in under identity's spelling."""
        self.db.users = ['User']
        self.run_backfill([(NOW - 5 * HOUR, 1)])
        self.assertEqual([r['username'] for r in self.db.listens], ['User'])
        # And a second round sees that row as the same user's, so it inserts nothing.
        self.assertEqual(self.run_backfill([(NOW - 5 * HOUR, 1)])['written']['lms_only_inserted'], 0)

    def test_a_user_muma_has_no_account_for_gets_nothing_inserted(self):
        self.db.users = ['anna']
        result = self.run_backfill([(NOW - 5 * HOUR, 1)])
        self.assertEqual(result['found']['lms_only_insertable'], 0)
        self.assertEqual(self.db.listens, [])

    def test_a_zone_mismatch_writes_nothing(self):
        self.db.process_offset += 3600
        with self.assertRaises(rec.ZoneMismatchError):
            self.run_backfill([(NOW - 5 * HOUR, 1)])
        self.assertEqual(self.db.listens, [])


class ReadLmsListensSinceTest(unittest.TestCase):
    """The `since` bound on LMS's side compares instants, not text."""

    def test_only_listens_at_or_after_since_are_read(self):
        server = lms_server([(NOW - 100, 1), (NOW - 99, 2), (NOW - 101, 3)])
        rows = rec.read_lms_listens(server, 'server-a', since=NOW - 100)
        self.assertEqual(sorted(row['path'] for row in rows), ['/music/t1.mp3', '/music/t2.mp3'])

    def test_a_space_separated_date_time_is_bounded_the_same_way(self):
        server = lms_server([])
        server.execute(
            "INSERT INTO listen (date_time, backend, sync_state, user_id, track_id) VALUES (?, 0, 1, 1, 1)",
            (datetime.fromtimestamp(NOW - 50, tz=UTC).strftime('%Y-%m-%d %H:%M:%S'),),
        )
        self.assertEqual(len(rec.read_lms_listens(server, 'server-a', since=NOW - 100)), 1)
        self.assertEqual(rec.read_lms_listens(server, 'server-a', since=NOW - 10), [])


class SettingsTest(unittest.TestCase):
    """The three config keys, with their defaults and validation."""

    def test_defaults_come_from_the_config_store_schema(self):
        # The unit suite replaces services.common.config_store with a mock (mock_base), so the
        # real schema is loaded from its file under another name.
        import importlib.util
        from pathlib import Path

        path = Path(__file__).resolve().parents[2] / 'common' / 'config_store.py'
        spec = importlib.util.spec_from_file_location('real_config_store', path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'real_config_store': module}):
            spec.loader.exec_module(module)
        fields = {field.key: field for field in module._config_fields()}
        self.assertIs(fields['lms_listen_backfill_enabled'].default, True)
        self.assertEqual(fields['lms_listen_backfill_interval_minutes'].default, 15)
        self.assertEqual(fields['lms_listen_backfill_window_hours'].default, 48)
        self.assertEqual({fields[key].group for key in fields if key.startswith('lms_listen_backfill')}, {'Scrobbling'})

    def test_missing_or_nonsense_values_fall_back_to_the_defaults(self):
        snapshot = loop.settings_snapshot(
            {'lms_listen_backfill_interval_minutes': 'soon', 'lms_listen_backfill_window_hours': 0}
        )
        self.assertEqual(snapshot, {'enabled': True, 'interval_seconds': 900, 'window_seconds': 48 * HOUR})

    def test_the_switch_reads_strings_as_booleans(self):
        self.assertFalse(loop.settings_snapshot({'lms_listen_backfill_enabled': 'false'})['enabled'])
        self.assertTrue(loop.settings_snapshot({'lms_listen_backfill_enabled': 'on'})['enabled'])
        self.assertFalse(loop.settings_snapshot({'lms_listen_backfill_enabled': False})['enabled'])


def result_with(inserted, collisions=0):
    """A `backfill()` result that inserted `inserted` listens for user."""
    return {
        'since': '2026-09-19T00:00:00Z',
        'until': '2026-09-20T23:30:00Z',
        'servers': ['server-a'],
        'found': {'lms_only': inserted, 'lms_only_insertable': inserted},
        'written': {'lms_only_inserted': inserted, 'collisions': collisions},
        'users': {'user': {'lms_only_inserted': inserted, 'collisions': collisions}} if inserted else {},
    }


class TickLoggingTest(unittest.TestCase):
    """INFO only when something was inserted; one WARNING for a whole run of failures."""

    SETTINGS = {'lms_listen_backfill_enabled': True, 'lms_listen_backfill_interval_minutes': 15}

    def setUp(self):
        loop._state['failing'] = False
        self.addCleanup(loop._state.__setitem__, 'failing', False)

    def tick(self):
        """One tick at NOW with the test settings."""
        return loop.backfill_tick(self.SETTINGS, clock=lambda: NOW)

    def test_a_round_that_inserted_logs_one_info_summary(self):
        with (
            patch.object(loop, 'run_once', return_value=result_with(3)) as run_once,
            self.assertLogs(LOGGER, level='DEBUG') as logs,
        ):
            self.assertEqual(self.tick(), 900)
        run_once.assert_called_once_with(NOW, 48 * HOUR)
        infos = [r for r in logs.records if r.levelno == logging.INFO]
        self.assertEqual(len(infos), 1)
        self.assertIn('inserted 3 listens', infos[0].getMessage())
        self.assertIn('user 3', infos[0].getMessage())

    def test_a_round_with_nothing_to_insert_logs_only_debug(self):
        with (
            patch.object(loop, 'run_once', return_value=result_with(0)),
            self.assertLogs(LOGGER, level='DEBUG') as logs,
        ):
            self.tick()
        self.assertEqual({r.levelno for r in logs.records}, {logging.DEBUG})

    def test_no_lms_database_is_debug_too(self):
        with patch.object(loop, 'run_once', return_value=None), self.assertLogs(LOGGER, level='DEBUG') as logs:
            self.tick()
        self.assertEqual({r.levelno for r in logs.records}, {logging.DEBUG})

    def test_a_run_of_failures_warns_once_and_a_success_rearms_it(self):
        with (
            patch.object(loop, 'run_once', side_effect=RuntimeError('database gone')),
            self.assertLogs(LOGGER, level='DEBUG') as logs,
        ):
            self.assertEqual(self.tick(), 900)
            self.tick()
            self.tick()
        warnings = [r for r in logs.records if r.levelno == logging.WARNING]
        self.assertEqual(len(warnings), 1)
        self.assertIn('database gone', warnings[0].getMessage())
        self.assertFalse(any(r.levelno > logging.WARNING for r in logs.records))

        with patch.object(loop, 'run_once', return_value=result_with(0)):
            self.tick()
        with (
            patch.object(loop, 'run_once', side_effect=RuntimeError('again')),
            self.assertLogs(LOGGER, level='WARNING') as again,
        ):
            self.tick()
        self.assertEqual(len(again.records), 1)

    def test_switched_off_it_reads_nothing(self):
        with patch.object(loop, 'run_once') as run_once:
            loop.backfill_tick({'lms_listen_backfill_enabled': False}, clock=lambda: NOW)
        run_once.assert_not_called()


class RunOnceTest(unittest.TestCase):
    """The glue: servers opened and closed, the window handed to `backfill()`."""

    def test_no_visible_lms_database_is_none(self):
        self.assertIsNone(loop.run_once(NOW, 48 * HOUR, servers_factory=list))

    def test_the_window_and_settle_bound_reach_backfill_and_everything_is_closed(self):
        server = MagicMock()
        conn = MagicMock()
        with (
            patch.object(loop, 'get_db_connection', return_value=conn),
            patch.object(rec, 'backfill', return_value=result_with(1)) as backfill,
        ):
            result = loop.run_once(NOW, 48 * HOUR, servers_factory=lambda: [(server, 'server-a')])
        self.assertEqual(result['written']['lms_only_inserted'], 1)
        backfill.assert_called_once_with(
            conn, [(server, 'server-a')], since=NOW - 48 * HOUR, until=NOW - loop.SETTLE_SECONDS
        )
        conn.close.assert_called_once()
        server.close.assert_called_once()

    def test_no_database_connection_raises_and_still_closes_the_servers(self):
        server = MagicMock()
        with patch.object(loop, 'get_db_connection', return_value=None), self.assertRaises(RuntimeError):
            loop.run_once(NOW, 48 * HOUR, servers_factory=lambda: [(server, 'server-a')])
        server.close.assert_called_once()


class OutboxStatusTest(unittest.TestCase):
    """`outbox_status()`: what each LMS still holds for muma in `muma_listen_outbox` (LMS db 125+)."""

    @staticmethod
    def _server_with_outbox(created: list[int]) -> sqlite3.Connection:
        """An in-memory LMS database with the outbox table as LMS creates it, holding `created`."""
        server = sqlite3.connect(':memory:')
        server.execute(
            'CREATE TABLE muma_listen_outbox (id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL,'
            ' created INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0)'
        )
        server.executemany(
            'INSERT INTO muma_listen_outbox (payload, created) VALUES (?, ?)', [('{}', c) for c in created]
        )
        return server

    def test_counts_the_waiting_listens_and_dates_the_oldest(self):
        server = self._server_with_outbox([NOW - HOUR, NOW - 2 * HOUR, NOW])
        status = loop.outbox_status(servers_factory=lambda: [(server, 'server-a')])
        self.assertEqual(
            status,
            [{'server': 'server-a', 'count': 3, 'oldest': datetime.fromtimestamp(NOW - 2 * HOUR, tz=UTC).isoformat()}],
        )

    def test_an_empty_outbox_has_no_oldest(self):
        server = self._server_with_outbox([])
        status = loop.outbox_status(servers_factory=lambda: [(server, 'server-a')])
        self.assertEqual(status, [{'server': 'server-a', 'count': 0, 'oldest': None}])

    def test_an_lms_without_an_outbox_reports_no_count_and_no_error(self):
        server = sqlite3.connect(':memory:')
        status = loop.outbox_status(servers_factory=lambda: [(server, 'server-a')])
        self.assertEqual(status, [{'server': 'server-a', 'count': None, 'oldest': None}])

    def test_an_unreadable_database_says_why_and_the_connection_is_closed(self):
        server = MagicMock()
        server.execute.side_effect = sqlite3.OperationalError('database is locked')
        status = loop.outbox_status(servers_factory=lambda: [(server, 'server-a')])
        self.assertEqual(status, [{'server': 'server-a', 'count': None, 'oldest': None, 'error': 'database is locked'}])
        server.close.assert_called_once()

    @patch('services.music_manager.main.event_service')
    @patch('services.music_manager.main.check_database', return_value=True)
    def test_health_carries_it_without_turning_red(self, _check, mock_events):
        mock_events.is_alive.return_value = True
        thread_registry.reset()
        self.addCleanup(thread_registry.reset)
        waiting = [{'server': 'server-a', 'count': 12, 'oldest': '2026-09-21T10:00:00+00:00'}]
        with patch.object(loop, 'outbox_status', return_value=waiting):
            response = _full_health()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['lms_listen_outbox'], waiting)

    @patch('services.music_manager.main.event_service')
    @patch('services.music_manager.main.check_database', return_value=True)
    def test_health_survives_a_status_that_raises(self, _check, mock_events):
        mock_events.is_alive.return_value = True
        thread_registry.reset()
        self.addCleanup(thread_registry.reset)
        with patch.object(loop, 'outbox_status', side_effect=RuntimeError('boom')):
            response = _full_health()
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['lms_listen_outbox'])


class LoopThreadTest(unittest.TestCase):
    """The thread runs through `run_forever`, stops on its event and shows in /health."""

    def setUp(self):
        thread_registry.reset()
        loop.stop_event.clear()
        self.addCleanup(thread_registry.reset)
        self.addCleanup(loop.stop_event.clear)

    @patch('services.music_manager.main.event_service')
    @patch('services.music_manager.main.check_database', return_value=True)
    def test_the_thread_shows_in_health_and_stops_on_its_event(self, _check, mock_events):
        mock_events.is_alive.return_value = True
        ticked = threading.Event()

        def fake_tick():
            ticked.set()
            return 3600

        with patch.object(loop, 'backfill_tick', side_effect=fake_tick):
            thread = thread_registry.start_thread(loop.THREAD_NAME, loop.run_lms_listen_backfill)
            self.assertTrue(ticked.wait(2))
            body = _full_health().json()
            self.assertTrue(body['threads']['lms-listen-backfill'])
            self.assertEqual(body['heartbeats']['lms-listen-backfill']['stale_after_seconds'], loop.STALE_AFTER_SECONDS)
            loop.stop_event.set()
            thread.join(timeout=2)
        self.assertFalse(thread.is_alive())

    def test_run_forever_without_a_stop_event_still_pauses_and_loops(self):
        calls = []

        def tick():
            calls.append(1)
            if len(calls) == 2:
                raise KeyboardInterrupt
            return 0.01

        with self.assertRaises(KeyboardInterrupt):
            thread_registry.run_forever('sleeper', tick, 1.0)
        self.assertEqual(calls, [1, 1])


if __name__ == '__main__':
    unittest.main()
