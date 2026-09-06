import sys
import unittest
from datetime import datetime
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
from services.music_manager.routers import listening

API_KEY = resolve_system_api_key()

ALL_PATHS = (
    '/api/listening/summary',
    '/api/listening/timeline',
    '/api/listening/clock',
    '/api/listening/sources',
    '/api/listening/top-tracks',
    '/api/listening/top-artists',
    '/api/listening/top-labels',
)


def mocked_db(mock_get_db):
    conn, cursor = MagicMock(), MagicMock()
    mock_get_db.return_value = conn
    conn.cursor.return_value.__enter__.return_value = cursor
    return cursor


def as_user(username='user'):
    app.dependency_overrides[listening.verify_api_key] = lambda: {
        'status': 'ok',
        'type': 'user',
        'user': {'username': username},
    }


class ListeningTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.headers = {'x-api-key': API_KEY}

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_every_endpoint_rejects_a_missing_key(self):
        for path in ALL_PATHS:
            self.assertEqual(self.client.get(path).status_code, 401, path)

    @patch('services.music_manager.routers.listening.get_db_connection')
    def test_summary_counts_both_tables_and_keeps_the_durations_apart(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        cursor.fetchone.side_effect = [
            {
                'listens': 100,
                'tracks': 40,
                'artists': 12,
                'measured_listens': 10,
                'imputed_listens': 85,
                'measured_secs': 2000,
                'imputed_secs': 18000,
                'first_listen': datetime(2024, 3, 28, 5, 36),
                'last_listen': datetime(2026, 9, 6, 12, 0),
            },
            {
                'listens': 300,
                'measured_listens': 0,
                'measured_secs': 0,
                'first_listen': datetime(2024, 1, 1, 0, 0),
                'last_listen': datetime(2026, 9, 1, 0, 0),
            },
        ]
        body = self.client.get('/api/listening/summary', headers=self.headers).json()

        self.assertEqual(body['listens'], 400)
        self.assertEqual(body['matched'], 100)
        self.assertEqual(body['unmatched'], 300)
        self.assertEqual(body['unmatched_share'], 0.75)
        # Measured, imputed and unknown must not collapse into one number: 10 of
        # 400 listens reported a duration, 85 borrowed one from their track, and
        # the remaining 305 have no duration at all rather than a zero one.
        self.assertEqual(body['measured_secs'], 2000)
        self.assertEqual(body['imputed_secs'], 18000)
        self.assertEqual(body['estimated_secs'], 20000)
        self.assertEqual(body['measured_listens'], 10)
        self.assertEqual(body['imputed_listens'], 85)
        self.assertEqual(body['unknown_duration_listens'], 305)
        self.assertEqual(body['measured_share'], 0.025)
        # The window spans both tables, so the earliest listen is the unmatched one.
        self.assertEqual(body['first_listen'], '2024-01-01T00:00:00')
        self.assertEqual(body['last_listen'], '2026-09-06T12:00:00')

    @patch('services.music_manager.routers.listening.get_db_connection')
    def test_summary_of_an_empty_history_reports_no_share_rather_than_zero(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        empty = {
            'listens': 0,
            'tracks': 0,
            'artists': 0,
            'measured_listens': None,
            'imputed_listens': None,
            'measured_secs': 0,
            'imputed_secs': 0,
            'first_listen': None,
            'last_listen': None,
        }
        cursor.fetchone.side_effect = [empty, dict(empty)]
        body = self.client.get('/api/listening/summary', headers=self.headers).json()

        self.assertEqual(body['listens'], 0)
        self.assertIsNone(body['unmatched_share'])
        self.assertIsNone(body['measured_share'])
        self.assertIsNone(body['first_listen'])

    def test_timeline_rejects_an_unknown_bucket(self):
        res = self.client.get('/api/listening/timeline?bucket=fortnight', headers=self.headers)
        self.assertEqual(res.status_code, 400)

    def test_an_unknown_timezone_is_refused_rather_than_silently_utc(self):
        res = self.client.get('/api/listening/clock?tz=Mars/Olympus_Mons', headers=self.headers)
        self.assertEqual(res.status_code, 400)

    def test_a_backwards_date_range_is_refused(self):
        res = self.client.get('/api/listening/summary?from=2026-02-01&to=2026-01-01', headers=self.headers)
        self.assertEqual(res.status_code, 400)

    @patch('services.music_manager.routers.listening.get_db_connection')
    def test_a_local_day_is_bucketed_in_the_callers_zone(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        # 22:30 UTC on the 5th is 00:30 on the 6th in Amsterdam in summer. In UTC
        # this would be filed under the 5th, which is the bug the zone fixes.
        cursor.fetchall.return_value = [{'slot': '2026-09-05 22', 'matched': 4, 'unmatched': 1}]
        body = self.client.get(
            '/api/listening/timeline?bucket=day&tz=Europe/Amsterdam', headers=self.headers
        ).json()

        self.assertEqual(body['timezone'], 'Europe/Amsterdam')
        self.assertEqual(body['buckets'][0]['bucket'], '2026-09-06')
        self.assertEqual(body['buckets'][0]['listens'], 5)

    @patch('services.music_manager.routers.listening.get_db_connection')
    def test_the_same_offset_is_not_applied_to_a_winter_listen(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        # Amsterdam is UTC+1 in January and UTC+2 in July, so a fixed offset taken
        # from the browser in summer would file this January listen an hour late.
        cursor.fetchall.return_value = [
            {'slot': '2026-01-15 23', 'matched': 1, 'unmatched': 0},
            {'slot': '2026-07-15 23', 'matched': 1, 'unmatched': 0},
        ]
        body = self.client.get('/api/listening/clock?tz=Europe/Amsterdam', headers=self.headers).json()

        self.assertEqual(body['hours'][0], 1)  # 23:00 UTC in January -> 00:00 local
        self.assertEqual(body['hours'][1], 1)  # 23:00 UTC in July    -> 01:00 local

    @patch('services.music_manager.routers.listening.get_db_connection')
    def test_clock_returns_every_hour_and_weekday(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        cursor.fetchall.return_value = [
            {'slot': '2026-09-04 22', 'matched': 7, 'unmatched': 0},
            {'slot': '2026-09-05 22', 'matched': 2, 'unmatched': 1},
        ]
        body = self.client.get('/api/listening/clock', headers=self.headers).json()

        self.assertEqual(len(body['hours']), 24)
        self.assertEqual(len(body['weekdays']), 7)
        self.assertEqual(body['hours'][22], 10)
        self.assertEqual(body['hours'][0], 0)
        self.assertEqual(body['weekdays'][4], 7)  # 2026-09-04 is a Friday
        self.assertEqual(body['weekdays'][5], 3)

    @patch('services.music_manager.routers.listening.get_db_connection')
    def test_a_week_bucket_follows_the_iso_calendar(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        cursor.fetchall.return_value = [{'slot': '2025-12-31 12', 'matched': 2, 'unmatched': 0}]
        body = self.client.get('/api/listening/timeline?bucket=week', headers=self.headers).json()
        self.assertEqual(body['buckets'][0]['bucket'], '2026-W01')

    @patch('services.music_manager.routers.listening.get_db_connection')
    def test_top_tracks_reports_the_unmatched_listens_it_could_not_rank(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        cursor.fetchall.return_value = [
            {
                'track_id': 5,
                'title': 'Rocking Around',
                'artist': 'Nosferatu',
                'listens': 9,
                'estimated_secs': 1800,
                'last_listen': datetime(2026, 9, 5, 20, 0),
            }
        ]
        cursor.fetchone.return_value = {'unmatched': 33461}
        body = self.client.get('/api/listening/top-tracks', headers=self.headers).json()

        self.assertEqual(body['unmatched'], 33461)
        self.assertEqual(body['tracks'][0]['title'], 'Rocking Around')
        self.assertEqual(body['tracks'][0]['last_listen'], '2026-09-05T20:00:00')

    @patch('services.music_manager.routers.listening.get_db_connection')
    def test_a_user_key_may_not_read_another_history(self, mock_get_db):
        mocked_db(mock_get_db)
        as_user()
        res = self.client.get('/api/listening/summary?username=someone_else', headers=self.headers)
        self.assertEqual(res.status_code, 403)

    @patch('services.music_manager.routers.listening.get_db_connection')
    def test_a_user_key_scopes_to_itself_without_asking(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        cursor.fetchall.return_value = []
        cursor.fetchone.return_value = {'unmatched': 0}
        as_user()
        res = self.client.get('/api/listening/top-artists', headers=self.headers)

        self.assertEqual(res.status_code, 200)
        sql, params = cursor.execute.call_args_list[0][0]
        self.assertIn('username = %s', sql)
        self.assertEqual(params[0], 'user')

    @patch('services.music_manager.routers.listening.get_db_connection')
    def test_a_system_key_naming_nobody_asks_about_everybody(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        cursor.fetchall.return_value = []
        cursor.fetchone.return_value = {'unmatched': 0}
        self.client.get('/api/listening/top-artists', headers=self.headers)

        sql, _params = cursor.execute.call_args_list[0][0]
        self.assertNotIn('username = %s', sql)

    @patch('services.music_manager.routers.listening.get_db_connection')
    def test_a_date_range_is_bounded_by_local_midnights(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        cursor.fetchall.return_value = []
        self.client.get(
            '/api/listening/sources?from=2026-01-01&to=2026-01-31&tz=Europe/Amsterdam',
            headers=self.headers,
        )

        sql, params = cursor.execute.call_args[0]
        self.assertIn('listened_at >= %s', sql)
        self.assertIn('listened_at < %s', sql)
        # Amsterdam is UTC+1 in January, so the local midnight is 23:00 the day
        # before in the UTC column the query compares against.
        self.assertEqual(params[0], datetime(2025, 12, 31, 23, 0))
        self.assertEqual(params[1], datetime(2026, 1, 31, 23, 0))


if __name__ == '__main__':
    unittest.main()
