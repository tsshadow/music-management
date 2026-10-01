"""The tempo estimator on synthetic click tracks at known tempos, off the old librosa grid."""

import unittest

import pytest

# The images and CI carry numpy (requirements.txt); a bare host interpreter may not.
np = pytest.importorskip('numpy')

from services.music_manager.bpm import bands, estimator  # noqa: E402

RATE = estimator.SAMPLE_RATE


def click_track(bpm: float, seconds: float = 60.0, offbeat_hats: bool = False, seed: int = 1) -> np.ndarray:
    """A kick on every beat (a decaying 55 Hz burst plus a click), optionally hats on the offbeats."""
    rng = np.random.default_rng(seed)
    y = rng.normal(0, 0.01, int(seconds * RATE)).astype(np.float32)
    kick_len = int(0.12 * RATE)
    t = np.arange(kick_len) / RATE
    kick = (np.sin(2 * np.pi * 55 * t) * np.exp(-t * 30) + rng.normal(0, 0.3, kick_len) * np.exp(-t * 200)).astype(
        np.float32
    )
    hat_len = int(0.03 * RATE)
    hat = (rng.normal(0, 0.3, hat_len) * np.exp(-np.arange(hat_len) / RATE * 150)).astype(np.float32)
    period = 60.0 / bpm
    beat = 0.013
    while beat * RATE + kick_len < len(y):
        start = int(round(beat * RATE))
        y[start : start + kick_len] += kick
        if offbeat_hats:
            off = int(round((beat + period / 2) * RATE))
            if off + hat_len < len(y):
                y[off : off + hat_len] += hat
        beat += period
    return y


class EstimatorTest(unittest.TestCase):
    def test_150_is_measured_as_150_not_the_old_grids_152(self):
        found = estimator.estimate_bpm(click_track(150.0))
        self.assertAlmostEqual(found.bpm, 150.0, delta=0.1)
        self.assertTrue(found.halves_agree)
        self.assertGreater(found.confidence, 0.5)

    def test_155_is_told_apart_from_150(self):
        self.assertAlmostEqual(estimator.estimate_bpm(click_track(155.0, offbeat_hats=True)).bpm, 155.0, delta=0.1)

    def test_a_fractional_tempo_keeps_its_fraction(self):
        self.assertAlmostEqual(estimator.estimate_bpm(click_track(172.5, seed=4)).bpm, 172.5, delta=0.1)

    def test_uptempo_is_in_range(self):
        self.assertAlmostEqual(estimator.estimate_bpm(click_track(210.0, seed=5)).bpm, 210.0, delta=0.15)

    def test_a_half_time_reading_folds_back_into_the_genre(self):
        found = estimator.estimate_bpm(click_track(75.0, seed=2))
        folded = bands.fold_into_band(found.bpm, bands.GENRE_BANDS['hardstyle'])
        self.assertAlmostEqual(folded.bpm, 150.0, delta=0.2)

    def test_the_octave_neighbours_are_scored(self):
        found = estimator.estimate_bpm(click_track(150.0))
        self.assertIsNotNone(found.half_score)
        # 300 is outside the search range but still scored: the octave choice weighs it too.
        self.assertIsNotNone(found.double_score)
        self.assertIsNone(estimator._score_at(np.ones(10), 20.0))  # pylint: disable=protected-access

    def test_noise_has_low_confidence(self):
        noise = np.random.default_rng(9).normal(0, 0.1, 60 * RATE).astype(np.float32)
        self.assertLess(estimator.estimate_bpm(noise).confidence, 0.5)

    def test_too_little_audio_is_refused(self):
        with self.assertRaises(estimator.TooShort):
            estimator.estimate_bpm(click_track(150.0, seconds=5.0))

    def test_the_wrong_rate_is_refused(self):
        with self.assertRaises(ValueError):
            estimator.estimate_bpm(click_track(150.0), sample_rate=22050)

    def test_stereo_input_is_mixed_down(self):
        y = click_track(150.0, seconds=20.0)
        envelope = estimator.onset_envelope(np.vstack([y, y]))
        self.assertEqual(envelope.ndim, 1)


if __name__ == '__main__':
    unittest.main()
