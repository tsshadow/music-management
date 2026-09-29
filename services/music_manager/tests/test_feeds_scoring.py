import unittest
from datetime import date, datetime, timedelta

from services.music_manager.feeds.policy import POLICIES
from services.music_manager.feeds.profile import TasteProfile
from services.music_manager.feeds.scoring import (
    _daily_entity_index,
    daily_sample_key,
    pick_daily_entity,
    pick_playable_entity,
    rediscovery_factor,
    score,
    taste_score,
)

PROFILE = TasteProfile(artists={'angerfist': 1.0}, labels={'peacock records': 0.4}, genres={'uptempo': 0.6})
RADAR = POLICIES['release-radar']


def candidate(**kw):
    base = {
        'artist': None,
        'labels': [],
        'genres': [],
        'rating': None,
        'is_soundcloud': False,
        'has_label': False,
        'track_uid': 'uid',
    }
    base.update(kw)
    return base


class TasteScoreTest(unittest.TestCase):
    def test_the_strongest_signal_wins_rather_than_the_sum(self):
        both = taste_score(candidate(artist='Angerfist', genres=['Uptempo']), PROFILE)
        artist_only = taste_score(candidate(artist='Angerfist'), PROFILE)
        self.assertEqual(both, artist_only)

    def test_a_missing_genre_does_not_lower_a_strong_artist_match(self):
        self.assertEqual(taste_score(candidate(artist='Angerfist'), PROFILE), 1.0)

    def test_nothing_known_scores_zero(self):
        self.assertEqual(taste_score(candidate(artist='Nobody'), PROFILE), 0.0)


class ScoreTest(unittest.TestCase):
    def test_a_real_label_is_worth_a_small_bonus(self):
        with_label = score(candidate(artist='Angerfist', has_label=True), PROFILE, RADAR)
        without = score(candidate(artist='Angerfist'), PROFILE, RADAR)
        self.assertAlmostEqual(with_label - without, RADAR.label_bonus)

    def test_a_soundcloud_rip_is_demoted(self):
        rip = score(candidate(artist='Angerfist', is_soundcloud=True), PROFILE, RADAR)
        clean = score(candidate(artist='Angerfist'), PROFILE, RADAR)
        self.assertAlmostEqual(clean - rip, RADAR.soundcloud_penalty)

    def test_an_unrated_track_is_not_punished(self):
        self.assertEqual(
            score(candidate(artist='Angerfist', rating=None), PROFILE, RADAR),
            score(candidate(artist='Angerfist', rating=3), PROFILE, RADAR),
        )

    def test_a_favourite_ranks_above_a_one_star(self):
        self.assertGreater(
            score(candidate(artist='Angerfist', rating=5), PROFILE, RADAR),
            score(candidate(artist='Angerfist', rating=1), PROFILE, RADAR),
        )

    def test_a_score_never_reaches_zero(self):
        self.assertGreater(score(candidate(artist='Nobody', is_soundcloud=True), PROFILE, RADAR), 0)

    def test_an_out_of_range_rating_is_ignored_rather_than_rescaled(self):
        self.assertEqual(
            score(candidate(artist='Angerfist', rating=99), PROFILE, RADAR),
            score(candidate(artist='Angerfist', rating=None), PROFILE, RADAR),
        )


class DailySampleKeyTest(unittest.TestCase):
    def test_the_same_day_gives_the_same_order(self):
        first = daily_sample_key('user', date(2026, 9, 5), 'uid', 1.0)
        second = daily_sample_key('user', date(2026, 9, 5), 'uid', 1.0)
        self.assertEqual(first, second)

    def test_the_next_day_gives_a_different_one(self):
        self.assertNotEqual(
            daily_sample_key('user', date(2026, 9, 5), 'uid', 1.0),
            daily_sample_key('user', date(2026, 9, 6), 'uid', 1.0),
        )

    def test_two_listeners_do_not_get_the_same_mix(self):
        self.assertNotEqual(
            daily_sample_key('user', date(2026, 9, 5), 'uid', 1.0),
            daily_sample_key('someone', date(2026, 9, 5), 'uid', 1.0),
        )


