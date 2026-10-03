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


class TestStats(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.api_key = resolve_system_api_key()

    def _mock(self, mock_get_db, fetchall):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [
            {'count': 10, 'non_music': 2},  # total tracks, of which non-music
            {'count': 5},  # total artists
            {'avg_dur': 200.0},  # avg duration
            {'count': 8},  # matched count
            None,  # scrobble_listens table check
            None,  # scrobble_unmatched_listens table check
        ]
        mock_cursor.fetchall.side_effect = fetchall
        return mock_cursor

    @patch('services.music_manager.routers.stats.get_db_connection')
    def test_top_genres_come_from_library_track_genres(self, mock_get_db):
        self._mock(
            mock_get_db,
            [
                [{'name': 'Artist 1', 'track_count': 5}],  # top_artists
                [{'genre': 'Hardstyle', 'count': 2}, {'genre': 'Terror', 'count': 1}],  # top_genres
                [{'title': 'Track 1', 'artist': 'Artist 1', 'created_at': '2026-07-28'}],
            ],
        )
        response = self.client.get('/api/stats/', headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()['top_genres'], [{'genre': 'Hardstyle', 'count': 2}, {'genre': 'Terror', 'count': 1}]
        )

    @patch('services.music_manager.routers.stats.get_db_connection')
    def test_non_music_is_counted_apart_from_the_tracks(self, mock_get_db):
        cursor = self._mock(mock_get_db, [[], [], []])
        body = self.client.get('/api/stats/', headers={'x-api-key': self.api_key}).json()
        self.assertEqual((body['total_tracks'], body['total_non_music']), (8, 2))
        sql, params = cursor.execute.call_args_list[0].args
        self.assertIn('SUM(form IN (%s, %s))', sql)
        self.assertEqual(params, ('interview', 'preview'))

    @patch('services.music_manager.routers.stats.get_db_connection')
    def test_ml_genre_is_not_consulted(self, mock_get_db):
        cursor = self._mock(mock_get_db, [[], [], []])
        self.client.get('/api/stats/', headers={'x-api-key': self.api_key})
        genre_sql = [
            str(c.args[0])
            for c in cursor.execute.call_args_list
            if 'library_track_genres' in str(c.args[0]) and 'GROUP BY' in str(c.args[0])
        ]
        self.assertTrue(genre_sql, 'top_genres should query library_track_genres')
        self.assertNotIn('ml_genre', genre_sql[0])

    @patch('services.music_manager.routers.stats.get_db_connection')
    def test_curated_away_genres_are_excluded(self, mock_get_db):
        cursor = self._mock(mock_get_db, [[], [], []])
        self.client.get('/api/stats/', headers={'x-api-key': self.api_key})
        genre_sql = [
            str(c.args[0])
            for c in cursor.execute.call_args_list
            if 'library_track_genres' in str(c.args[0]) and 'GROUP BY' in str(c.args[0])
        ]
        self.assertIn("g.state <> 'black'", genre_sql[0])


if __name__ == '__main__':
    unittest.main()
