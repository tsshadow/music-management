import unittest
from unittest.mock import MagicMock, patch
import os
import sys
import json

# Mock PooledDB before importing any music_manager modules
sys.modules['dbutils'] = MagicMock()
sys.modules['dbutils.pooled_db'] = MagicMock()
sys.modules['pymysql'] = MagicMock()
sys.modules['mutagen'] = MagicMock()
sys.modules['mutagen.easyid3'] = MagicMock()
sys.modules['markdown'] = MagicMock()

# Avoid background tasks and real DB during import/startup
# pylint: disable=wrong-import-position,wrong-import-order
import services.music_manager.ntfy_listener
services.music_manager.ntfy_listener.start_ntfy_listener = lambda: None

import services.music_manager.routers.users
services.music_manager.routers.users.run_lms_db_sync = lambda: None

import services.music_manager.database
services.music_manager.database.get_db_connection = MagicMock(return_value=None)

# Now it should be safe to import app
from fastapi.testclient import TestClient
from services.music_manager.main import app

class TestRating(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        # Use the default API key from rating.py if not set in environment
        self.api_key = os.getenv("API_KEY") or os.getenv("MUMA_API_KEY") or "453ecd33-3cb2-4ca4-a531-1677330bbaee"

    @patch('services.music_manager.routers.rating.get_db_connection')
    def test_handle_lms_event_success(self, mock_get_db):
        # Mock DB connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        # Test data
        payload = {
            "event": "rating_changed",
            "object_type": "track",
            "object_id": "track123",
            "username": "teun",
            "rating": 80
        }

        response = self.client.post(
            "/rating/api/lms-event",
            json=payload,
            headers={"x-api-key": self.api_key}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "success", "entity_id": "track123"})

        # Verify SQL execution
        mock_cursor.execute.assert_called()
        # Find the call that contains INSERT INTO rating_tracks
        insert_call = next(call for call in mock_cursor.execute.call_args_list if "INSERT INTO rating_tracks" in call[0][0])
        self.assertIn("ON DUPLICATE KEY UPDATE", insert_call[0][0])
        self.assertEqual(insert_call[0][1], ("track", "track123", "teun", 80))

    @patch('services.music_manager.routers.rating.get_db_connection')
    def test_handle_lms_event_with_path_resolution(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        # Mock path resolution query
        mock_cursor.fetchone.return_value = {'track_uid': 'resolved-uid'}

        payload = {
            "event": "rating_changed",
            "object_type": "track",
            "object_id": "lms-id",
            "username": "teun",
            "rating": 90,
            "path": "/music/artist/album/song.mp3"
        }

        response = self.client.post(
            "/rating/api/lms-event",
            json=payload,
            headers={"x-api-key": self.api_key}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "success", "entity_id": "resolved-uid"})

        # Check that it tried to resolve the path
        path_res_call = next(call for call in mock_cursor.execute.call_args_list if "SELECT t.track_uid" in call[0][0])
        self.assertIn("library_media_files", path_res_call[0][0])

        # The first argument of the second call (the INSERT) should use the resolved-uid
        insert_call = next(call for call in mock_cursor.execute.call_args_list if "INSERT INTO rating_tracks" in call[0][0])
        self.assertEqual(insert_call[0][1][1], "resolved-uid")

    def test_handle_lms_event_invalid_event(self):
        payload = {
            "event": "some_other_event",
            "object_type": "track",
            "object_id": "123",
            "username": "teun",
            "rating": 50
        }
        response = self.client.post(
            "/rating/api/lms-event",
            json=payload,
            headers={"x-api-key": self.api_key}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ignored", "reason": "unsupported event type"})

    @patch('services.music_manager.routers.rating.get_db_connection')
    def test_handle_lms_event_db_failure(self, mock_get_db):
        mock_get_db.return_value = None

        payload = {
            "event": "rating_changed",
            "object_type": "track",
            "object_id": "123",
            "username": "teun",
            "rating": 50
        }
        response = self.client.post(
            "/rating/api/lms-event",
            json=payload,
            headers={"x-api-key": self.api_key}
        )
        self.assertEqual(response.status_code, 500)
        self.assertIn("Database connection failed", response.json()['detail'])

    def test_handle_lms_event_no_auth(self):
        payload = {
            "event": "rating_changed",
            "object_type": "track",
            "object_id": "123",
            "username": "teun",
            "rating": 50
        }
        response = self.client.post(
            "/rating/api/lms-event",
            json=payload
        )
        self.assertEqual(response.status_code, 401)

    @patch('services.music_manager.routers.users.get_db_connection')
    def test_get_playlist_tracks_with_rating_filter(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        # Mock user and playlist
        mock_cursor.fetchone.side_effect = [
            {'username': 'teun'}, # User lookup
            {'params': json.dumps({
                "rating_range": [80, 100],
                "genres": ["Trance"],
                "size": 100,
                "sort_method": "highest_rated"
            })} # Playlist params
        ]

        # We need a mock response for the main tracks query
        mock_cursor.fetchall.return_value = [
            {'id': 1, 'title': 'Track 1', 'artist': 'Artist 1', 'rating': 90}
        ]

        response = self.client.get(
            "/api/users/1/dynamic-playlists/1/tracks",
            headers={"x-api-key": self.api_key}
        )

        self.assertEqual(response.status_code, 200)

        # Verify SQL execution
        # Find the tracks query call
        tracks_query_call = next(call for call in mock_cursor.execute.call_args_list if "SELECT DISTINCT" in call[0][0])
        query = tracks_query_call[0][0]
        params = tracks_query_call[0][1]

        self.assertIn("rt.rating >= %s AND rt.rating <= %s", query)
        self.assertIn("ORDER BY rt.rating DESC", query)
        # params[0] is username, params[1], params[2] are genres, params[3], params[4] are genres (ml), params[5], params[6] are ratings
        # Actually it depends on how the query is built.
        self.assertIn(80, params)
        self.assertIn(100, params)

if __name__ == '__main__':
    unittest.main()
