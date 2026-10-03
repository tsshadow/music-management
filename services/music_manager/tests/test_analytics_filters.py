import unittest
from typing import Any

from services.music_manager.routers.analytics_filters import (
    EFFECTIVE_BPM_JOIN,
    EFFECTIVE_BPM_SQL,
    EFFECTIVE_YEAR_SQL,
    FROM_CLAUSE,
    LibraryFilter,
    build_filter,
    parse_filter,
)

# parse_filter is a FastAPI dependency; called directly, every Query default must be passed.
PARSE_DEFAULTS: dict[str, Any] = {
    'q': '',
    'artist': [],
    'genre': [],
    'label': [],
    'bpm_min': None,
    'bpm_max': None,
    'year_min': None,
    'year_max': None,
    'analyzed': None,
}


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
        self.assertEqual(where, '(eb.bpm BETWEEN %s AND %s)')
        self.assertEqual(params, [148.0, 152.0])

    def test_no_bpm_reader_chooses_between_the_sources_itself(self):
        """Issue #141: the search term and the range read the effective BPM, never the old
        analyzer's tempo or tag directly."""
        for f in (LibraryFilter(q='150'), LibraryFilter(bpm_min=140, bpm_max=180)):
            where, _ = build_filter(f)
            self.assertNotIn('af.tempo', where)
            self.assertNotIn('af.bpm_tag', where)

    def test_the_shared_from_clause_joins_the_effective_bpm(self):
        self.assertEqual(EFFECTIVE_BPM_SQL, 'eb.bpm')
        self.assertIn(EFFECTIVE_BPM_JOIN, FROM_CLAUSE)
        self.assertIn('library_track_effective_bpm eb ON eb.track_id = t.id', FROM_CLAUSE)

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

    def test_bpm_range_uses_the_effective_bpm(self):
        where, params = build_filter(LibraryFilter(bpm_min=140, bpm_max=180))
        self.assertIn('eb.bpm >= %s', where)
        self.assertIn('eb.bpm <= %s', where)
        self.assertEqual(params, [140, 180])

    def test_year_range_uses_the_effective_year(self):
        """Performance date for a live set, then the release date, then the analyzer's year."""
        where, params = build_filter(LibraryFilter(year_min=2020, year_max=2024))
        self.assertIn(f'{EFFECTIVE_YEAR_SQL} >= %s', where)
        self.assertIn(f'{EFFECTIVE_YEAR_SQL} <= %s', where)
        self.assertLess(EFFECTIVE_YEAR_SQL.index('performance_date'), EFFECTIVE_YEAR_SQL.index('release_date'))
        self.assertTrue(EFFECTIVE_YEAR_SQL.rstrip(')').endswith('af.release_year'))
        self.assertEqual(params, [2020, 2024])

    def test_several_forms_are_or_within_the_parameter(self):
        where, params = build_filter(LibraryFilter(form=['liveset', 'set']))
        self.assertEqual(where, 't.form IN (%s, %s)')
        self.assertEqual(params, ['liveset', 'set'])

    def test_an_unknown_form_is_refused(self):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as raised:
            parse_filter(form=['liveset', 'mixtape'], **PARSE_DEFAULTS)
        self.assertEqual(raised.exception.status_code, 422)

    def test_a_known_form_reaches_the_filter(self):
        self.assertEqual(parse_filter(form=['podcast'], **PARSE_DEFAULTS).form, ['podcast'])

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
        self.assertEqual(where, f'eb.bpm >= %s AND {EFFECTIVE_YEAR_SQL} >= %s AND af.track_id IS NOT NULL')
        self.assertEqual(params, [190, 2020])

    def test_subquery_parameters_appear_in_declaration_order(self):
        where, params = build_filter(LibraryFilter(genre=['Hardcore'], label=['Footworxx'], bpm_min=190))
        self.assertIn('rg.name IN (%s)', where)
        self.assertIn('l.name IN (%s)', where)
        self.assertIn('eb.bpm >= %s', where)
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
