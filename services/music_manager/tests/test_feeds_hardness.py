import unittest

from services.music_manager.feeds.hardness import (
    ANCHOR_HARDNESS,
    DEFAULT_BAND_EDGES,
    classify_band,
    hardness_percentiles,
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


class DefaultBandEdgesTest(unittest.TestCase):
    """The band edges are fixed on the genre anchors now, not derived from any one

    listener's history -- see hardness.py's module docstring for why: a listener
    whose own listening skews hard must not see "hard" redefined as "what they
    already play". 50 keeps hardstyle and mainstream hardstyle (both 45) soft; 75
    keeps raw hardstyle/hardcore/mainstream hardcore (65/70/70) mid and puts gabber
    (75, exactly on the edge, `classify_band`'s `>= hi` favouring hard) and up in
    the hard band.
    """

    def test_the_default_matches_the_genre_anchors(self):
        self.assertEqual(DEFAULT_BAND_EDGES, (50.0, 75.0))

    def test_the_soft_mid_split_keeps_hardstyle_soft_and_raw_hardstyle_mid(self):
        lo, hi = DEFAULT_BAND_EDGES
        self.assertEqual(classify_band(ANCHOR_HARDNESS['euphoric hardstyle'], lo, hi), 'soft')
        self.assertEqual(classify_band(ANCHOR_HARDNESS['hardstyle'], lo, hi), 'soft')
        self.assertEqual(classify_band(ANCHOR_HARDNESS['mainstream hardstyle'], lo, hi), 'soft')
        self.assertEqual(classify_band(ANCHOR_HARDNESS['raw hardstyle'], lo, hi), 'mid')

    def test_the_mid_hard_split_keeps_hardcore_mid_and_gabber_and_up_hard(self):
        lo, hi = DEFAULT_BAND_EDGES
        self.assertEqual(classify_band(ANCHOR_HARDNESS['hardcore'], lo, hi), 'mid')
        self.assertEqual(classify_band(ANCHOR_HARDNESS['mainstream hardcore'], lo, hi), 'mid')
        self.assertEqual(classify_band(ANCHOR_HARDNESS['gabber'], lo, hi), 'hard')
        self.assertEqual(classify_band(ANCHOR_HARDNESS['uptempo hardcore'], lo, hi), 'hard')
        self.assertEqual(classify_band(ANCHOR_HARDNESS['terror'], lo, hi), 'hard')


class HardnessPercentilesTest(unittest.TestCase):
    """Purely informational now -- see DefaultBandEdgesTest above for what decides

    the band. Still worth getting right: it is what a listener sees when they ask
    where their own taste actually sits.
    """

    def test_no_history_at_all_reports_nothing(self):
        self.assertIsNone(hardness_percentiles([]))

    def test_a_single_uniform_value_is_every_percentile(self):
        weighted = [(50.0, 1.0)] * 40
        self.assertEqual(hardness_percentiles(weighted), {'p33': 50.0, 'p50': 50.0, 'p67': 50.0})

    def test_a_spread_out_taste_reports_distinct_percentiles(self):
        # 30 tracks evenly spread 10..100 in steps of 3.
        weighted = [(10.0 + 3.0 * i, 1.0) for i in range(30)]
        percentiles = hardness_percentiles(weighted)
        self.assertLess(percentiles['p33'], percentiles['p50'])
        self.assertLess(percentiles['p50'], percentiles['p67'])

    def test_recency_and_confidence_can_outweigh_raw_track_count(self):
        """The distribution is weighted, not a plain count -- a handful of

        heavily-weighted recent plays should not read the same as an equally
        sized but barely-weighted one.
        """
        heavy_soft = [(20.0, 3.0)] * 20
        light_hard = [(90.0, 0.01)] * 20
        percentiles = hardness_percentiles(heavy_soft + light_hard)
        # The soft cluster dominates the weighted mass, so even p67 should land
        # far below the hard cluster's value.
        self.assertLess(percentiles['p67'], 90.0)


class ClassifyBandTest(unittest.TestCase):
    def test_at_or_below_the_low_edge_is_soft(self):
        self.assertEqual(classify_band(30, 40, 70), 'soft')
        self.assertEqual(classify_band(40, 40, 70), 'soft')

    def test_at_or_above_the_high_edge_is_hard(self):
        self.assertEqual(classify_band(70, 40, 70), 'hard')
        self.assertEqual(classify_band(90, 40, 70), 'hard')

    def test_strictly_between_is_mid(self):
        self.assertEqual(classify_band(55, 40, 70), 'mid')


def test_track_hardness_accepts_database_decimals():
    """A DECIMAL BPM or mean from MariaDB arrives as Decimal and must not raise (500 on daily-mix-soft)."""
    from decimal import Decimal

    from services.music_manager.feeds.hardness import tempo_hardness, track_hardness

    value, source = track_hardness(None, None, None, None, Decimal('150.25'))
    assert source == 'tempo'
    assert value == tempo_hardness(150.25)
    assert track_hardness(Decimal('120'), Decimal('2'), None, None, None) == (60.0, 'genre')
    assert track_hardness(None, None, Decimal('42.5'), None, None) == (42.5, 'label')
