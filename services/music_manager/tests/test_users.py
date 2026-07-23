import unittest
from unittest.mock import MagicMock, patch
import os
import sys
import json

# Mock external modules to avoid import errors
sys.modules['dbutils'] = MagicMock()
sys.modules['dbutils.pooled_db'] = MagicMock()
sys.modules['pymysql'] = MagicMock()
sys.modules['mutagen'] = MagicMock()
sys.modules['mutagen.easyid3'] = MagicMock()
sys.modules['markdown'] = MagicMock()

import services.music_manager.ntfy_listener
services.music_manager.ntfy_listener.start_ntfy_listener = lambda: None
import services.music_manager.routers.users
services.music_manager.routers.users.run_lms_db_sync = lambda: None
import services.music_manager.database
services.music_manager.database.get_db_connection = MagicMock(return_value=None)

from fastapi.testclient import TestClient
from services.music_manager.main import app

class TestUsers(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.api_key = os.getenv('API_KEY') or os.getenv('MUMA_API_KEY') or '00000000-0000-4000-8000-000000000000'

    @patch('services.music_manager.routers.users.get_db_connection')
    def test_update_password_post_works(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        payload = {'password': 'newpassword123'}
        response = self.client.post('/api/users/1/password', json=payload, headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    @patch('services.music_manager.routers.users.get_db_connection')
    def test_update_password_put_works(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        payload = {'password': 'newpassword123'}
        response = self.client.put('/api/users/1/password', json=payload, headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

if __name__ == '__main__':
    unittest.main()
