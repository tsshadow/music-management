import unittest

from services.music_manager.feeds.hardness import (
    ANCHOR_HARDNESS,
    classify_band,
    hardness_band_edges,
    seed_genre_hardness,
    tempo_hardness,
    track_hardness,
)

PARENTS = {'upterror': {'uptempo', 'terror'}, 'uptempo': {'hardcore'}, 'terror': {'hardcore'}}


class _FakeGenreCursor:
    """Just enough of a cursor for `seed_genre_hardness`: two SELECTs it tells

    apart by their statement text, and an UPDATE it applies to its own in-memory
    rows -- so a test can assert both what was written and what a second read
    would now see, without a real database.
    """

    def __init__(self, genre_rows, hierarchy_rows=()):
        self.rows = {row['id']: dict(row) for row in genre_rows}
        self.hierarchy_rows = list(hierarchy_rows)
        self.updates: list[tuple[int, float | None]] = []
        self._pending: list[dict] = []

    def execute(self, sql, params=None):
        statement = ' '.join(sql.split())
        if statement.startswith('SELECT id, name, hardness FROM rules_genres'):
            self._pending = [dict(row) for row in self.rows.values()]
        elif statement.startswith('SELECT subgenre, genre FROM rules_subgenre_hierarchy'):
            self._pending = list(self.hierarchy_rows)
        elif statement.startswith('UPDATE rules_genres SET hardness'):
            value, genre_id = params
            self.updates.append((genre_id, value))
            if self.rows[genre_id]['hardness'] is None:
                self.rows[genre_id]['hardness'] = value
            self._pending = []
        else:  # pragma: no cover - defensive, every statement above is exhaustive
            raise AssertionError(f'unexpected statement: {statement}')

    def fetchall(self):
        return self._pending


class SeedGenreHardnessTest(unittest.TestCase):
    def test_an_anchor_name_is_seeded_directly(self):
        cursor = _FakeGenreCursor([{'id': 1, 'name': 'Hardcore', 'hardness': None}])
        seed_genre_hardness(cursor)
        self.assertEqual(cursor.rows[1]['hardness'], ANCHOR_HARDNESS['hardcore'])

    def test_matching_is_case_insensitive(self):
        cursor = _FakeGenreCursor([{'id': 1, 'name': 'HARDCORE', 'hardness': None}])
        seed_genre_hardness(cursor)
        self.assertEqual(cursor.rows[1]['hardness'], ANCHOR_HARDNESS['hardcore'])

    def test_an_uncurated_genre_inherits_its_nearest_ancestor(self):
        """Upterror carries no anchor of its own; Hardcore does. The hierarchy

        walk should resolve the whole chain in one pass, not need a second
        startup to notice Hardcore was just seeded.
        """
        cursor = _FakeGenreCursor(
            [
                {'id': 1, 'name': 'Hardcore', 'hardness': None},
                {'id': 2, 'name': 'Upterror', 'hardness': None},
            ],
            hierarchy_rows=[{'subgenre': 'Upterror', 'genre': 'Hardcore'}],
        )
        seed_genre_hardness(cursor)
        self.assertEqual(cursor.rows[2]['hardness'], ANCHOR_HARDNESS['hardcore'])

    def test_a_multi_level_chain_resolves_in_one_pass(self):
        """Upterror -> Uptempo -> Hardcore: two hops from the nearest anchor,

        with nothing in between carrying one of its own. `nearest_ancestor`
        already walks the whole graph per call, so this must not depend on
        processing order.
        """
        cursor = _FakeGenreCursor(
            [
                {'id': 1, 'name': 'Hardcore', 'hardness': None},
                {'id': 2, 'name': 'Uptempo Custom', 'hardness': None},
                {'id': 3, 'name': 'Deep Uptempo Custom', 'hardness': None},
            ],
            hierarchy_rows=[
                {'subgenre': 'Deep Uptempo Custom', 'genre': 'Uptempo Custom'},
                {'subgenre': 'Uptempo Custom', 'genre': 'Hardcore'},
            ],
        )
        seed_genre_hardness(cursor)
        self.assertEqual(cursor.rows[3]['hardness'], ANCHOR_HARDNESS['hardcore'])

    def test_a_genre_with_no_anchor_ancestor_is_left_null(self):
        cursor = _FakeGenreCursor([{'id': 1, 'name': 'Completely Unrelated Genre', 'hardness': None}])
        seed_genre_hardness(cursor)
        self.assertIsNone(cursor.rows[1]['hardness'])

    def test_a_curators_own_value_is_never_overwritten(self):
        """Idempotent, and safe to run on every startup: a genre that already

        has a hardness -- however it got one -- is never touched again, even
        when its name also happens to be an anchor with a different value.
        """
        cursor = _FakeGenreCursor([{'id': 1, 'name': 'Hardcore', 'hardness': 12}])
        updated = seed_genre_hardness(cursor)
        self.assertEqual(cursor.rows[1]['hardness'], 12)
        self.assertEqual(updated, 0)
        self.assertEqual(cursor.updates, [])

    def test_running_it_twice_changes_nothing_the_second_time(self):
        cursor = _FakeGenreCursor(
            [
                {'id': 1, 'name': 'Hardcore', 'hardness': None},
                {'id': 2, 'name': 'Upterror', 'hardness': None},
            ],
            hierarchy_rows=[{'subgenre': 'Upterror', 'genre': 'Hardcore'}],
        )
        first = seed_genre_hardness(cursor)
        second = seed_genre_hardness(cursor)
        self.assertEqual(first, 2)
        self.assertEqual(second, 0)


