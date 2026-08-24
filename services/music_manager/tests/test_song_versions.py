"""Which recordings are the same song, and which only look like it.

Pure functions, no database: the grouping rule is pinned down here so the worker
only has to be right about SQL.
"""
import unittest

from services.music_manager.song_versions import (
    KIND_ORDER,
    version_free_title,
    version_kind,
    work_key,
)


class VersionFreeTitleTest(unittest.TestCase):

    def test_length_variants_of_one_recording_collapse(self):
        titles = [
            'Raise Your Fist',
            'Raise Your Fist (Radio Edit)',
            'Raise Your Fist (Extended Mix)',
            'Raise Your Fist (Original Mix)',
            'Raise Your Fist (Official Video)',
            'Raise Your Fist [Free Download]',
        ]
        results = {version_free_title(title) for title in titles}
        self.assertEqual(len(results), 1, results)

    def test_a_remix_keeps_its_bracket(self):
        self.assertNotEqual(
            version_free_title('Raise Your Fist (Wildstylez Remix)'),
            version_free_title('Raise Your Fist'),
        )

    def test_a_named_edit_is_not_a_radio_edit(self):
        self.assertNotEqual(
            version_free_title('Raise Your Fist (Wildstylez Edit)'),
            version_free_title('Raise Your Fist (Radio Edit)'),
        )

    def test_a_bootleg_stays_its_own_song(self):
        self.assertNotEqual(
            version_free_title('Raise Your Fist (Bootleg)'),
            version_free_title('Raise Your Fist'),
        )

    def test_a_bracket_that_is_part_of_the_title_survives(self):
        self.assertEqual(
            version_free_title('Raise Your Fist (Part 1)'),
            version_free_title('Raise Your Fist (Part 1)'),
        )
        self.assertNotEqual(
            version_free_title('Raise Your Fist (Part 1)'),
            version_free_title('Raise Your Fist'),
        )

    def test_two_stacked_markers_both_go(self):
        self.assertEqual(
            version_free_title('Raise Your Fist (Radio Edit) (Remastered)'),
            version_free_title('Raise Your Fist'),
        )

    def test_the_result_is_normalized(self):
        self.assertEqual(
            version_free_title('  Raise   Your Fist!  (Radio Edit)'),
            version_free_title('raise your fist'),
        )

    def test_an_empty_title_is_empty(self):
        self.assertEqual(version_free_title(None), '')
        self.assertEqual(version_free_title(''), '')


class VersionKindTest(unittest.TestCase):

    def test_radio_beats_edit_when_both_words_are_present(self):
        self.assertEqual(version_kind('Raise Your Fist (Radio Edit)'), 'radio')

    def test_extended_is_recognised(self):
        self.assertEqual(version_kind('Raise Your Fist (Extended Mix)'), 'extended')

    def test_original_is_recognised(self):
        self.assertEqual(version_kind('Raise Your Fist (Original Mix)'), 'original')

    def test_a_bare_edit_is_an_edit(self):
        self.assertEqual(version_kind('Raise Your Fist (Edit)'), 'edit')

    def test_instrumental_wins_over_everything_because_it_must_never_be_canonical(self):
        self.assertEqual(version_kind('Raise Your Fist (Radio Instrumental)'), 'instrumental')

    def test_no_marker_at_all_is_none(self):
        self.assertEqual(version_kind('Raise Your Fist'), 'none')

    def test_a_marker_that_names_no_length_is_none(self):
        self.assertEqual(version_kind('Raise Your Fist (Official Video)'), 'none')

    def test_a_remix_is_none_because_it_is_a_song_of_its_own(self):
        self.assertEqual(version_kind('Raise Your Fist (Wildstylez Remix)'), 'none')

    def test_every_kind_appears_in_the_ranking_order(self):
        kinds = {'radio', 'edit', 'original', 'none', 'extended', 'instrumental'}
        self.assertEqual(set(KIND_ORDER), kinds)


class WorkKeyTest(unittest.TestCase):

    def test_the_same_song_by_the_same_artist_shares_a_key(self):
        self.assertEqual(
            work_key('Angerfist', 'Raise Your Fist (Radio Edit)'),
            work_key('angerfist', 'Raise Your Fist (Extended Mix)'),
        )

    def test_a_different_artist_is_a_different_work(self):
        self.assertNotEqual(
            work_key('Angerfist', 'Raise Your Fist'),
            work_key('Radical Redemption', 'Raise Your Fist'),
        )

    def test_the_key_fits_the_column(self):
        key = work_key('A' * 300, 'B' * 300)
        self.assertLessEqual(len(key), 191)
