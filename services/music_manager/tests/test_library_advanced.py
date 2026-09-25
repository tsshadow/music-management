import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector')


import services.music_manager.routers.users
from services.music_manager.api_key import resolve_system_api_key

services.music_manager.routers.users.run_lms_db_sync = lambda: None
import services.music_manager.database

services.music_manager.database.get_db_connection = MagicMock(return_value=None)
from fastapi.testclient import TestClient

from services.music_manager.main import app

API_KEY = resolve_system_api_key()

# The five columns that never existed in production. Selecting them made every
# request fail with ERROR 1054, which the frontend rendered as "no results".
REMOVED_COLUMNS = ('musical_key', 'energy', 'danceability', 'valence', 'popularity')


class LibraryAdvancedTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.headers = {'x-api-key': API_KEY}

    def _mock(self, mock_get_db, rows=None):
        conn, cursor = MagicMock(), MagicMock()
        mock_get_db.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchall.return_value = rows if rows is not None else []
        cursor.fetchone.return_value = {'total': 0}
        return cursor

    @patch('services.music_manager.routers.library.get_db_connection')
    def test_query_names_no_column_that_does_not_exist(self, mock_get_db):
        cursor = self._mock(mock_get_db)
        self.client.get('/api/library/advanced', headers=self.headers)
        sql = ' '.join(str(call.args[0]) for call in cursor.execute.call_args_list)
        for column in REMOVED_COLUMNS:
            self.assertNotIn(column, sql, f'{column} does not exist in production')

    @patch('services.music_manager.routers.library.get_db_connection')
    def test_response_carries_duration_and_release_year(self, mock_get_db):
        self._mock(
            mock_get_db,
            rows=[
                {
                    'id': 1,
                    'title': 'Track',
                    'artist': 'Angerfist',
                    'label': 'Footworxx',
                    'genres': 'Hardcore,Uptempo Hardcore',
                    'bpm': 190.0,
                    'release_year': 2024,
                    'duration_secs': 312.0,
                    'file_path': '/mnt/music/a.mp3',
                    'created_at': '2026-07-01 10:00:00',
                }
            ],
        )
        res = self.client.get('/api/library/advanced', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        track = res.json()['tracks'][0]
        self.assertEqual(track['duration_secs'], 312.0)
        self.assertEqual(track['release_year'], 2024)
        self.assertEqual(track['genres'], ['Hardcore', 'Uptempo Hardcore'])
        for column in REMOVED_COLUMNS:
            self.assertNotIn(column, track)

    @patch('services.music_manager.routers.library.get_db_connection')
    def test_null_genres_become_an_empty_list(self, mock_get_db):
        self._mock(
            mock_get_db,
            rows=[
                {
                    'id': 1,
                    'title': 'Track',
                    'artist': None,
                    'label': None,
                    'genres': None,
                    'bpm': None,
                    'release_year': None,
                    'duration_secs': None,
                    'file_path': None,
                    'created_at': '2026-07-01 10:00:00',
                }
            ],
        )
        res = self.client.get('/api/library/advanced', headers=self.headers)
        self.assertEqual(res.json()['tracks'][0]['genres'], [])

    @patch('services.music_manager.routers.library.get_db_connection')
    def test_page_parameter_drives_the_offset(self, mock_get_db):
        cursor = self._mock(mock_get_db)
        self.client.get('/api/library/advanced?page=3&limit=50', headers=self.headers)
        first_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(tuple(first_params[-2:]), (50, 100))

    @patch('services.music_manager.routers.library.get_db_connection')
    def test_no_matches_is_200_with_an_empty_list(self, mock_get_db):
        self._mock(mock_get_db)
        res = self.client.get('/api/library/advanced?genre=Nope', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['tracks'], [])
        self.assertEqual(res.json()['total'], 0)

    @patch('services.music_manager.routers.library.get_db_connection')
    def test_filter_values_are_passed_as_bound_parameters(self, mock_get_db):
        cursor = self._mock(mock_get_db)
        self.client.get('/api/library/advanced?genre=Hardcore', headers=self.headers)
        sql, params = cursor.execute.call_args_list[0].args
        self.assertNotIn('Hardcore', sql)
        self.assertIn('Hardcore', params)

    @patch('services.music_manager.routers.library.get_db_connection')
    def test_curated_away_genres_are_not_listed_on_a_track(self, mock_get_db):
        cursor = self._mock(mock_get_db)
        self.client.get('/api/library/advanced', headers=self.headers)
        self.assertIn("rg.state <> 'black'", cursor.execute.call_args_list[0].args[0])

    def test_missing_api_key_is_401(self):
        self.assertEqual(self.client.get('/api/library/advanced').status_code, 401)

    @patch('services.music_manager.routers.library.get_db_connection')
    def test_release_date_is_selected(self, mock_get_db):
        cursor = self._mock(mock_get_db)
        self.client.get('/api/library/advanced', headers=self.headers)
        self.assertIn('af.release_date', cursor.execute.call_args_list[0].args[0])

    @patch('services.music_manager.routers.library.get_db_connection')
    def test_default_sort_is_newest_added_first(self, mock_get_db):
        cursor = self._mock(mock_get_db)
        self.client.get('/api/library/advanced', headers=self.headers)
        self.assertIn('ORDER BY t.created_at DESC', cursor.execute.call_args_list[0].args[0])

    @patch('services.music_manager.routers.library.get_db_connection')
    def test_sorting_by_release_puts_unknown_dates_last(self, mock_get_db):
        cursor = self._mock(mock_get_db)
        self.client.get('/api/library/advanced?sort=release&direction=desc', headers=self.headers)
        sql = cursor.execute.call_args_list[0].args[0]
        self.assertIn('af.release_date IS NULL', sql)
        self.assertIn('af.release_date DESC', sql)

    @patch('services.music_manager.routers.library.get_db_connection')
    def test_an_unknown_sort_key_falls_back_to_the_default(self, mock_get_db):
        """The sort key reaches the SQL as an expression, so only a whitelist may decide it."""
        cursor = self._mock(mock_get_db)
        self.client.get('/api/library/advanced?sort=%3B+DROP+TABLE+library_tracks--', headers=self.headers)
        sql = cursor.execute.call_args_list[0].args[0]
        self.assertIn('ORDER BY t.created_at DESC', sql)
        self.assertNotIn('DROP', sql)


class LibraryGenresTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.headers = {'x-api-key': API_KEY}

    def _mock(self, mock_get_db, rows):
        conn, cursor = MagicMock(), MagicMock()
        mock_get_db.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchall.return_value = rows
        return cursor

    @patch('services.music_manager.routers.library.get_db_connection')
    def test_genres_carry_state_and_count(self, mock_get_db):
        self._mock(
            mock_get_db,
            [
                {'genre': 'Hardcore', 'state': 'white', 'count': 9001},
                {'genre': 'zaagtempo', 'state': 'unknown', 'count': 12},
            ],
        )
        res = self.client.get('/api/library/genres', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        # The tint travels with the row: both clients draw a genre as a coloured tile and neither
        # of them owns the colour.
        self.assertEqual(
            res.json()[0],
            {'genre': 'Hardcore', 'state': 'white', 'count': 9001, 'tint': '#e5002b'},
        )

    @patch('services.music_manager.routers.library.get_db_connection')
    def test_black_genres_are_excluded_by_the_query(self, mock_get_db):
        cursor = self._mock(mock_get_db, [])
        self.client.get('/api/library/genres', headers=self.headers)
        self.assertIn("state <> 'black'", cursor.execute.call_args.args[0])

    @patch('services.music_manager.routers.library.get_db_connection')
    def test_it_joins_the_table_the_scanner_now_writes(self, mock_get_db):
        cursor = self._mock(mock_get_db, [])
        self.client.get('/api/library/genres', headers=self.headers)
        self.assertIn('library_track_genres', cursor.execute.call_args.args[0])

    def test_missing_api_key_is_401(self):
        self.assertEqual(self.client.get('/api/library/genres').status_code, 401)


if __name__ == '__main__':
    unittest.main()
