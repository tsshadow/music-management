import dataclasses
import unittest

from services.music_manager.feeds.policy import POLICIES, parse_starting_genres


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
        with self.assertRaises(dataclasses.FrozenInstanceError):
            POLICIES['release-radar'].size = 5


class SpectrumPolicyTest(unittest.TestCase):
    """The three hardness-band mixes: same daily-mix pool, one third of the

    listener's own spectrum each."""

    def test_the_three_bands_share_the_daily_mix_pool(self):
        for slug, band in (('daily-mix-soft', 'soft'), ('daily-mix-mid', 'mid'), ('daily-mix-hard', 'hard')):
            with self.subTest(slug=slug):
                policy = POLICIES[slug]
                self.assertEqual(policy.hardness_band, band)
                self.assertEqual(policy.release_window_days, 90)
                self.assertEqual(policy.pools, frozenset({'unheard', 'loved'}))
                self.assertEqual(policy.order, 'daily_sample')
                self.assertIsNone(policy.rotate)

    def test_plain_daily_mix_is_the_classic_unrestricted_policy(self):
        """Design correction: 'daily-mix' is not an alias of 'daily-mix-mid' --

        aliasing it meant a track with no resolvable hardness lost its place on
        the one slug the car and the phone already call, which must never come
        up empty just because the library's genre coverage is thin. It shares
        the same pool/order/window as the band mixes (still one ranker, many
        parameter sets) but carries no hardness_band of its own.
        """
        classic, mid = POLICIES['daily-mix'], POLICIES['daily-mix-mid']
        self.assertIsNone(classic.hardness_band)
        self.assertIsNone(classic.rotate)
        self.assertEqual(classic.release_window_days, mid.release_window_days)
        self.assertEqual(classic.pools, mid.pools)
        self.assertEqual(classic.order, mid.order)
        self.assertNotEqual(classic.slug, mid.slug)


class RotatingPolicyTest(unittest.TestCase):
    def test_the_artist_mix_rotates_and_carries_no_band(self):
        policy = POLICIES['daily-mix-artist']
        self.assertEqual(policy.rotate, 'artist')
        self.assertIsNone(policy.hardness_band)
        self.assertEqual(policy.pools, frozenset({'unheard', 'loved'}))

    def test_the_label_mix_rotates_and_carries_no_band(self):
        policy = POLICIES['daily-mix-label']
        self.assertEqual(policy.rotate, 'label')
        self.assertIsNone(policy.hardness_band)

    def test_release_radar_neither_bands_nor_rotates(self):
        radar = POLICIES['release-radar']
        self.assertIsNone(radar.hardness_band)
        self.assertIsNone(radar.rotate)


class StartingGenresTest(unittest.TestCase):
    """The router and the dry run read the same setting, so they parse it in one place."""

    def test_a_comma_separated_list_is_split_and_trimmed(self):
        self.assertEqual(parse_starting_genres(' uptempo , raw hardcore '), ['uptempo', 'raw hardcore'])

    def test_nothing_configured_means_no_fallback_at_all(self):
        """Not "an empty fallback": a server with no history reports

        not_enough_data rather than inventing a taste out of an empty setting.
        """
        self.assertIsNone(parse_starting_genres(''))
        self.assertIsNone(parse_starting_genres(None))
        self.assertIsNone(parse_starting_genres(' , , '))
