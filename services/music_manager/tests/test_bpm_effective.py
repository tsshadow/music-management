"""Octave folding into a genre's band and the one rule that picks a track's effective BPM."""

import unittest

from services.music_manager.bpm import bands
from services.music_manager.bpm.effective import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    SOURCE_ANALYZER,
    SOURCE_MEASURED,
    SOURCE_TAG,
    resolve,
)


class BandForGenresTest(unittest.TestCase):
    def test_a_known_genre_has_its_band_whatever_the_casing(self):
        self.assertEqual(bands.band_for_genres(['Raw Hardstyle']), bands.GENRE_BANDS['raw hardstyle'])

    def test_unknown_genres_have_no_band(self):
        self.assertIsNone(bands.band_for_genres(['Podcast', '']))

    def test_overlapping_genres_meet_where_both_agree(self):
        self.assertEqual(bands.band_for_genres(['Hardstyle', 'Hardcore']), (150.0, 175.0))

    def test_disjoint_genres_fall_back_to_the_narrowest_band(self):
        self.assertEqual(bands.band_for_genres(['House', 'Uptempo Hardcore']), bands.GENRE_BANDS['house'])

    def test_every_band_holds_at_most_one_octave(self):
        for name, (low, high) in bands.GENRE_BANDS.items():
            with self.subTest(genre=name):
                self.assertLess(high, 2 * low)


class FoldIntoBandTest(unittest.TestCase):
    def test_a_value_in_the_band_is_left_alone(self):
        folded = bands.fold_into_band(152.0, (135.0, 175.0))
        self.assertEqual((folded.bpm, folded.octave_corrected, folded.in_band), (152.0, False, True))

    def test_a_half_time_reading_is_doubled(self):
        folded = bands.fold_into_band(75.0, (135.0, 175.0))
        self.assertEqual((folded.bpm, folded.octave_corrected), (150.0, True))

    def test_a_double_time_reading_is_halved(self):
        self.assertEqual(bands.fold_into_band(300.0, (135.0, 175.0)).bpm, 150.0)

    def test_an_uptempo_half_reading_goes_up_to_the_uptempo_band(self):
        self.assertEqual(bands.fold_into_band(105.0, bands.GENRE_BANDS['uptempo hardcore']).bpm, 210.0)

    def test_without_a_genre_only_half_time_is_doubled(self):
        self.assertEqual(bands.fold_into_band(76.0, None).bpm, 152.0)
        self.assertEqual(bands.fold_into_band(210.0, None).bpm, 210.0)
        self.assertTrue(bands.fold_into_band(210.0, None).default_band)

    def test_no_octave_in_the_band_picks_the_nearest_and_says_so(self):
        folded = bands.fold_into_band(100.0, (160.0, 190.0))
        self.assertFalse(folded.in_band)
        self.assertEqual(folded.bpm, 200.0)


class ResolveTest(unittest.TestCase):
    def test_nothing_usable_is_none(self):
        self.assertIsNone(resolve(tag=0, tempo=None))
        self.assertIsNone(resolve(tag='not a number', tempo=1500))

    def test_a_measurement_wins_over_tag_and_tempo(self):
        found = resolve(measured=150.04, measured_confidence=0.9, tag=152, tempo=152, genres=['Hardstyle'])
        self.assertEqual((found.bpm, found.source, found.confidence), (150.04, SOURCE_MEASURED, CONFIDENCE_HIGH))
        self.assertFalse(found.approximate)

    def test_a_measurement_below_the_reliable_threshold_is_medium(self):
        found = resolve(measured=150.0, measured_confidence=0.5, reliable_confidence=0.75)
        self.assertEqual(found.confidence, CONFIDENCE_MEDIUM)

    def test_a_measurement_is_never_folded_again(self):
        found = resolve(measured=100.0, measured_confidence=0.9, measured_folded=True, genres=['Hardstyle'])
        self.assertEqual((found.bpm, found.folded), (100.0, True))

    def test_the_tag_wins_over_the_analyzer(self):
        found = resolve(tag=152.0, tempo=161.5, genres=['Hardstyle'])
        self.assertEqual((found.bpm, found.source), (152.0, SOURCE_TAG))
        self.assertTrue(found.approximate)

    def test_a_tag_the_analyzer_agrees_with_inside_the_band_is_medium(self):
        self.assertEqual(resolve(tag=152.0, tempo=151.999, genres=['Hardstyle']).confidence, CONFIDENCE_MEDIUM)

    def test_agreement_counts_after_folding_the_analyzer(self):
        found = resolve(tag=152.0, tempo=76.0, genres=['Hardstyle'])
        self.assertEqual(found.confidence, CONFIDENCE_MEDIUM)

    def test_a_tag_alone_is_low(self):
        self.assertEqual(resolve(tag=152.0, genres=['Hardstyle']).confidence, CONFIDENCE_LOW)

    def test_a_tag_without_a_genre_is_low_even_when_the_analyzer_agrees(self):
        self.assertEqual(resolve(tag=152.0, tempo=152.0).confidence, CONFIDENCE_LOW)

    def test_a_folded_tag_is_low_and_marked(self):
        found = resolve(tag=105.0, tempo=105.0, genres=['Uptempo Hardcore'])
        self.assertEqual((found.bpm, found.folded, found.confidence), (210.0, True, CONFIDENCE_LOW))

    def test_the_analyzer_alone_is_low_and_folded_into_the_band(self):
        found = resolve(tempo=76.0, genres=['Raw Hardstyle'])
        self.assertEqual(
            (found.bpm, found.source, found.confidence, found.folded), (152.0, SOURCE_ANALYZER, CONFIDENCE_LOW, True)
        )


if __name__ == '__main__':
    unittest.main()
