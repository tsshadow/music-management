import unittest

from services.music_manager.feeds.policy import POLICIES


class PolicyTest(unittest.TestCase):
    def test_the_radar_is_a_seven_day_window_over_everything(self):
        radar = POLICIES['release-radar']
        self.assertEqual(radar.release_window_days, 7)
        self.assertEqual(radar.pools, frozenset({'any'}))
        self.assertEqual(radar.order, 'release')
        self.assertTrue(radar.heard_rank_penalty)

    def test_the_daily_mix_is_ninety_days_of_unheard_or_loved(self):
        mix = POLICIES['daily-mix']
        self.assertEqual(mix.release_window_days, 90)
        self.assertEqual(mix.pools, frozenset({'unheard', 'loved'}))
        self.assertEqual(mix.loved_min_rating, 4)
        self.assertEqual(mix.order, 'daily_sample')

    def test_both_feeds_are_songs_only(self):
        for policy in POLICIES.values():
            self.assertEqual(policy.max_track_seconds, 600)
            self.assertEqual(policy.size, 30)
            self.assertEqual(policy.max_per_artist, 3)

    def test_a_policy_cannot_be_mutated_at_runtime(self):
        with self.assertRaises(Exception):
            POLICIES['release-radar'].size = 5
