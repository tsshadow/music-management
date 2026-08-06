import sys
import threading
import unittest
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
    @patch('services.music_manager.main.get_db_connection')
    def test_healthy_when_database_and_threads_are_up(self, mock_get_db, mock_events):
        mock_get_db.return_value = MagicMock()
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

    @patch('services.music_manager.main.event_service')
    @patch('services.music_manager.main.get_db_connection')
    def test_degraded_with_503_when_database_is_gone(self, mock_get_db, mock_events):
        mock_get_db.return_value = None
        mock_events.is_alive.return_value = True

        response = self.client.get('/health')

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['status'], 'degraded')
        self.assertEqual(response.json()['database'], 'unreachable')

    @patch('services.music_manager.main.event_service')
    @patch('services.music_manager.main.get_db_connection')
    def test_degraded_with_503_when_database_raises(self, mock_get_db, mock_events):
        mock_get_db.side_effect = Exception('pool kan geen connectie geven')
        mock_events.is_alive.return_value = True

        response = self.client.get('/health')

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['status'], 'degraded')
        self.assertEqual(response.json()['database'], 'unreachable')

    @patch('services.music_manager.main.event_service')
    @patch('services.music_manager.main.get_db_connection')
    def test_degraded_when_a_thread_died(self, mock_get_db, mock_events):
        mock_get_db.return_value = MagicMock()
        mock_events.is_alive.return_value = True
        thread = thread_registry.start_thread('scanner', lambda: None)
        thread.join(timeout=2)

        response = self.client.get('/health')

        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()['threads']['scanner'])

    @patch('services.music_manager.main.event_service')
    @patch('services.music_manager.main.get_db_connection')
    def test_degraded_when_the_event_worker_died(self, mock_get_db, mock_events):
        mock_get_db.return_value = MagicMock()
        mock_events.is_alive.return_value = False

        response = self.client.get('/health')

        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()['threads']['events'])
