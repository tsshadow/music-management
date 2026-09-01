"""Which recordings are the same song, and which only look like it.

Pure functions, no database: the grouping rule is pinned down here so the worker
only has to be right about SQL.
"""

import unittest

from services.music_manager.song_versions import (
    KIND_ORDER,
    derived_bitrate,
    format_tier,
    version_free_title,
    version_kind,
    version_score,
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


class DerivedBitrateTest(unittest.TestCase):
    def test_a_320k_file_reads_as_320ish(self):
        # 320 kbit/s over 300 seconds is 12 MB.
        self.assertGreaterEqual(derived_bitrate(12_000_000, 300.0), 300)

    def test_a_192k_file_reads_as_192ish(self):
        self.assertLess(derived_bitrate(7_200_000, 300.0), 250)

    def test_a_missing_duration_is_zero_rather_than_a_crash(self):
        self.assertEqual(derived_bitrate(12_000_000, None), 0)
        self.assertEqual(derived_bitrate(12_000_000, 0.0), 0)

    def test_a_missing_size_is_zero(self):
        self.assertEqual(derived_bitrate(None, 300.0), 0)


class FormatTierTest(unittest.TestCase):
    def test_flac_outranks_every_lossy_format(self):
        self.assertLess(format_tier('a.flac', 1000), format_tier('a.mp3', 320))
        self.assertLess(format_tier('a.flac', 1000), format_tier('a.m4a', 256))

    def test_a_320_mp3_outranks_a_192_mp3(self):
        self.assertLess(format_tier('a.mp3', 320), format_tier('a.mp3', 192))

    def test_the_extension_is_case_insensitive(self):
        self.assertEqual(format_tier('a.FLAC', 1000), format_tier('a.flac', 1000))


class VersionScoreTest(unittest.TestCase):
    def test_an_official_192k_radio_edit_beats_a_320k_rip(self):
        official = version_score(True, 'radio', 'a.mp3', 192)
        rip = version_score(False, 'none', 'b.mp3', 320)
        self.assertGreater(official, rip)

    def test_within_one_provenance_the_version_decides_before_the_format(self):
        radio_mp3 = version_score(True, 'radio', 'a.mp3', 192)
        extended_flac = version_score(True, 'extended', 'b.flac', 1000)
        self.assertGreater(radio_mp3, extended_flac)

    def test_within_one_version_the_format_decides(self):
        flac = version_score(True, 'radio', 'a.flac', 1000)
        mp3 = version_score(True, 'radio', 'b.mp3', 320)
        self.assertGreater(flac, mp3)

    def test_instrumental_is_the_worst_kind(self):
        for kind in ('radio', 'edit', 'original', 'none', 'extended'):
            self.assertGreater(
                version_score(True, kind, 'a.flac', 1000),
                version_score(True, 'instrumental', 'a.flac', 1000),
                kind,
            )

    def test_an_unknown_kind_does_not_crash_and_ranks_as_none(self):
        self.assertEqual(
            version_score(True, 'nonsense', 'a.flac', 1000),
            version_score(True, 'none', 'a.flac', 1000),
        )
