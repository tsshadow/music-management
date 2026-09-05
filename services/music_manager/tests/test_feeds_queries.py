import unittest
from datetime import datetime, timedelta

from services.music_manager.feeds.policy import POLICIES
from services.music_manager.feeds.queries import (
    candidates_query,
    dominant_genre_query,
    listens_query,
)

NOW = datetime(2026, 9, 5, 12, 0, 0)


class ListensQueryTest(unittest.TestCase):
    def test_a_user_query_filters_on_the_username(self):
        sql, params = listens_query('user', 90, NOW)
        self.assertIn('s.username = %s', sql)
        self.assertEqual(params[0], 'user')

    def test_the_server_profile_reads_everyone(self):
        sql, _ = listens_query(None, 90, NOW)
        self.assertNotIn('s.username = %s', sql)

    def test_black_genres_never_enter_the_profile(self):
        sql, _ = listens_query('user', 90, NOW)
        self.assertIn("rg.state <> 'black'", sql)

    def test_the_window_cutoff_is_computed_in_python_not_sql(self):
        sql, params = listens_query('user', 90, NOW)
        self.assertNotIn('NOW()', sql)
        self.assertIn(NOW - timedelta(days=90), params)


class CandidatesQueryTest(unittest.TestCase):
    def test_a_release_window_demands_day_precision(self):
        sql, _ = candidates_query('user', POLICIES['release-radar'], NOW)
        self.assertIn('LENGTH(af.release_date) = 10', sql)

    def test_the_added_date_is_never_a_release_date(self):
        sql, _ = candidates_query('user', POLICIES['release-radar'], NOW)
        self.assertNotIn('created_at', sql)

    def test_audio_features_join_on_the_internal_track_id(self):
        sql, _ = candidates_query('user', POLICIES['release-radar'], NOW)
        self.assertIn('internal_track_id', sql)
        self.assertNotIn('af.track_id = t.track_uid', sql)

    def test_the_rating_join_carries_all_three_key_columns(self):
        sql, _ = candidates_query('user', POLICIES['release-radar'], NOW)
        self.assertIn("r.entity_type = 'track'", sql)
        self.assertIn('r.entity_id = t.track_uid', sql)
        self.assertIn('r.username = %s', sql)

    def test_a_rating_is_not_a_filter_on_the_radar(self):
        sql, _ = candidates_query('user', POLICIES['release-radar'], NOW)
        self.assertNotIn('r.rating >=', sql)

    def test_the_daily_mix_pools_are_one_or_group(self):
        sql, _ = candidates_query('user', POLICIES['daily-mix'], NOW)
        self.assertIn('OR', sql)
        self.assertIn('r.rating >= %s', sql)
        self.assertIn('NOT EXISTS', sql)

    def test_only_songs_compete(self):
        sql, params = candidates_query('user', POLICIES['release-radar'], NOW)
        self.assertIn('t.duration_secs < %s', sql)
        self.assertIn(600, params)

    def test_a_candidate_must_have_a_file(self):
        sql, _ = candidates_query('user', POLICIES['release-radar'], NOW)
        self.assertIn('library_media_files', sql)


class DominantGenreQueryTest(unittest.TestCase):
    def test_the_label_variant_groups_by_label(self):
        self.assertIn('library_track_labels', dominant_genre_query('label'))

    def test_an_unknown_dimension_is_refused_rather_than_interpolated(self):
        with self.assertRaises(ValueError):
            dominant_genre_query('; DROP TABLE library_tracks')
