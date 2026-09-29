"""The "Oude hitjes" rules (feeds/old_hits.py): age, exclusions, tiers, filling and order."""

import unittest
from datetime import date, datetime, timedelta

from services.music_manager.feeds import old_hits
from services.music_manager.feeds.old_hits import (
    OldHitsConfig,
    Song,
    age_cutoff,
    artist_affinity,
    fill_tiers,
    interleave,
    is_old,
    parse_config,
    parse_shares,
    quotas,
    reason_for,
    song_rating,
    tier_favourites,
    tier_hits,
    tier_worn,
)

NOW = datetime(2026, 9, 29, 12, 0, 0)
TODAY = NOW.date()
CUTOFF = date(2023, 9, 29)
CFG = OldHitsConfig()


def _song(n, **kwargs):
    kwargs.setdefault('artist_id', n)
    kwargs.setdefault('old', True)
    return Song(key=('work', n), track_id=n, **kwargs)


def _heard(days):
    return NOW - timedelta(days=days)


class AgeTest(unittest.TestCase):
    def test_the_cutoff_is_calendar_years_back_and_survives_a_leap_day(self):
        self.assertEqual(age_cutoff(TODAY, 3), CUTOFF)
        self.assertEqual(age_cutoff(date(2028, 2, 29), 3), date(2025, 2, 28))

    def test_a_full_date_decides_first(self):
        self.assertTrue(is_old('2009-06-27', None, 0, 0, CUTOFF))
        self.assertFalse(is_old('2024-01-01', 2001, 10, 10, CUTOFF))

    def test_a_year_is_old_only_when_the_whole_year_lies_before_the_cutoff_year(self):
        self.assertTrue(is_old(None, 2022, 0, 0, CUTOFF))
        self.assertFalse(is_old(None, 2023, 0, 0, CUTOFF))
        # A bogus year (an analyzer zero) is no evidence at all.
        self.assertFalse(is_old(None, 0, 0, 0, CUTOFF))

    def test_an_undated_song_borrows_its_artists_age_only_with_enough_evidence(self):
        self.assertTrue(is_old(None, None, 10, 8, CUTOFF))
        self.assertFalse(is_old(None, None, 10, 7, CUTOFF))
        # Two dated tracks are too few to speak for the artist.
        self.assertFalse(is_old(None, None, 2, 2, CUTOFF))
        self.assertFalse(is_old('', None, 0, 0, CUTOFF))


class ConfigTest(unittest.TestCase):
    def test_defaults_when_nothing_is_set(self):
        self.assertEqual(parse_config(lambda key: None), OldHitsConfig())

    def test_values_are_read_and_garbage_falls_back_per_field(self):
        values = {
            old_hits.MIN_AGE_SETTING: '5',
            old_hits.REST_DAYS_SETTING: 'soon',
            old_hits.SHARES_SETTING: '2,1,1',
            old_hits.MAX_PER_ARTIST_SETTING: 0,
        }
        cfg = parse_config(values.get, size=50)
        self.assertEqual(cfg.min_age_years, 5)
        self.assertEqual(cfg.rest_days, 90)
        self.assertEqual(cfg.shares, (0.5, 0.25, 0.25))
        self.assertEqual(cfg.max_per_artist, 3)
        self.assertEqual(cfg.size, 50)

    def test_shares_must_be_three_non_negative_numbers(self):
        for raw in ('40,60', 'a,b,c', '-1,1,1', '0,0,0', None, 7):
            self.assertEqual(parse_shares(raw), OldHitsConfig.shares, raw)


