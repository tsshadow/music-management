import unittest

from services.music_manager.feeds.profile import listen_weight


class ListenWeightTest(unittest.TestCase):
    def test_a_listen_today_counts_fully(self):
        self.assertAlmostEqual(listen_weight(0, 'exact', None), 1.0)

    def test_weight_halves_every_thirty_days(self):
        self.assertAlmostEqual(listen_weight(30, 'exact', None), 0.5)
        self.assertAlmostEqual(listen_weight(60, 'exact', None), 0.25)

    def test_a_normalized_match_is_trusted_like_an_exact_one(self):
        self.assertAlmostEqual(listen_weight(0, 'normalized', None), 1.0)

    def test_a_weak_match_counts_for_less(self):
        self.assertAlmostEqual(listen_weight(0, 'base_title', None), 0.5)
        self.assertAlmostEqual(listen_weight(0, 'fuzzy', None), 0.25)

    def test_unknown_played_time_is_not_zero_engagement(self):
        # Imported history has no played_secs at all; treating it as zero would
        # silently delete most of the listening history from the profile.
        self.assertAlmostEqual(listen_weight(0, 'exact', None), 1.0)

    def test_a_skip_counts_for_a_fraction(self):
        self.assertAlmostEqual(listen_weight(0, 'exact', 30), 0.25)

    def test_playing_past_two_minutes_is_a_full_listen(self):
        self.assertAlmostEqual(listen_weight(0, 'exact', 600), 1.0)

    def test_an_unknown_match_method_is_treated_as_the_weakest(self):
        self.assertAlmostEqual(listen_weight(0, 'something-new', None), 0.25)
