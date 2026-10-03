import unittest
from datetime import datetime
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
    '/api/listening/top-genres',
    '/api/listening/years',
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
        body = self.client.get('/api/listening/timeline?bucket=day&tz=Europe/Amsterdam', headers=self.headers).json()

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

    # --- genre and release-year breakdowns and filters ---------------------------

    def test_a_malformed_year_is_refused(self):
        for query in ('year=abc', 'year=12', 'year=20155', 'year_from=99'):
            res = self.client.get(f'/api/listening/summary?{query}', headers=self.headers)
            self.assertEqual(res.status_code, 400 if query.startswith('year=') else 422, query)

    def test_a_backwards_year_range_is_refused(self):
        res = self.client.get('/api/listening/summary?year_from=2020&year_to=2010', headers=self.headers)
        self.assertEqual(res.status_code, 400)

    def test_too_many_filter_values_are_refused(self):
        query = '&'.join(f'genre=g{i}' for i in range(listening.MAX_FILTER_VALUES + 1))
        res = self.client.get(f'/api/listening/summary?{query}', headers=self.headers)
        self.assertEqual(res.status_code, 400)

    def test_filter_values_are_trimmed_deduplicated_and_blank_ones_dropped(self):
        parsed = listening.parse_track_filter(
            [' Hardstyle ', 'Hardstyle', '', '  '], ['2019', 'UNKNOWN', '2015', '2019', ''], None, None
        )
        self.assertEqual(parsed.genres, ('Hardstyle',))
        self.assertEqual(parsed.years, (2015, 2019))
        self.assertTrue(parsed.unknown_year)
        self.assertFalse(listening.parse_track_filter(['', ' '], [''], None, None).active)

    @patch('services.music_manager.routers.listening.get_db_connection')
    def test_genres_are_alternatives_and_years_are_a_second_condition(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        cursor.fetchall.return_value = []
        cursor.fetchone.return_value = {'unmatched': 0}
        self.client.get(
            '/api/listening/top-artists?genre=Hardstyle&genre=Uptempo+Hardcore&year=2012&year_from=2015&year_to=2019',
            headers=self.headers,
        )
        sql, params = cursor.execute.call_args_list[0][0]
        # One EXISTS per dimension, joined by AND; OR only inside each.
        self.assertIn('fr.name IN (%s, %s)', sql)
        self.assertIn("fr.state <> 'black'", sql)
        self.assertIn('BETWEEN %s AND %s', sql)
        self.assertIn(' OR ', sql)
        self.assertEqual(sql.count('EXISTS (SELECT 1 FROM library_track_genres fg'), 1)
        self.assertEqual(sql.count('EXISTS (SELECT 1 FROM library_tracks ft'), 1)
        self.assertEqual(list(params), ['Hardstyle', 'Uptempo Hardcore', 2012, 2015, 2019, 20])

    @patch('services.music_manager.routers.listening.get_db_connection')
    def test_the_unknown_year_is_selectable(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        cursor.fetchall.return_value = []
        self.client.get('/api/listening/clock?year=unknown', headers=self.headers)
        sql, _params = cursor.execute.call_args[0]
        self.assertIn('IS NULL', sql)

    @patch('services.music_manager.routers.listening.get_db_connection')
    def test_a_filter_excludes_the_unmatched_listens_and_says_how_many(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        cursor.fetchone.side_effect = [
            {
                'listens': 40,
                'tracks': 10,
                'artists': 4,
                'measured_listens': 2,
                'imputed_listens': 38,
                'measured_secs': 400,
                'imputed_secs': 9000,
                'first_listen': None,
                'last_listen': None,
            },
            # The unmatched query runs over who and when only, so it still sees them.
            {'listens': 300, 'measured_listens': 5, 'measured_secs': 900, 'first_listen': None, 'last_listen': None},
        ]
        body = self.client.get('/api/listening/summary?genre=Hardstyle', headers=self.headers).json()

        self.assertTrue(body['filtered'])
        self.assertEqual(body['excluded_unmatched'], 300)
        # Nothing of the excluded listens leaks into the totals.
        self.assertEqual(body['listens'], 40)
        self.assertEqual(body['unmatched'], 0)
        self.assertEqual(body['unmatched_share'], 0)
        self.assertEqual(body['measured_secs'], 400)
        self.assertEqual(body['unknown_duration_listens'], 0)
        matched_sql = cursor.execute.call_args_list[0][0][0]
        unmatched_sql = cursor.execute.call_args_list[1][0][0]
        self.assertIn('library_track_genres', matched_sql)
        self.assertNotIn('library_track_genres', unmatched_sql)

    @patch('services.music_manager.routers.listening.get_db_connection')
    def test_without_a_filter_nothing_is_reported_excluded(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        cursor.fetchone.side_effect = [
            {'listens': 40, 'tracks': 10, 'artists': 4},
            {'listens': 60},
        ]
        body = self.client.get('/api/listening/summary', headers=self.headers).json()
        self.assertFalse(body['filtered'])
        self.assertEqual(body['excluded_unmatched'], 0)
        self.assertEqual(body['unmatched'], 60)

    @patch('services.music_manager.routers.listening.get_db_connection')
    def test_a_filtered_timeline_reads_no_unmatched_listens(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        cursor.fetchall.return_value = []
        self.client.get('/api/listening/timeline?year_from=2015', headers=self.headers)
        sql, _params = cursor.execute.call_args[0]
        unmatched_part = sql.split('FROM scrobble_unmatched_listens')[1]
        self.assertIn('1=0', unmatched_part)
        self.assertIn('scrobble_listens.track_id', sql.split('FROM scrobble_unmatched_listens')[0])

    @patch('services.music_manager.routers.listening.get_db_connection')
    def test_a_filtered_ranking_moves_the_unmatched_count_to_excluded(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        cursor.fetchall.return_value = []
        cursor.fetchone.return_value = {'unmatched': 33461}
        body = self.client.get('/api/listening/top-labels?year=2019', headers=self.headers).json()
        self.assertEqual(body['unmatched'], 0)
        self.assertEqual(body['excluded_unmatched'], 33461)

    @patch('services.music_manager.routers.listening.get_db_connection')
    def test_top_genres_overlap_and_say_so_with_numbers(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        # One track tagged Hardcore and Uptempo Hardcore, played ten times, counts ten in each.
        cursor.fetchall.return_value = [
            {'genre_id': 1, 'genre': 'Hardcore', 'listens': 10, 'tracks': 1},
            {'genre_id': 2, 'genre': 'Uptempo Hardcore', 'listens': 10, 'tracks': 1},
        ]
        cursor.fetchone.side_effect = [{'matched': 12, 'untagged': 2}, {'unmatched': 50}]
        body = self.client.get('/api/listening/top-genres', headers=self.headers).json()

        self.assertEqual(body['matched'], 12)
        self.assertEqual(body['untagged'], 2)
        self.assertEqual(body['unmatched'], 50)
        self.assertEqual(body['excluded_unmatched'], 0)
        self.assertGreater(sum(g['listens'] for g in body['genres']), body['matched'])
        sql = cursor.execute.call_args_list[0][0][0]
        self.assertIn("rg.state <> 'black'", sql)

    def test_top_genres_allows_a_limit_large_enough_for_the_picker(self):
        res = self.client.get(f'/api/listening/top-genres?limit={listening.MAX_GENRE_LIMIT + 1}', headers=self.headers)
        self.assertEqual(res.status_code, 422)

    @patch('services.music_manager.routers.listening.get_db_connection')
    def test_years_put_undated_tracks_in_unknown_and_add_up(self, mock_get_db):
        cursor = mocked_db(mock_get_db)
        cursor.fetchall.return_value = [
            {'year': None, 'listens': 7, 'tracks': 3},
            {'year': 2015, 'listens': 20, 'tracks': 5},
            {'year': 2019, 'listens': 13, 'tracks': 4},
        ]
        cursor.fetchone.return_value = {'unmatched': 99}
        body = self.client.get('/api/listening/years?genre=Hardstyle', headers=self.headers).json()

        self.assertEqual(body['unknown'], {'listens': 7, 'tracks': 3})
        self.assertEqual([y['year'] for y in body['years']], [2015, 2019])
        self.assertEqual(body['matched'], 40)
        self.assertEqual(body['excluded_unmatched'], 99)
        sql = cursor.execute.call_args_list[0][0][0]
        # The feeds' release-date source: the servers' date, the analyzer's only when it is NULL.
        self.assertIn('t.release_date IS NULL', sql)
        self.assertIn('library_track_audio_features', sql)

    @patch('services.music_manager.routers.listening.get_db_connection')
    def test_a_user_key_may_not_read_another_history_through_the_new_endpoints(self, mock_get_db):
        mocked_db(mock_get_db)
        as_user()
        for path in ('/api/listening/top-genres', '/api/listening/years'):
            res = self.client.get(f'{path}?username=someone_else&genre=Hardstyle', headers=self.headers)
            self.assertEqual(res.status_code, 403, path)

    def test_release_year_sql_prefers_the_servers_date_over_the_analyzers(self):
        sql = listening.release_year_sql('t')
        self.assertIn("CASE WHEN t.release_date IS NULL THEN (SELECT", sql)
        self.assertIn("ELSE NULLIF(t.release_date, '')", sql)
        self.assertIn("REGEXP '^[0-9]{4}'", sql)


if __name__ == '__main__':
    unittest.main()