class SongRatingTest(unittest.TestCase):
    def test_the_canonicals_own_rating_wins_over_a_higher_one_elsewhere(self):
        rows = [
            {'track_id': 1, 'work_id': 9, 'canonical_track_id': 1, 'rating': 3},
            {'track_id': 2, 'work_id': 9, 'canonical_track_id': 1, 'rating': 5},
        ]
        self.assertEqual(song_rating(rows), {('work', 9): 3})

    def test_without_a_rated_canonical_the_highest_counts(self):
        rows = [
            {'track_id': 2, 'work_id': 9, 'canonical_track_id': 1, 'rating': 2},
            {'track_id': 3, 'work_id': 9, 'canonical_track_id': 1, 'rating': 4},
            {'track_id': 7, 'work_id': None, 'canonical_track_id': None, 'rating': 5},
        ]
        self.assertEqual(song_rating(rows), {('work', 9): 4, ('track', 7): 5})


class AffinityTest(unittest.TestCase):
    def test_ratings_and_plays_add_up_and_disliked_artists_drop_out(self):
        songs = [
            _song(1, artist_id=10, rating=5),
            _song(2, artist_id=10, plays=20),
            _song(3, artist_id=20, rating=1),
            _song(4, artist_id=20, rating=4),
            _song(5, artist_id=30, rating=2),
            _song(6, artist_id=None, rating=5),
        ]
        affinity = artist_affinity(songs)
        self.assertGreater(affinity[10], 3.0)
        self.assertNotIn(20, affinity)
        self.assertNotIn(30, affinity)


class TierTest(unittest.TestCase):
    def test_favourites_are_old_4_5_star_songs_that_have_rested(self):
        songs = [
            _song(1, rating=5, last_heard=_heard(400)),
            _song(2, rating=4),  # never heard since the history began
            _song(3, rating=5, last_heard=_heard(30)),  # heard within rest_days
            _song(4, rating=3, last_heard=_heard(400)),
            _song(5, rating=5, last_heard=_heard(400), old=False),
        ]
        picked = tier_favourites(songs, CFG, NOW, 'user', TODAY)
        self.assertEqual({song.track_id for song in picked}, {1, 2})

    def test_worn_needs_enough_plays_and_a_long_silence_and_no_low_rating(self):
        songs = [
            _song(1, plays=12, last_heard=_heard(200)),
            _song(2, plays=2, last_heard=_heard(400)),
            _song(3, plays=30, last_heard=_heard(120)),
            _song(4, plays=9, last_heard=_heard(400), rating=2),
            _song(5, plays=9, last_heard=_heard(400), rating=1),
        ]
        picked = tier_worn(songs, CFG, NOW, 'user', TODAY)
        self.assertEqual([song.track_id for song in picked], [1])

    def test_hits_need_a_liked_artist_a_hit_signal_and_no_low_rating(self):
        songs = [
            _song(1, artist_id=10, popular_position=1, popular_source='deezer'),
            _song(2, artist_id=10, versions=6),
            _song(3, artist_id=10, versions=2),  # below min_versions and not on a top list
            _song(4, artist_id=99, popular_position=1),  # an artist the listener does not like
            _song(5, artist_id=10, popular_position=3, rating=2),
            _song(6, artist_id=10, popular_position=3, rating=3, last_heard=_heard(10)),
            _song(7, artist_id=10, popular_position=4, rating=3),
        ]
        picked = tier_hits(songs, {10: 4.0}, CFG, NOW, 'user', TODAY)
        self.assertEqual({song.track_id for song in picked}, {1, 2, 7})

    def test_the_order_is_stable_for_a_day_and_changes_the_next(self):
        songs = [_song(n, rating=5, last_heard=_heard(100 + n)) for n in range(1, 40)]
        first = [song.track_id for song in tier_favourites(songs, CFG, NOW, 'user', TODAY)]
        again = [song.track_id for song in tier_favourites(list(reversed(songs)), CFG, NOW, 'user', TODAY)]
        tomorrow = [song.track_id for song in tier_favourites(songs, CFG, NOW, 'user', TODAY + timedelta(days=1))]
        self.assertEqual(first, again)
        self.assertNotEqual(first, tomorrow)

    def test_longer_unheard_favourites_tend_to_come_first(self):
        stale = [_song(n, rating=5, last_heard=_heard(900)) for n in range(1, 21)]
        fresh = [_song(n, rating=5, last_heard=_heard(95)) for n in range(21, 41)]
        order = [song.track_id for song in tier_favourites(stale + fresh, CFG, NOW, 'user', TODAY)]
        self.assertGreater(sum(1 for track_id in order[:20] if track_id <= 20), 15)


