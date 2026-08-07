import os
import sys
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.easyid3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())

import services.music_manager.routers.users

services.music_manager.routers.users.run_lms_db_sync = lambda: None
import services.music_manager.database

services.music_manager.database.get_db_connection = MagicMock(return_value=None)
from fastapi.testclient import TestClient

from services.music_manager.main import app

API_KEY = os.getenv('API_KEY') or os.getenv('MUMA_API_KEY') or '00000000-0000-4000-8000-000000000000'

ALL_PATHS = (
    '/api/analytics/summary',
    '/api/analytics/genre-distribution',
    '/api/analytics/bpm-histogram',
    '/api/analytics/year-histogram',
    '/api/analytics/top-artists',
    '/api/analytics/top-labels',
    '/api/analytics/artist-search?q=an',
)


def mocked_db(mock_get_db):
    conn, cursor = MagicMock(), MagicMock()
    mock_get_db.return_value = conn
    conn.cursor.return_value.__enter__.return_value = cursor
    return cursor


class AnalyticsTest(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.headers = {'x-api-key': API_KEY}

    def test_every_endpoint_rejects_a_missing_key(self):
        for path in ALL_PATHS:
            self.assertEqual(self.client.get(path).status_code, 401, path)

    @patch('services.music_manager.routers.analytics.get_db_connection')
    def test_summary_reports_counts_and_coverage(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        cursor.fetchone.return_value = {
            'tracks': 100, 'artists': 20, 'labels': 5, 'genres': 8,
            'total_duration_secs': 36000.0,
            'with_bpm': 40, 'with_genre': 25, 'with_artist': 80, 'analyzed': 40,
        }
        res = self.client.get('/api/analytics/summary', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body['tracks'], 100)
        self.assertEqual(body['labels'], 5)
        self.assertEqual(body['genres'], 8)
        self.assertAlmostEqual(body['coverage']['bpm'], 0.4)
        self.assertAlmostEqual(body['coverage']['genre'], 0.25)
        self.assertAlmostEqual(body['coverage']['artist'], 0.8)

    @patch('services.music_manager.routers.analytics.get_db_connection')
    def test_summary_coverage_is_zero_when_no_tracks_match(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        cursor.fetchone.return_value = {
            'tracks': 0, 'artists': 0, 'labels': 0, 'genres': 0,
            'total_duration_secs': None,
            'with_bpm': 0, 'with_genre': 0, 'with_artist': 0, 'analyzed': 0,
        }
        res = self.client.get('/api/analytics/summary', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['coverage']['bpm'], 0)
        self.assertEqual(res.json()['total_duration_secs'], 0)

    @patch('services.music_manager.routers.analytics.get_db_connection')
    def test_genre_distribution_returns_rows(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        cursor.fetchall.return_value = [
            {'genre': 'Hardcore', 'state': 'white', 'count': 42},
            {'genre': 'zaagtempo', 'state': 'unknown', 'count': 3},
        ]
        res = self.client.get('/api/analytics/genre-distribution', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()[0], {'genre': 'Hardcore', 'state': 'white', 'count': 42})

    @patch('services.music_manager.routers.analytics.get_db_connection')
    def test_genre_distribution_excludes_curated_away_genres(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        cursor.fetchall.return_value = []
        self.client.get('/api/analytics/genre-distribution', headers=self.headers)
        self.assertIn("rg.state <> 'black'", cursor.execute.call_args.args[0])

    @patch('services.music_manager.routers.analytics.get_db_connection')
    def test_empty_result_is_200_with_an_empty_list(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        cursor.fetchall.return_value = []
        res = self.client.get('/api/analytics/genre-distribution?genre=Nope', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), [])

    @patch('services.music_manager.routers.analytics.get_db_connection')
    def test_bpm_histogram_returns_raw_buckets(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        cursor.fetchall.return_value = [
            {'bucket_start': 150.0, 'count': 31177},
            {'bucket_start': 190.0, 'count': 11421},
        ]
        res = self.client.get('/api/analytics/bpm-histogram?bucket=10', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()[0]['count'], 31177)

    def test_bpm_histogram_rejects_an_out_of_range_bucket(self):
        for bucket in (0, 51):
            res = self.client.get(f'/api/analytics/bpm-histogram?bucket={bucket}',
                                  headers=self.headers)
            self.assertEqual(res.status_code, 422)

    @patch('services.music_manager.routers.analytics.get_db_connection')
    def test_top_artists_honours_limit(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        cursor.fetchall.return_value = [{'artist': 'Angerfist', 'count': 300}]
        res = self.client.get('/api/analytics/top-artists?limit=1', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), [{'artist': 'Angerfist', 'count': 300}])

    def test_top_artists_rejects_a_limit_over_the_maximum(self):
        res = self.client.get('/api/analytics/top-artists?limit=201', headers=self.headers)
        self.assertEqual(res.status_code, 422)

    def test_artist_search_rejects_a_query_shorter_than_two_characters(self):
        res = self.client.get('/api/analytics/artist-search?q=a', headers=self.headers)
        self.assertEqual(res.status_code, 422)

    @patch('services.music_manager.routers.analytics.get_db_connection')
    def test_artist_search_returns_matches(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        cursor.fetchall.return_value = [{'artist': 'Angerfist', 'count': 300}]
        res = self.client.get('/api/analytics/artist-search?q=ang', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()[0]['artist'], 'Angerfist')

    @patch('services.music_manager.routers.analytics.get_db_connection')
    def test_year_histogram_returns_rows(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        cursor.fetchall.return_value = [{'year': 2024, 'count': 8836}]
        res = self.client.get('/api/analytics/year-histogram', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), [{'year': 2024, 'count': 8836}])

    @patch('services.music_manager.routers.analytics.get_db_connection')
    def test_top_labels_returns_rows(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        cursor.fetchall.return_value = [{'label': 'Footworxx', 'count': 1041}]
        res = self.client.get('/api/analytics/top-labels', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), [{'label': 'Footworxx', 'count': 1041}])

    @patch('services.music_manager.routers.analytics.get_db_connection')
    def test_filter_values_are_passed_as_bound_parameters(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        cursor.fetchall.return_value = []
        self.client.get('/api/analytics/top-artists?genre=Hardcore&bpm_min=190',
                        headers=self.headers)
        sql, params = cursor.execute.call_args.args
        self.assertNotIn('Hardcore', sql)
        self.assertIn('Hardcore', params)
        self.assertIn(190.0, params)

    @patch('services.music_manager.routers.analytics.get_db_connection')
    def test_database_unavailable_is_a_500(self, mock_get_db):
        mock_get_db.return_value = None
        res = self.client.get('/api/analytics/summary', headers=self.headers)
        self.assertEqual(res.status_code, 500)


if __name__ == '__main__':
    unittest.main()