class PickDailyEntityTest(unittest.TestCase):
    NAMES = [f'artist-{i}' for i in range(10)]

    def test_no_names_at_all_is_nothing_to_rotate_through(self):
        self.assertIsNone(pick_daily_entity('user', date(2026, 9, 5), []))

    def test_a_single_name_always_wins(self):
        self.assertEqual(pick_daily_entity('user', date(2026, 9, 5), ['only']), 'only')

    def test_stable_within_the_same_day(self):
        first = pick_daily_entity('user', date(2026, 9, 5), self.NAMES)
        second = pick_daily_entity('user', date(2026, 9, 5), self.NAMES)
        self.assertEqual(first, second)

    def test_changes_across_days(self):
        """Not guaranteed for every possible pair of dates -- a hash can land on

        the same bucket twice -- but true often enough over a week that a test
        finding no difference at all across seven days would be a real
        regression, not bad luck.
        """
        picks = {pick_daily_entity('user', date(2026, 9, 5 + offset), self.NAMES) for offset in range(7)}
        self.assertGreater(len(picks), 1)

    def test_two_listeners_do_not_rotate_in_lockstep(self):
        self.assertNotEqual(
            pick_daily_entity('user', date(2026, 9, 5), self.NAMES),
            pick_daily_entity('anna', date(2026, 9, 5), self.NAMES),
        )

    def test_the_pick_always_comes_from_the_given_names(self):
        for offset in range(20):
            chosen = pick_daily_entity('user', date(2026, 9, 5 + offset), self.NAMES)
            self.assertIn(chosen, self.NAMES)


class PickPlayableEntityTest(unittest.TestCase):
    """Bug report 110: the rotation only lands on a name with enough to play."""

    NAMES = [f'artist-{i}' for i in range(10)]
    WINDOWS = (90, 365, None)
    DAY = date(2026, 9, 26)

    def _start(self):
        return _daily_entity_index('user', self.DAY, len(self.NAMES))

    def _pick(self, counts, minimum=15):
        return pick_playable_entity('user', self.DAY, self.NAMES, counts, self.WINDOWS, minimum)

    def test_the_drawn_name_wins_when_it_can_fill_the_mix(self):
        drawn = self.NAMES[self._start()]
        counts = dict.fromkeys(self.NAMES, (20, 20, 20))
        self.assertEqual(self._pick(counts), (drawn, 90))
        self.assertEqual(drawn, pick_daily_entity('user', self.DAY, self.NAMES))

    def test_a_name_with_nothing_playable_is_skipped_for_the_next_ranked(self):
        start = self._start()
        following = self.NAMES[(start + 1) % len(self.NAMES)]
        counts = dict.fromkeys(self.NAMES, (20, 20, 20))
        del counts[self.NAMES[start]]
        self.assertEqual(self._pick(counts), (following, 90))

    def test_a_name_below_the_minimum_is_skipped(self):
        start = self._start()
        following = self.NAMES[(start + 1) % len(self.NAMES)]
        counts = dict.fromkeys(self.NAMES, (20, 20, 20))
        counts[self.NAMES[start]] = (14, 14, 14)
        self.assertEqual(self._pick(counts), (following, 90))

    def test_the_walk_wraps_around_the_end_of_the_ranking(self):
        start = self._start()
        before = self.NAMES[(start - 1) % len(self.NAMES)]
        self.assertEqual(self._pick({before: (0, 0, 15)}), (before, None))

    def test_the_drawn_name_at_a_wider_window_beats_the_next_name_at_ninety_days(self):
        start = self._start()
        counts = dict.fromkeys(self.NAMES, (20, 20, 20))
        counts[self.NAMES[start]] = (2, 15, 30)
        self.assertEqual(self._pick(counts), (self.NAMES[start], 365))

    def test_counts_are_matched_case_insensitively(self):
        mixed = ['Angerfist']
        self.assertEqual(
            pick_playable_entity('user', self.DAY, mixed, {'angerfist': (15, 15, 15)}, self.WINDOWS, 15),
            ('Angerfist', 90),
        )

    def test_nothing_qualifies_is_none(self):
        self.assertIsNone(self._pick(dict.fromkeys(self.NAMES, (14, 14, 14))))
        self.assertIsNone(self._pick({}))

    def test_no_names_is_none(self):
        self.assertIsNone(pick_playable_entity('user', self.DAY, [], {}, self.WINDOWS, 15))


class RediscoveryFactorTest(unittest.TestCase):
    """Bug report 131: the older half prefers songs not played lately."""

    NOW = datetime(2026, 9, 29, 12, 0, 0)

    def test_never_played_and_long_ago_keep_their_full_score(self):
        self.assertEqual(rediscovery_factor(None, self.NOW), 1.0)
        self.assertEqual(rediscovery_factor(self.NOW - timedelta(days=400), self.NOW), 1.0)

    def test_played_today_keeps_the_floor_and_it_rises_with_age(self):
        today = rediscovery_factor(self.NOW, self.NOW)
        month = rediscovery_factor(self.NOW - timedelta(days=30), self.NOW)
        quarter = rediscovery_factor(self.NOW - timedelta(days=90), self.NOW)
        self.assertAlmostEqual(today, 0.2)
        self.assertLess(today, month)
        self.assertLess(month, quarter)
        self.assertLess(quarter, 1.0)

    def test_a_scaled_down_weight_is_drawn_later_not_floored_away(self):
        day = date(2026, 9, 29)
        self.assertGreater(daily_sample_key('user', day, 'uid', 0.002), daily_sample_key('user', day, 'uid', 0.01))
