import json
import os
import sys
import threading
import time
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.easyid3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())
import services.music_manager.routers.users

services.music_manager.routers.users.run_lms_db_sync = lambda: None
import services.music_manager.database

services.music_manager.database.get_db_connection = MagicMock(return_value=None)
from fastapi.testclient import TestClient

from services.music_manager import thread_registry
from services.music_manager.main import app


class ThreadRegistryTest(unittest.TestCase):
    def setUp(self):
        thread_registry.reset()

    def tearDown(self):
        thread_registry.reset()

    def test_started_thread_reports_alive(self):
        stop = threading.Event()
        thread_registry.start_thread('slaper', stop.wait)
        self.addCleanup(stop.set)

        self.assertTrue(thread_registry.thread_status()['slaper'])

    def test_finished_thread_reports_dead(self):
        thread = thread_registry.start_thread('vlieger', lambda: None)
        thread.join(timeout=2)

        self.assertFalse(thread_registry.thread_status()['vlieger'])


class HealthTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        thread_registry.reset()

    def tearDown(self):
        thread_registry.reset()

    @patch('services.music_manager.main.event_service')
    @patch('services.music_manager.main.check_database')
    def test_healthy_when_database_and_threads_are_up(self, mock_get_db, mock_events):
        mock_get_db.return_value = True
        mock_events.is_alive.return_value = True
        stop = threading.Event()
        thread_registry.start_thread('tagger', stop.wait)
        self.addCleanup(stop.set)

        response = self.client.get('/health')

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['status'], 'ok')
        self.assertEqual(body['database'], 'ok')
        self.assertTrue(body['threads']['tagger'])
        self.assertTrue(body['threads']['events'])

    # The database check is now database.check_database (SELECT 1 on its own connection)
    # rather than "the pool handed out a connection", so these two patch that instead.
    @patch('services.music_manager.main.event_service')
    @patch('services.music_manager.main.check_database')
    def test_degraded_with_503_when_database_is_gone(self, mock_check, mock_events):
        mock_check.return_value = False
        mock_events.is_alive.return_value = True

        response = self.client.get('/health')

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['status'], 'degraded')
        self.assertEqual(response.json()['database'], 'unreachable')

    @patch('services.music_manager.main.event_service')
    @patch('services.music_manager.main.check_database')
    def test_degraded_with_503_when_database_raises(self, mock_check, mock_events):
        mock_check.side_effect = Exception('pool kan geen connectie geven')
        mock_events.is_alive.return_value = True

        response = self.client.get('/health')

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['status'], 'degraded')
        self.assertEqual(response.json()['database'], 'unreachable')

    @patch('services.music_manager.main.event_service')
    @patch('services.music_manager.main.check_database')
    def test_degraded_when_a_thread_died(self, mock_get_db, mock_events):
        mock_get_db.return_value = True
        mock_events.is_alive.return_value = True
        thread = thread_registry.start_thread('scanner', lambda: None)
        thread.join(timeout=2)

        response = self.client.get('/health')

        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()['threads']['scanner'])

    @patch('services.music_manager.main.event_service')
    @patch('services.music_manager.main.check_database')
    def test_degraded_when_the_event_worker_died(self, mock_get_db, mock_events):
        mock_get_db.return_value = True
        mock_events.is_alive.return_value = False

        response = self.client.get('/health')

        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()['threads']['events'])


class HealthHeartbeatTest(unittest.TestCase):
    """A loop that is alive but no longer completes a tick is as broken as a dead one."""

    def setUp(self):
        self.client = TestClient(app)
        thread_registry.reset()
        stop = threading.Event()
        self.addCleanup(stop.set)
        self.addCleanup(thread_registry.reset)
        thread_registry.start_thread('scanner', stop.wait)

    @patch('services.music_manager.main.event_service')
    @patch('services.music_manager.main.check_database', return_value=True)
    def test_fresh_heartbeat_right_after_startup_is_healthy(self, _check, mock_events):
        """The e2e suite waits on a 200 right after startup: registration counts as a beat."""
        mock_events.is_alive.return_value = True
        thread_registry.register_heartbeat('scanner', stale_after=3600)

        response = self.client.get('/health')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['threads']['scanner'])
        detail = response.json()['heartbeats']['scanner']
        self.assertTrue(detail['alive'])
        self.assertFalse(detail['stale'])
        self.assertEqual(detail['stale_after_seconds'], 3600)

    @patch('services.music_manager.main.event_service')
    @patch('services.music_manager.main.check_database', return_value=True)
    def test_stale_heartbeat_flips_health_to_503(self, _check, mock_events):
        mock_events.is_alive.return_value = True
        thread_registry.register_heartbeat('scanner', stale_after=60)
        thread_registry._heartbeats['scanner'].last_beat_monotonic -= 120

        response = self.client.get('/health')

        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body['status'], 'degraded')
        self.assertFalse(body['threads']['scanner'])
        self.assertTrue(body['heartbeats']['scanner']['alive'])
        self.assertTrue(body['heartbeats']['scanner']['stale'])

    @patch('services.music_manager.main.event_service')
    @patch('services.music_manager.main.check_database', return_value=True)
    def test_a_new_beat_makes_it_healthy_again(self, _check, mock_events):
        mock_events.is_alive.return_value = True
        thread_registry.register_heartbeat('scanner', stale_after=60)
        thread_registry._heartbeats['scanner'].last_beat_monotonic -= 120
        thread_registry.beat('scanner')

        self.assertEqual(self.client.get('/health').status_code, 200)


