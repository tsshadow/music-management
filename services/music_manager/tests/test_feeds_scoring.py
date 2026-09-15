import unittest
from datetime import date

from services.music_manager.feeds.policy import POLICIES
from services.music_manager.feeds.profile import TasteProfile
from services.music_manager.feeds.scoring import daily_sample_key, pick_daily_entity, score, taste_score

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
