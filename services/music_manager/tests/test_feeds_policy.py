import dataclasses
import unittest

from services.music_manager.feeds.hardness import DEFAULT_BAND_EDGES
from services.music_manager.feeds.policy import (
    DEFAULT_FEED_SIZE,
    MAX_FEED_SIZE,
    MIN_FEED_SIZE,
    POLICIES,
    parse_feed_size,
    parse_hardness_edges,
    parse_older_min_rating,
    parse_recent_share,
    parse_recent_window_days,
    parse_starting_genres,
    resize,
    with_recent_split,
)


class FeedSizeTest(unittest.TestCase):
    """`feeds_size`: a usable number is taken as is, anything else is the default."""

    def test_the_default_is_a_hundred(self):
        self.assertEqual(DEFAULT_FEED_SIZE, 100)

    def test_a_value_in_range_is_taken(self):
        for raw, expected in (
            (150, 150),
            ('40', 40),
            (' 60 ', 60),
            (MIN_FEED_SIZE, MIN_FEED_SIZE),
            (MAX_FEED_SIZE, MAX_FEED_SIZE),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(parse_feed_size(raw), expected)

    def test_garbage_and_out_of_range_fall_back(self):
        for raw in (None, '', 'veel', '12.5', True, 0, -5, MIN_FEED_SIZE - 1, MAX_FEED_SIZE + 1):
            with self.subTest(raw=raw):
                self.assertEqual(parse_feed_size(raw), DEFAULT_FEED_SIZE)


class PolicyTest(unittest.TestCase):
    def test_the_radar_is_a_seven_day_window_over_everything(self):
        radar = POLICIES['release-radar']
        self.assertEqual(radar.release_window_days, 7)
        self.assertEqual(radar.pools, frozenset({'any'}))
        self.assertEqual(radar.order, 'release')
        self.assertTrue(radar.heard_rank_penalty)

    def test_the_daily_mix_is_half_last_year_and_half_older(self):
        """Bug report 131: no window on the pool itself, a recent share of it instead."""
        mix = POLICIES['daily-mix']
        self.assertIsNone(mix.release_window_days)
        self.assertEqual(mix.recent_share, 0.5)
        self.assertEqual(mix.recent_window_days, 365)
        self.assertEqual(mix.older_min_rating, 3)
        self.assertEqual(mix.pools, frozenset({'unheard', 'loved'}))
        self.assertEqual(mix.loved_min_rating, 4)
        self.assertEqual(mix.order, 'daily_sample')

    def test_both_feeds_are_songs_only(self):
        for policy in POLICIES.values():
            self.assertEqual(policy.max_track_seconds, 600)
            self.assertEqual(policy.size, DEFAULT_FEED_SIZE)
            if policy.slug != 'daily-mix-artist':
                self.assertEqual(policy.max_per_artist, 3)

    def test_the_artist_mix_is_not_capped_per_artist(self):
        # Every candidate of an artist mix shares one primary artist; a cap of three
        # would cut the whole mix to three tracks (bug report 110).
        policy = POLICIES['daily-mix-artist']
        self.assertEqual(policy.max_per_artist, policy.size)
        self.assertEqual(POLICIES['daily-mix-label'].max_per_artist, 3)

    def test_resizing_the_artist_mix_moves_its_cap_with_it(self):
        """`feeds_size` 150 must not leave the artist mix capped at the code default."""
        for size in (40, 150):
            with self.subTest(size=size):
                resized = resize(POLICIES['daily-mix-artist'], size)
                self.assertEqual((resized.size, resized.max_per_artist), (size, size))

    def test_resizing_a_capped_policy_keeps_its_cap(self):
        for slug in ('release-radar', 'daily-mix', 'daily-mix-label', 'daily-mix-mid'):
            with self.subTest(slug=slug):
                resized = resize(POLICIES[slug], 150)
                self.assertEqual((resized.size, resized.max_per_artist), (150, 3))

    def test_resizing_to_the_same_size_is_the_same_policy(self):
        policy = POLICIES['release-radar']
        self.assertIs(resize(policy, policy.size), policy)

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
                self.assertIsNone(policy.release_window_days)
                self.assertEqual(policy.recent_share, 0.5)
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


class HardnessEdgesSettingTest(unittest.TestCase):
    """The router and the dry run read the same setting, so they parse it in one

    place -- the same contract StartingGenresTest above exercises for its own
    setting.
    """

    def test_a_well_formed_setting_is_used_and_reported_as_such(self):
        self.assertEqual(parse_hardness_edges('50,75'), ((50.0, 75.0), 'setting'))

    def test_whitespace_around_the_numbers_is_trimmed(self):
        self.assertEqual(parse_hardness_edges(' 40 , 70 '), ((40.0, 70.0), 'setting'))

    def test_nothing_configured_falls_back_to_the_default(self):
        self.assertEqual(parse_hardness_edges(''), (DEFAULT_BAND_EDGES, 'default'))
        self.assertEqual(parse_hardness_edges(None), (DEFAULT_BAND_EDGES, 'default'))

    def test_edges_that_are_not_ascending_fall_back_to_the_default(self):
        self.assertEqual(parse_hardness_edges('75,50'), (DEFAULT_BAND_EDGES, 'default'))
        self.assertEqual(parse_hardness_edges('50,50'), (DEFAULT_BAND_EDGES, 'default'))

    def test_edges_outside_zero_to_a_hundred_fall_back_to_the_default(self):
        self.assertEqual(parse_hardness_edges('-5,75'), (DEFAULT_BAND_EDGES, 'default'))
        self.assertEqual(parse_hardness_edges('50,150'), (DEFAULT_BAND_EDGES, 'default'))

    def test_unparsable_garbage_falls_back_to_the_default(self):
        self.assertEqual(parse_hardness_edges('nope'), (DEFAULT_BAND_EDGES, 'default'))
        self.assertEqual(parse_hardness_edges('50,75,90'), (DEFAULT_BAND_EDGES, 'default'))
        self.assertEqual(parse_hardness_edges('fifty,seventyfive'), (DEFAULT_BAND_EDGES, 'default'))


class RecentSplitTest(unittest.TestCase):
    """Bug report 131: which mixes split recent/older, and the three settings behind it."""

    def test_the_label_mix_splits_and_radar_and_artist_mix_do_not(self):
        self.assertEqual(POLICIES['daily-mix-label'].recent_share, 0.5)
        self.assertIsNone(POLICIES['daily-mix-label'].release_window_days)
        self.assertIsNone(POLICIES['release-radar'].recent_share)
        self.assertEqual(POLICIES['release-radar'].release_window_days, 7)
        self.assertIsNone(POLICIES['daily-mix-artist'].recent_share)
        self.assertEqual(POLICIES['daily-mix-artist'].release_window_days, 90)

    def test_the_percentage_setting_becomes_a_share(self):
        for raw, expected in ((50, 0.5), ('30', 0.3), (0, 0.0), (100, 1.0), (None, 0.5), ('x', 0.5), (101, 0.5)):
            with self.subTest(raw=raw):
                self.assertEqual(parse_recent_share(raw), expected)

    def test_the_window_and_rating_fall_back_on_garbage(self):
        self.assertEqual(parse_recent_window_days(90), 90)
        self.assertEqual(parse_recent_window_days('0'), 365)
        self.assertEqual(parse_recent_window_days(None), 365)
        self.assertEqual(parse_older_min_rating(4), 4)
        self.assertEqual(parse_older_min_rating(6), 3)
        self.assertEqual(parse_older_min_rating(True), 3)

    def test_the_settings_never_switch_the_split_on_for_a_policy_without_one(self):
        radar = POLICIES['release-radar']
        self.assertIs(with_recent_split(radar, 0.3, 90, 4), radar)
        tuned = with_recent_split(POLICIES['daily-mix-hard'], 0.3, 90, 4)
        self.assertEqual((tuned.recent_share, tuned.recent_window_days, tuned.older_min_rating), (0.3, 90, 4))
        self.assertEqual(tuned.hardness_band, 'hard')
