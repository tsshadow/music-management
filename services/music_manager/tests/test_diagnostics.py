import hashlib
import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector')


import services.music_manager.routers.users
from services.music_manager.api_key import resolve_system_api_key

services.music_manager.routers.users.run_lms_db_sync = lambda only_sources=None: None
import services.music_manager.database

services.music_manager.database.get_db_connection = MagicMock(return_value=None)
from fastapi.testclient import TestClient

from services.music_manager.main import app


class TestDiagnostics(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.api_key = resolve_system_api_key()
        self.payload = {
            'device_model': 'Pixel 7',
            'os_version': '34',
            'app_version_name': '4.2.0',
            'app_version_code': 420,
            'build_type': 'release',
            'ring_buffer_text': 'log line 1\nlog line 2',
            'stacktrace_text': None,
        }

    @patch('services.music_manager.routers.diagnostics.get_db_connection')
    def test_create_crash_report_success(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.lastrowid = 7

        response = self.client.post(
            '/api/diagnostics/crash-reports', json=self.payload, headers={'x-api-key': self.api_key}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok', 'id': 7})
        insert_call = next(
            call for call in mock_cursor.execute.call_args_list if 'INSERT INTO crash_reports' in call[0][0]
        )
        self.assertIsNone(insert_call[0][1][0])  # user_id: system-key caller, no user
        self.assertEqual(insert_call[0][1][1], 'Pixel 7')

    @patch('services.music_manager.routers.diagnostics.get_db_connection')
    def test_create_crash_report_db_failure(self, mock_get_db):
        mock_get_db.return_value = None

        response = self.client.post(
            '/api/diagnostics/crash-reports', json=self.payload, headers={'x-api-key': self.api_key}
        )

        self.assertEqual(response.status_code, 500)

    def test_create_crash_report_no_auth(self):
        response = self.client.post('/api/diagnostics/crash-reports', json=self.payload)

        self.assertEqual(response.status_code, 401)

    @patch('services.music_manager.routers.diagnostics.get_db_connection')
    def test_create_stores_stacktrace_hash(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        payload = dict(self.payload, stacktrace_text='java.lang.NullPointerException\n  at Foo.bar')
        response = self.client.post('/api/diagnostics/crash-reports', json=payload, headers={'x-api-key': self.api_key})

        self.assertEqual(response.status_code, 200)
        insert_call = next(
            call for call in mock_cursor.execute.call_args_list if 'INSERT INTO crash_reports' in call[0][0]
        )
        expected = hashlib.sha256(payload['stacktrace_text'].encode('utf-8')).hexdigest()
        self.assertIn(expected, insert_call[0][1])

    @patch('services.music_manager.routers.diagnostics.get_db_connection')
    def test_create_without_stacktrace_stores_null_hash(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        response = self.client.post(
            '/api/diagnostics/crash-reports', json=self.payload, headers={'x-api-key': self.api_key}
        )

        self.assertEqual(response.status_code, 200)
        insert_call = next(
            call for call in mock_cursor.execute.call_args_list if 'INSERT INTO crash_reports' in call[0][0]
        )
        self.assertIsNone(insert_call[0][1][-1])  # stacktrace_hash

    @patch('services.music_manager.routers.diagnostics.threading.Thread')
    @patch('services.music_manager.routers.diagnostics.get_db_connection')
    def test_create_fires_hook_thread(self, mock_get_db, mock_thread):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.lastrowid = 12

        response = self.client.post(
            '/api/diagnostics/crash-reports', json=self.payload, headers={'x-api-key': self.api_key}
        )

        self.assertEqual(response.status_code, 200)
        _, kwargs = mock_thread.call_args
        self.assertEqual(kwargs['args'], (12,))
        mock_thread.return_value.start.assert_called_once()

    @patch('services.music_manager.routers.diagnostics.requests.post')
    def test_post_crash_hook_disabled_without_url(self, mock_post):
        from services.music_manager.routers import diagnostics

        with patch.object(diagnostics, '_settings') as mock_settings:
            mock_settings.get.return_value = ''
            diagnostics._post_crash_hook(12)

        mock_post.assert_not_called()

    @patch('services.music_manager.routers.diagnostics.requests.post')
    def test_post_crash_hook_posts_report_id(self, mock_post):
        from services.music_manager.routers import diagnostics

        with patch.object(diagnostics, '_settings') as mock_settings:
            mock_settings.get.return_value = 'http://192.0.2.40:9876/crash'
            diagnostics._post_crash_hook(12)

        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], 'http://192.0.2.40:9876/crash')
        self.assertEqual(kwargs['json'], {'id': 12})

    @patch('services.music_manager.routers.diagnostics.get_db_connection')
    def test_get_report_returns_row_for_system_key(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'id': 12, 'status': 'new', 'device_model': 'Pixel 7'}

        response = self.client.get('/api/diagnostics/crash-reports/12', headers={'x-api-key': self.api_key})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['id'], 12)

    @patch('services.music_manager.routers.diagnostics.get_db_connection')
    def test_get_report_404_when_missing(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        response = self.client.get('/api/diagnostics/crash-reports/999', headers={'x-api-key': self.api_key})

        self.assertEqual(response.status_code, 404)

    def test_get_report_403_for_user_key(self):
        with patch('services.music_manager.routers.users.verify_token') as mock_verify:
            mock_verify.return_value = {'status': 'ok', 'user': {'id': 3}}
            response = self.client.get('/api/diagnostics/crash-reports/12', headers={'x-api-key': 'some-user-key'})

        self.assertEqual(response.status_code, 403)

    @patch('services.music_manager.routers.diagnostics.get_db_connection')
    def test_patch_status_updates_row(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.rowcount = 1

        response = self.client.patch(
            '/api/diagnostics/crash-reports/12/status',
            json={'status': 'analyzing'},
            headers={'x-api-key': self.api_key},
        )

        self.assertEqual(response.status_code, 200)
        update_call = next(call for call in mock_cursor.execute.call_args_list if 'UPDATE crash_reports' in call[0][0])
        self.assertEqual(update_call[0][1], ('analyzing', 12))

    @patch('services.music_manager.routers.diagnostics.get_db_connection')
    def test_patch_status_rejects_unknown_value(self, mock_get_db):
        response = self.client.patch(
            '/api/diagnostics/crash-reports/12/status', json={'status': 'sideways'}, headers={'x-api-key': self.api_key}
        )

        self.assertEqual(response.status_code, 422)
        mock_get_db.assert_not_called()


if __name__ == '__main__':
    unittest.main()