class HealthDatabaseProbeTest(unittest.TestCase):
    """`database: ok` has to mean MariaDB answered, and the answer has to come in time."""

    def setUp(self):
        self.client = TestClient(app)
        thread_registry.reset()
        self.addCleanup(thread_registry.reset)

    @patch('services.music_manager.main.event_service')
    def test_unreachable_when_select_1_raises(self, mock_events):
        mock_events.is_alive.return_value = True
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value.execute.side_effect = Exception('server has gone away')
        with patch.object(services.music_manager.database.pymysql, 'connect', return_value=conn):
            response = self.client.get('/health')

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['database'], 'unreachable')
        conn.close.assert_called_once()

    @patch('services.music_manager.main.event_service')
    def test_ok_when_select_1_answers(self, mock_events):
        mock_events.is_alive.return_value = True
        conn = MagicMock()
        with patch.object(services.music_manager.database.pymysql, 'connect', return_value=conn) as connect:
            response = self.client.get('/health')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['database'], 'ok')
        conn.cursor.return_value.__enter__.return_value.execute.assert_called_once_with('SELECT 1')
        # Short timeouts on the probe's own connection, never the pool's.
        self.assertEqual(
            connect.call_args.kwargs['read_timeout'], services.music_manager.database.HEALTH_TIMEOUT_SECONDS
        )

    @patch('services.music_manager.main.event_service')
    def test_answers_within_the_bound_when_the_pool_is_exhausted_and_the_probe_hangs(self, mock_events):
        """An exhausted pool used to make /health wait forever. Neither may hold it up now."""
        mock_events.is_alive.return_value = True
        release = threading.Event()
        self.addCleanup(release.set)
        exhausted_pool = MagicMock()
        exhausted_pool.connection.side_effect = lambda: release.wait(30)
        with (
            patch.object(services.music_manager.database, '_pool', exhausted_pool),
            patch.object(services.music_manager.database.pymysql, 'connect', side_effect=lambda **_: release.wait(30)),
        ):
            started = time.monotonic()
            response = self.client.get('/health')
            elapsed = time.monotonic() - started

        self.assertLess(elapsed, 3.5)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['database'], 'unreachable')


class BackupHealthTest(unittest.TestCase):
    """De monitor die van buiten de host kijkt of er nog gebackupt wordt.

    Los van /health, want een verlopen backup is een echt probleem maar geen
    storing van de dienst.
    """

    def setUp(self):
        self.client = TestClient(app)
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dest = Path(self.tmp.name)

    def _latest(self, age_hours: float):
        finished = datetime.now(UTC) - timedelta(hours=age_hours)
        (self.dest / 'latest.json').write_text(
            json.dumps(
                {
                    'file': 'muma_db_20260831_031200.sql.gz',
                    'finished_at': finished.isoformat(),
                    'tables': 72,
                }
            )
        )

    def _env(self, **extra):
        env = {'BACKUP_PATH': str(self.dest), 'BACKUP_STALE_AFTER_HOURS': '36'}
        env.update(extra)
        return patch.dict('os.environ', env, clear=False)

    def test_recent_backup_reports_ok(self):
        self._latest(age_hours=5)
        with self._env():
            response = self.client.get('/health/backup')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['status'], 'ok')
        self.assertEqual(body['tables'], 72)
        self.assertLess(body['age_hours'], 36)

    def test_stale_backup_returns_503_so_an_outside_monitor_notices(self):
        self._latest(age_hours=40)
        with self._env():
            response = self.client.get('/health/backup')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['status'], 'stale')

    def test_missing_latest_json_is_not_silently_ok(self):
        """Nooit gedraaid en verlopen moeten allebei alarm geven, niet groen."""
        with self._env():
            response = self.client.get('/health/backup')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['status'], 'missing')

    def test_unset_backup_path_is_reported_rather_than_assumed_fine(self):
        with patch.dict('os.environ', {}, clear=False):
            os.environ.pop('BACKUP_PATH', None)
            response = self.client.get('/health/backup')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['status'], 'unconfigured')

    def test_unreadable_latest_json_is_reported(self):
        (self.dest / 'latest.json').write_text('{not json')
        with self._env():
            response = self.client.get('/health/backup')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['status'], 'unreadable')
