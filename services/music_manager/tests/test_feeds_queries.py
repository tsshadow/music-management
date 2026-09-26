import unittest
from datetime import datetime, timedelta

from services.music_manager.feeds.policy import POLICIES
from services.music_manager.feeds.queries import (
    candidates_query,
    canonical_rows_query,
    dominant_genre_query,
    entity_hardness_query,
    genre_hardness_query,
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

    def test_the_grouped_names_come_back_in_a_defined_order(self):
        """candidates_query orders its GROUP_CONCAT; this one has to agree, or

        the same track is described one way to the profile and another way to
        the ranker, and the difference shows up as an unreproducible profile
        rather than as an error.
        """
        sql = ' '.join(listens_query('user', 90, NOW)[0].split())
        self.assertIn('GROUP_CONCAT(l.name ORDER BY l.name SEPARATOR', sql)
        self.assertIn('GROUP_CONCAT(rg.name ORDER BY rg.name SEPARATOR', sql)

    def test_the_window_cutoff_is_computed_in_python_not_sql(self):
        sql, params = listens_query('user', 90, NOW)
        self.assertNotIn('NOW()', sql)
        self.assertIn(NOW - timedelta(days=90), params)


class CandidatesQueryTest(unittest.TestCase):
    def test_a_release_window_demands_day_precision(self):
        sql, _ = candidates_query('user', POLICIES['release-radar'], NOW)
        self.assertIn(
            "LENGTH(CASE WHEN t.release_date IS NULL THEN af.release_date ELSE NULLIF(t.release_date, '') END) = 10",
            sql,
        )

    def test_the_settled_track_date_is_preferred_over_the_audio_features_one(self):
        """`library_tracks.release_date` is what the servers read off the file, settled hourly

        by release_date_sync and covering the whole library. The audio-features column behind
        it only ever held what the ml-analyzer processed -- a quarter of the library, and on
        production nothing at all, which is why both feeds returned zero tracks. Preferring the
        wrong one of the two is a silently empty feed, so the order is asserted, not assumed.
        """
        sql, _ = candidates_query('user', POLICIES['release-radar'], NOW)
        self.assertIn(
            "CASE WHEN t.release_date IS NULL THEN af.release_date ELSE NULLIF(t.release_date, '') END AS release_date",
            sql,
        )

    def test_a_rejected_date_is_not_resurrected_by_the_audio_features_column(self):
        """A CASE and not a COALESCE. The sync writes the empty string when it has weighed every

        file on every server and found no date they agree on -- a decision, not a gap. COALESCE
        would treat it exactly like NULL and hand back the analyzer's value, which is the one
        the servers just contradicted. NULL alone means nobody holds the file, and only then is
        the older column worth reading.
        """
        sql, _ = candidates_query('user', POLICIES['release-radar'], NOW)
        self.assertNotIn("COALESCE(NULLIF(t.release_date", sql)
        self.assertIn("CASE WHEN t.release_date IS NULL THEN af.release_date", sql)

    def test_a_release_dated_in_the_future_is_outside_the_window(self):
        """`release_date` comes out of a file tag, so a track tagged 2027-01-01

        satisfies day precision and the lower bound, and step 7's
        release-descending order then pins it to the top of every radar for as
        long as it exists. The window is closed at `now` for exactly that.
        """
        sql, params = candidates_query('user', POLICIES['release-radar'], NOW)
        self.assertIn(
            "CASE WHEN t.release_date IS NULL THEN af.release_date ELSE NULLIF(t.release_date, '') END <= %s", sql
        )
        self.assertIn(NOW.date().isoformat(), params)
        lower = params.index((NOW.date() - timedelta(days=7)).isoformat())
        upper = params.index(NOW.date().isoformat())
        self.assertLess(lower, upper)

    def test_the_daily_mix_window_is_bounded_at_both_ends_too(self):
        sql, params = candidates_query('user', POLICIES['daily-mix'], NOW)
        self.assertIn(
            "CASE WHEN t.release_date IS NULL THEN af.release_date ELSE NULLIF(t.release_date, '') END >= %s", sql
        )
        self.assertIn(
            "CASE WHEN t.release_date IS NULL THEN af.release_date ELSE NULLIF(t.release_date, '') END <= %s", sql
        )
        self.assertIn((NOW.date() - timedelta(days=90)).isoformat(), params)
        self.assertIn(NOW.date().isoformat(), params)

    def test_the_bounds_admit_this_week_and_refuse_last_year_and_next_year(self):
        """The two bound parameters, applied the way MySQL applies them to a

        `DATE`-shaped string: lexical comparison on `YYYY-MM-DD` is the same
        ordering as chronological comparison, which is why a string bound is
        sound here at all.
        """
        _, params = candidates_query('user', POLICIES['release-radar'], NOW)
        lower = (NOW.date() - timedelta(days=7)).isoformat()
        upper = NOW.date().isoformat()
        self.assertEqual([lower, upper], [p for p in params if p in (lower, upper)])
        self.assertTrue(lower <= '2026-09-05' <= upper)  # released today
        self.assertFalse(lower <= '2027-01-01' <= upper)  # mistagged, in the future
        self.assertFalse(lower <= '2025-09-05' <= upper)  # a year old

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
        normalized = ' '.join(sql.split())
        self.assertIn('OR', sql)
        self.assertIn('r.rating) >= %s', normalized)
        self.assertIn('NOT (EXISTS', normalized)

    def test_the_pools_ask_about_the_song_not_the_file(self):
        """A rip of a song heard in its official version is not "unheard", and a song rated
        in one version is loved in all of them (bug report 096)."""
        sql, _ = candidates_query('user', POLICIES['daily-mix'], NOW)
        where = ' '.join(sql.split()).split(' WHERE EXISTS (SELECT 1 FROM library_media_files', 1)[1]
        self.assertIn('hv.work_id = t.work_id', where)
        self.assertIn('v.work_id = t.work_id', where)

    def test_every_placeholder_has_exactly_one_parameter(self):
        """The song-level heard and rating add placeholders ahead of the WHERE clause; a
        miscount shifts every later parameter one slot along, silently."""
        for slug in ('release-radar', 'daily-mix', 'daily-mix-artist'):
            with self.subTest(slug=slug):
                entity = ('artist', 'Angerfist') if slug == 'daily-mix-artist' else None
                sql, params = candidates_query('user', POLICIES[slug], NOW, entity_filter=entity)
                self.assertEqual(sql.count('%s'), len(params))

    def test_the_candidate_names_its_work_and_the_work_s_canonical(self):
        sql, _ = candidates_query('user', POLICIES['release-radar'], NOW)
        normalized = ' '.join(sql.split())
        self.assertIn('t.work_id, w.canonical_track_id', normalized)
        self.assertIn('LEFT JOIN library_works w ON w.id = t.work_id', normalized)

    def test_the_rating_is_the_canonical_s_else_the_highest_on_any_version(self):
        """Ratings stay stored per track_uid and display per song: the canonical's own when it
        has one (a rating given from a list lands there, so it has to show), else the highest
        in the group; a track without a work keeps its own."""
        sql, _ = candidates_query('user', POLICIES['release-radar'], NOW)
        normalized = ' '.join(sql.split())
        canonical = normalized.index('WHERE c.id = w.canonical_track_id)')
        highest = normalized.index('(SELECT MAX(rv.rating) FROM library_tracks v')
        self.assertLess(canonical, highest)
        self.assertIn('WHERE v.work_id = t.work_id), r.rating) AS rating', normalized)

    def test_only_songs_compete(self):
        sql, params = candidates_query('user', POLICIES['release-radar'], NOW)
        self.assertIn('t.duration_secs < %s', sql)
        self.assertIn(600, params)

    def test_a_multi_label_track_always_reports_the_same_label(self):
        """The picked label decides both the bucket a genre-less candidate

        competes in and the `label:<name>` reason shown for it. `LIMIT 1` with
        no `ORDER BY` leaves that to the storage engine, so the same track can
        be explained two different ways on two runs.
        """
        sql, _ = candidates_query('user', POLICIES['release-radar'], NOW)
        self.assertIn('WHERE tl.track_id = t.id ORDER BY l.name LIMIT 1) AS label', ' '.join(sql.split()))

    def test_a_candidate_must_have_a_file(self):
        sql, _ = candidates_query('user', POLICIES['release-radar'], NOW)
        self.assertIn('library_media_files', sql)

    def test_heard_is_an_exists_against_this_listener_s_history(self):
        sql, _ = candidates_query('user', POLICIES['release-radar'], NOW)
        self.assertIn(
            '(EXISTS (SELECT 1 FROM scrobble_listens sl WHERE sl.track_id = t.id AND sl.username = %s)',
            ' '.join(sql.split()),
        )

    def test_a_listen_of_any_version_counts_as_heard(self):
        """Bug report 096: Teun heard the official version, and the radar ranked the rip of
        the same song as unheard, above it."""
        sql, _ = candidates_query('user', POLICIES['release-radar'], NOW)
        self.assertIn(
            'OR EXISTS (SELECT 1 FROM library_tracks hv JOIN scrobble_listens hl ON hl.track_id = hv.id'
            ' WHERE hv.work_id = t.work_id AND hl.username = %s)) AS heard',
            ' '.join(sql.split()),
        )

    def test_heard_s_parameter_sits_ahead_of_the_rating_join_and_every_where_param(self):
        """The heard EXISTS lives in the SELECT list, textually before the rating

        join and the WHERE clause, so its %s must bind first -- a param list
        built in any other order feeds the wrong username into the wrong slot.
        """
        sql, params = candidates_query('user', POLICIES['release-radar'], NOW)
        normalized = ' '.join(sql.split())
        heard_pos = normalized.index('AS heard')
        rating_pos = normalized.index("r.username = %s")
        self.assertLess(heard_pos, rating_pos)
        self.assertEqual(params[:5], ['user'] * 5)
        self.assertEqual(params[5], POLICIES['release-radar'].max_track_seconds)


class CanonicalRowsQueryTest(unittest.TestCase):
    """The canonical a work collapses onto, fetched when it was not a candidate itself."""

    @staticmethod
    def _select(sql):
        return ' '.join(sql.split()).split(' WHERE EXISTS (SELECT 1 FROM library_media_files')[0]

    def test_same_row_shape_as_a_candidate(self):
        canonical_sql, _ = canonical_rows_query('user', [7])
        candidate_sql, _ = candidates_query('user', POLICIES['release-radar'], NOW)
        self.assertEqual(self._select(canonical_sql), self._select(candidate_sql))

    def test_no_policy_filter_only_a_file_and_the_ids(self):
        sql, params = canonical_rows_query('user', [7, 9])
        normalized = ' '.join(sql.split())
        self.assertIn('t.id IN (%s, %s)', normalized)
        self.assertNotIn('duration_secs <', normalized)
        self.assertEqual(params, ['user'] * 5 + [7, 9])
        self.assertEqual(sql.count('%s'), len(params))

    def test_an_empty_id_list_is_refused(self):
        with self.assertRaises(ValueError):
            canonical_rows_query('user', [])


class EntityFilterTest(unittest.TestCase):
    """candidates_query's entity_filter: the two rotating daily mixes restrict

    the pool to one artist or one label, everything else about it unchanged.
    """

    def test_an_artist_filter_adds_a_name_match_on_the_primary_artist(self):
        sql, params = candidates_query('user', POLICIES['daily-mix-artist'], NOW, entity_filter=('artist', 'Angerfist'))
        self.assertIn('a.name = %s', sql)
        self.assertEqual(params[-1], 'Angerfist')

    def test_a_label_filter_adds_an_exists_against_the_track_s_labels(self):
        sql, params = candidates_query(
            'user', POLICIES['daily-mix-label'], NOW, entity_filter=('label', 'Neophyte Records')
        )
        self.assertIn('library_track_labels', sql)
        self.assertEqual(params[-1], 'Neophyte Records')

    def test_no_filter_changes_nothing_about_the_statement(self):
        with_none, _ = candidates_query('user', POLICIES['daily-mix-artist'], NOW, entity_filter=None)
        without_arg, _ = candidates_query('user', POLICIES['daily-mix-artist'], NOW)
        self.assertEqual(with_none, without_arg)

    def test_an_unknown_dimension_is_refused(self):
        with self.assertRaises(ValueError):
            candidates_query('user', POLICIES['daily-mix-artist'], NOW, entity_filter=('genre', 'Uptempo'))


class GenreHardnessQueryTest(unittest.TestCase):
    def test_bounded_to_the_given_track_ids(self):
        sql, params = genre_hardness_query([1, 2, 3])
        self.assertIn('tg.track_id IN (%s, %s, %s)', sql)
        self.assertEqual(params, [1, 2, 3])

    def test_only_genres_with_a_known_hardness_are_summed(self):
        sql, _ = genre_hardness_query([1])
        self.assertIn('rg.hardness IS NOT NULL', sql)
        self.assertIn("rg.state <> 'black'", sql)

    def test_no_ids_is_refused_rather_than_rendered_as_an_empty_in(self):
        with self.assertRaises(ValueError):
            genre_hardness_query([])


class EntityHardnessQueryTest(unittest.TestCase):
    def test_the_label_variant_groups_by_label(self):
        sql, params = entity_hardness_query('label', ['Neophyte Records'])
        self.assertIn('library_track_labels', sql)
        self.assertEqual(params, ['Neophyte Records'])

    def test_the_artist_variant_groups_by_artist(self):
        sql, params = entity_hardness_query('artist', ['Angerfist'])
        self.assertIn('primary_artist_id', sql)
        self.assertEqual(params, ['Angerfist'])

    def test_a_mean_needs_at_least_five_scored_tracks(self):
        sql, _ = entity_hardness_query('label', ['Neophyte Records'])
        self.assertIn('HAVING COUNT(DISTINCT tg.track_id) >= 5', sql)

    def test_an_unknown_dimension_is_refused(self):
        with self.assertRaises(ValueError):
            entity_hardness_query('genre', ['Uptempo'])

    def test_no_names_is_refused(self):
        with self.assertRaises(ValueError):
            entity_hardness_query('label', [])

    def test_a_name_is_never_written_into_the_statement(self):
        sql, params = entity_hardness_query('artist', ["Angerfist'; DROP TABLE library_tracks--"])
        self.assertNotIn('Angerfist', sql)
        self.assertEqual(params, ["Angerfist'; DROP TABLE library_tracks--"])


class DominantGenreQueryTest(unittest.TestCase):
    def test_the_label_variant_groups_by_label(self):
        sql, _ = dominant_genre_query('label', ['Peacock Records'])
        self.assertIn('library_track_labels', sql)

    def test_an_unknown_dimension_is_refused_rather_than_interpolated(self):
        with self.assertRaises(ValueError):
            dominant_genre_query('; DROP TABLE library_tracks', ['Peacock Records'])

    def test_the_aggregation_is_bounded_to_the_names_it_is_asked_about(self):
        """Unbounded, this groups over every (label, genre) pair in the library

        on every feed request. The names are what the candidates carry.
        """
        sql, params = dominant_genre_query('label', ['Peacock Records', 'Masters of Hardcore'])
        self.assertIn('l.name IN (%s, %s)', ' '.join(sql.split()))
        self.assertEqual(params, ['Peacock Records', 'Masters of Hardcore'])

    def test_a_name_is_never_written_into_the_statement(self):
        sql, params = dominant_genre_query('artist', ["Angerfist'; DROP TABLE library_tracks--"])
        self.assertNotIn('Angerfist', sql)
        self.assertNotIn('DROP TABLE', sql)
        self.assertEqual(params, ["Angerfist'; DROP TABLE library_tracks--"])

    def test_no_names_is_refused_rather_than_rendered_as_an_empty_in(self):
        """`IN ()` is a syntax error, so the caller has to skip the query -- and

        this refusal is what makes forgetting that impossible to miss.
        """
        with self.assertRaises(ValueError):
            dominant_genre_query('label', [])