class TempoHardnessTest(unittest.TestCase):
    def test_at_or_below_the_lowest_anchor_is_clamped(self):
        self.assertEqual(tempo_hardness(120), 20.0)
        self.assertEqual(tempo_hardness(140), 20.0)

    def test_at_or_above_the_highest_anchor_is_clamped(self):
        self.assertEqual(tempo_hardness(200), 95.0)
        self.assertEqual(tempo_hardness(230), 95.0)

    def test_between_two_anchors_it_interpolates_linearly(self):
        self.assertAlmostEqual(tempo_hardness(145), 32.5)  # halfway between 140/20 and 150/45

    def test_no_tempo_is_no_estimate(self):
        self.assertIsNone(tempo_hardness(None))


class TrackHardnessTest(unittest.TestCase):
    def test_a_known_genre_wins_over_every_other_signal(self):
        value, source = track_hardness(140.0, 2.0, label_mean=10.0, artist_mean=10.0, tempo=200)
        self.assertEqual(value, 70.0)
        self.assertEqual(source, 'genre')

    def test_zero_genre_weight_falls_through_to_the_label(self):
        value, source = track_hardness(0.0, 0.0, label_mean=55.0, artist_mean=10.0, tempo=200)
        self.assertEqual(value, 55.0)
        self.assertEqual(source, 'label')

    def test_no_label_falls_through_to_the_artist(self):
        value, source = track_hardness(None, 0.0, label_mean=None, artist_mean=42.0, tempo=200)
        self.assertEqual(value, 42.0)
        self.assertEqual(source, 'artist')

    def test_no_label_or_artist_falls_through_to_tempo(self):
        value, source = track_hardness(None, 0.0, label_mean=None, artist_mean=None, tempo=200)
        self.assertEqual(value, 95.0)
        self.assertEqual(source, 'tempo')

    def test_nothing_at_all_is_none(self):
        value, source = track_hardness(None, 0.0, label_mean=None, artist_mean=None, tempo=None)
        self.assertIsNone(value)
        self.assertEqual(source, 'none')


class HardnessBandEdgesTest(unittest.TestCase):
    def test_a_narrow_taste_still_gets_two_distinct_edges(self):
        """A listener whose whole 30+ tracks sit around one hardness value would

        otherwise get a soft/hard edge closer than 15 points apart -- three
        mixes drawing from a five-point-wide slice each are not three
        different mixes. The median +/- 15 fallback is what keeps them apart.
        """
        weighted = [(50.0, 1.0)] * 40
        lo, hi = hardness_band_edges(weighted)
        self.assertEqual((lo, hi), (35.0, 65.0))

    def test_a_cold_start_listener_gets_the_fixed_fallback(self):
        weighted = [(50.0, 1.0)] * 10  # below MIN_TRACKS_FOR_OWN_BAND
        self.assertEqual(hardness_band_edges(weighted), (40.0, 70.0))

    def test_no_history_at_all_is_the_same_fixed_fallback(self):
        self.assertEqual(hardness_band_edges([]), (40.0, 70.0))

    def test_a_spread_out_taste_uses_its_own_percentiles(self):
        # 30 tracks evenly spread 10..100 in steps of 3: p33 and p67 are comfortably
        # more than 15 points apart, so the listener's own numbers are used as-is.
        weighted = [(10.0 + 3.0 * i, 1.0) for i in range(30)]
        lo, hi = hardness_band_edges(weighted)
        self.assertGreater(hi - lo, 15.0)
        self.assertLess(lo, 50.0)
        self.assertGreater(hi, 50.0)

    def test_recency_and_confidence_can_outweigh_raw_track_count(self):
        """The distribution is weighted, not a plain count -- a handful of

        heavily-weighted recent plays should not read the same as an equally
        sized but barely-weighted one.
        """
        heavy_soft = [(20.0, 3.0)] * 20
        light_hard = [(90.0, 0.01)] * 20
        lo, hi = hardness_band_edges(heavy_soft + light_hard)
        # The soft cluster dominates the weighted mass, so even p67 should land
        # far below the hard cluster's value.
        self.assertLess(hi, 90.0)


class ClassifyBandTest(unittest.TestCase):
    def test_at_or_below_the_low_edge_is_soft(self):
        self.assertEqual(classify_band(30, 40, 70), 'soft')
        self.assertEqual(classify_band(40, 40, 70), 'soft')

    def test_at_or_above_the_high_edge_is_hard(self):
        self.assertEqual(classify_band(70, 40, 70), 'hard')
        self.assertEqual(classify_band(90, 40, 70), 'hard')

    def test_strictly_between_is_mid(self):
        self.assertEqual(classify_band(55, 40, 70), 'mid')
