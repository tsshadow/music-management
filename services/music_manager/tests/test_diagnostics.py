import sys
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.easyid3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())

import services.music_manager.routers.users
from services.music_manager.api_key import resolve_system_api_key

services.music_manager.routers.users.run_lms_db_sync = lambda: None
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


if __name__ == '__main__':
    unittest.main()
