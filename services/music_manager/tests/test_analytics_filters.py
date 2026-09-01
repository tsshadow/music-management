import unittest

from services.music_manager.routers.analytics_filters import LibraryFilter, build_filter


class BuildFilterTest(unittest.TestCase):
    def test_no_filters_is_unrestricted(self):
        where, params = build_filter(LibraryFilter())
        self.assertEqual(where, '1=1')
        self.assertEqual(params, [])

    def test_free_text_searches_title_artist_and_label(self):
        where, params = build_filter(LibraryFilter(q='angerfist'))
        self.assertIn('t.title LIKE %s', where)
        self.assertIn('a.name LIKE %s', where)
        self.assertIn('library_track_labels', where)
        self.assertEqual(params, ['%angerfist%', '%angerfist%', '%angerfist%'])

    def test_bare_number_in_range_is_read_as_bpm(self):
        where, params = build_filter(LibraryFilter(q='150'))
        self.assertIn('BETWEEN %s AND %s', where)
        self.assertEqual(params, [148.0, 152.0])

    def test_number_outside_bpm_range_is_treated_as_text(self):
        where, params = build_filter(LibraryFilter(q='2024'))
        self.assertIn('t.title LIKE %s', where)
        self.assertEqual(params, ['%2024%', '%2024%', '%2024%'])

    def test_multiple_terms_are_combined_with_and(self):
        where, _ = build_filter(LibraryFilter(q='angerfist masters'))
        self.assertEqual(where.count('t.title LIKE %s'), 2)
        self.assertIn(') AND (', where)

    def test_several_genres_are_or_within_the_parameter(self):
        where, params = build_filter(LibraryFilter(genre=['Hardcore', 'Frenchcore']))
        self.assertIn('rg.name IN (%s, %s)', where)
        self.assertEqual(params, ['Hardcore', 'Frenchcore'])

    def test_several_artists_are_or_within_the_parameter(self):
        where, params = build_filter(LibraryFilter(artist=['Angerfist', 'Radical Redemption']))
        self.assertIn('a.name IN (%s, %s)', where)
        self.assertEqual(params, ['Angerfist', 'Radical Redemption'])

    def test_several_labels_are_or_within_the_parameter(self):
        where, params = build_filter(LibraryFilter(label=['Footworxx']))
        self.assertIn('l.name IN (%s)', where)
        self.assertEqual(params, ['Footworxx'])

    def test_bpm_range_uses_tempo_with_bpm_tag_fallback(self):
        where, params = build_filter(LibraryFilter(bpm_min=140, bpm_max=180))
        self.assertIn('COALESCE(af.tempo, af.bpm_tag) >= %s', where)
        self.assertIn('COALESCE(af.tempo, af.bpm_tag) <= %s', where)
        self.assertEqual(params, [140, 180])

    def test_year_range_uses_release_year(self):
        where, params = build_filter(LibraryFilter(year_min=2020, year_max=2024))
        self.assertIn('af.release_year >= %s', where)
        self.assertIn('af.release_year <= %s', where)
        self.assertEqual(params, [2020, 2024])

    def test_analyzed_requires_an_audio_features_row(self):
        where, params = build_filter(LibraryFilter(analyzed=True))
        self.assertIn('af.track_id IS NOT NULL', where)
        self.assertEqual(params, [])

    def test_analyzed_false_requires_the_absence_of_one(self):
        where, _ = build_filter(LibraryFilter(analyzed=False))
        self.assertIn('af.track_id IS NULL', where)

    def test_parameters_are_combined_with_and(self):
        """Counted on clauses without subqueries, so the AND inside an EXISTS
        does not get mistaken for a top-level one."""
        where, params = build_filter(LibraryFilter(bpm_min=190, year_min=2020, analyzed=True))
        self.assertEqual(where.count(' AND '), 2)
        self.assertEqual(
            where, 'COALESCE(af.tempo, af.bpm_tag) >= %s AND af.release_year >= %s AND af.track_id IS NOT NULL'
        )
        self.assertEqual(params, [190, 2020])

    def test_subquery_parameters_appear_in_declaration_order(self):
        where, params = build_filter(LibraryFilter(genre=['Hardcore'], label=['Footworxx'], bpm_min=190))
        self.assertIn('rg.name IN (%s)', where)
        self.assertIn('l.name IN (%s)', where)
        self.assertIn('COALESCE(af.tempo, af.bpm_tag) >= %s', where)
        self.assertEqual(params, ['Hardcore', 'Footworxx', 190])

    def test_empty_strings_are_ignored(self):
        where, params = build_filter(LibraryFilter(q='  ', genre=[''], artist=[]))
        self.assertEqual(where, '1=1')
        self.assertEqual(params, [])

    def test_values_are_never_interpolated_into_the_sql(self):
        """Everything user-supplied travels as a parameter, never as literal SQL."""
        where, params = build_filter(LibraryFilter(genre=["'; DROP TABLE library_tracks; --"]))
        self.assertNotIn('DROP TABLE', where)
        self.assertEqual(params, ["'; DROP TABLE library_tracks; --"])


if __name__ == '__main__':
    unittest.main()
