import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.easyid3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())
import services.music_manager.routers.users

services.music_manager.routers.users.run_lms_db_sync = lambda: None
import services.music_manager.database

services.music_manager.database.get_db_connection = MagicMock(return_value=None)
from fastapi.testclient import TestClient

from services.music_manager.main import app
from services.music_manager.routers.events import parse_since


class ParseSinceTest(unittest.TestCase):

    def test_relative_hours(self):
        result = parse_since('-2h')
        self.assertAlmostEqual((datetime.now() - result).total_seconds(), 7200, delta=5)

    def test_relative_days(self):
        result = parse_since('-7d')
        self.assertAlmostEqual((datetime.now() - result).total_seconds(), 604800, delta=5)

    def test_relative_minutes(self):
        result = parse_since('-30m')
        self.assertAlmostEqual((datetime.now() - result).total_seconds(), 1800, delta=5)

    def test_absolute_iso(self):
        self.assertEqual(parse_since('2026-08-01T12:00:00'), datetime(2026, 8, 1, 12, 0, 0))

    def test_nonsense_raises(self):
        with self.assertRaises(ValueError):
            parse_since('gisteren')


class EventsRouterTest(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.api_key = os.getenv('API_KEY') or os.getenv('MUMA_API_KEY') or '00000000-0000-4000-8000-000000000000'
        self.headers = {'x-api-key': self.api_key}

    def _mock_db(self, mock_get_db, rows=None, total=3, counts=None):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.side_effect = [
            rows if rows is not None else [],
            counts if counts is not None else [],
        ]
        mock_cursor.fetchone.return_value = {'total': total}
        return mock_cursor

    def test_requires_api_key(self):
        self.assertEqual(self.client.get('/api/events').status_code, 401)

    @patch('services.music_manager.routers.events.get_db_connection')
    def test_returns_events_total_and_counts(self, mock_get_db):
        self._mock_db(
            mock_get_db,
            rows=[{'id': 1, 'level': 'ERROR', 'source': 'downloader', 'title': 'stuk'}],
            total=1,
            counts=[{'level': 'ERROR', 'n': 1}],
        )

        response = self.client.get('/api/events', headers=self.headers)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body['events']), 1)
        self.assertEqual(body['total'], 1)
        self.assertEqual(body['counts']['ERROR'], 1)
        self.assertEqual(body['counts']['INFO'], 0)

    @patch('services.music_manager.routers.events.get_db_connection')
    def test_level_filter_is_a_set_not_a_threshold(self, mock_get_db):
        cursor = self._mock_db(mock_get_db)

        self.client.get('/api/events?level=ERROR&level=CRITICAL', headers=self.headers)

        sql, params = cursor.execute.call_args_list[0][0]
        self.assertIn('level IN (%s, %s)', sql)
        self.assertIn('ERROR', params)
        self.assertIn('CRITICAL', params)
        self.assertNotIn('WARNING', params)

    @patch('services.music_manager.routers.events.get_db_connection')
    def test_source_and_search_filters_combine(self, mock_get_db):
        cursor = self._mock_db(mock_get_db)

        self.client.get('/api/events?source=importer&q=mislukt', headers=self.headers)

        sql, params = cursor.execute.call_args_list[0][0]
        self.assertIn('source IN (%s)', sql)
        self.assertIn('(title LIKE %s OR message LIKE %s)', sql)
        self.assertIn('%mislukt%', params)

    @patch('services.music_manager.routers.events.get_db_connection')
    def test_since_filter_is_applied(self, mock_get_db):
        cursor = self._mock_db(mock_get_db)

        self.client.get('/api/events?since=-1h', headers=self.headers)

        sql, _params = cursor.execute.call_args_list[0][0]
        self.assertIn('created_at >= %s', sql)

    def test_invalid_since_gives_400(self):
        response = self.client.get('/api/events?since=gisteren', headers=self.headers)

        self.assertEqual(response.status_code, 400)

    @patch('services.music_manager.routers.events.get_db_connection')
    def test_limit_is_capped(self, mock_get_db):
        cursor = self._mock_db(mock_get_db)

        self.client.get('/api/events?limit=99999', headers=self.headers)

        _sql, params = cursor.execute.call_args_list[0][0]
        self.assertIn(1000, params)

    @patch('services.music_manager.routers.events.get_db_connection')
    def test_invalid_level_gives_400(self, mock_get_db):
        response = self.client.get('/api/events?level=TRACE', headers=self.headers)

        self.assertEqual(response.status_code, 400)

    @patch('services.music_manager.routers.events.get_db_connection')
    def test_invalid_source_gives_400(self, mock_get_db):
        response = self.client.get('/api/events?source=unknown-service', headers=self.headers)

        self.assertEqual(response.status_code, 400)

    @patch('services.music_manager.routers.events.get_db_connection')
    def test_delete_one(self, mock_get_db):
        cursor = self._mock_db(mock_get_db)

        response = self.client.delete('/api/events/12', headers=self.headers)

        self.assertEqual(response.status_code, 200)
        sql, params = cursor.execute.call_args[0]
        self.assertIn('DELETE FROM events WHERE id', sql)
        self.assertEqual(params, (12,))

    @patch('services.music_manager.routers.events.get_db_connection')
    def test_delete_all(self, mock_get_db):
        cursor = self._mock_db(mock_get_db)

        response = self.client.delete('/api/events', headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertIn('DELETE FROM events', cursor.execute.call_args[0][0])