class FillTest(unittest.TestCase):
    def _pool(self, start, count, artist=None):
        return [_song(n, artist_id=artist if artist is not None else n) for n in range(start, start + count)]

    def test_quotas_sum_to_the_size(self):
        self.assertEqual(quotas(100, (0.4, 0.3, 0.3)), [40, 30, 30])
        self.assertEqual(sum(quotas(10, (1 / 3, 1 / 3, 1 / 3))), 10)

    def test_full_pools_fill_in_proportion(self):
        pools = [self._pool(1, 100), self._pool(1001, 100), self._pool(2001, 100)]
        picked = fill_tiers(pools, (0.4, 0.3, 0.3), 100, 3)
        counts = [sum(1 for _, tier in picked if tier == index) for index in range(3)]
        self.assertEqual(counts, [40, 30, 30])

    def test_a_short_tier_passes_its_places_to_the_next(self):
        pools = [self._pool(1, 10), self._pool(1001, 100), self._pool(2001, 100)]
        picked = fill_tiers(pools, (0.4, 0.3, 0.3), 100, 3)
        counts = [sum(1 for _, tier in picked if tier == index) for index in range(3)]
        self.assertEqual(counts, [10, 60, 30])

    def test_a_short_last_tier_hands_back_to_the_first(self):
        pools = [self._pool(1, 100), self._pool(1001, 30), self._pool(2001, 5)]
        picked = fill_tiers(pools, (0.4, 0.3, 0.3), 100, 3)
        counts = [sum(1 for _, tier in picked if tier == index) for index in range(3)]
        self.assertEqual(counts, [65, 30, 5])

    def test_one_song_never_takes_two_places(self):
        shared = self._pool(1, 50)
        picked = fill_tiers([shared, shared, shared], (0.4, 0.3, 0.3), 100, 3)
        keys = [song.key for song, _ in picked]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(picked), 50)

    def test_no_artist_takes_more_than_the_cap(self):
        pools = [self._pool(1, 20, artist=7), self._pool(101, 20, artist=7), self._pool(201, 20)]
        picked = fill_tiers(pools, (0.4, 0.3, 0.3), 30, 3)
        self.assertEqual(sum(1 for song, _ in picked if song.artist_id == 7), 3)
        self.assertEqual(len(picked), 23)

    def test_interleave_lets_the_tiers_take_turns(self):
        pools = [self._pool(1, 100), self._pool(1001, 100), self._pool(2001, 100)]
        picked = fill_tiers(pools, (0.4, 0.3, 0.3), 10, 3)
        tiers = [tier for _, tier in interleave(picked)]
        self.assertEqual(sorted(tiers), sorted(tier for _, tier in picked))
        self.assertEqual(set(tiers[:3]), {0, 1, 2})
        # Within a tier the pick order is kept.
        firsts = [song.track_id for song, tier in interleave(picked) if tier == 0]
        self.assertEqual(firsts, sorted(firsts))

    def test_reasons_name_the_tier_and_the_evidence(self):
        self.assertEqual(reason_for(_song(1, rating=5), 0), 'favourite:5')
        self.assertEqual(reason_for(_song(1, plays=7), 1), 'worn:7')
        self.assertEqual(reason_for(_song(1, popular_source='deezer', popular_position=2), 2), 'hit:deezer:2')
        self.assertEqual(reason_for(_song(1, versions=6), 2), 'hit:versions:6')


if __name__ == '__main__':
    unittest.main()
