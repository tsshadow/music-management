import unittest

from services.common.Helpers.GenreRulesHelper import BLACK, UNKNOWN, WHITE, GenreRow, GenreRulesHelper


def helper_with(rows, expansions=None):
    """Build a helper, deriving expansions from canonical_id like the migration does."""
    if expansions is None:
        expansions = {row.id: [row.canonical_id] for row in rows if row.canonical_id and row.canonical_id != row.id}
    return GenreRulesHelper(preload=False, rows=rows, expansions=expansions)


class GenreRulesHelperNormalizeTest(unittest.TestCase):
    def test_normalizes_casing_and_punctuation(self):
        self.assertEqual(GenreRulesHelper.normalize('Raw  Hardstyle'), 'raw hardstyle')
        self.assertEqual(GenreRulesHelper.normalize('raw-hardstyle'), 'raw hardstyle')
        self.assertEqual(GenreRulesHelper.normalize('  RAW/HARDSTYLE  '), 'raw hardstyle')

    def test_strips_accents(self):
        self.assertEqual(GenreRulesHelper.normalize('Frenchcöre'), 'frenchcore')

    def test_empty_input_yields_empty_key(self):
        self.assertEqual(GenreRulesHelper.normalize('   '), '')
        self.assertEqual(GenreRulesHelper.normalize(''), '')


class GenreRulesHelperResolveTest(unittest.TestCase):
    def setUp(self):
        self.hardstyle = GenreRow(1, 'Hardstyle', 'hardstyle', WHITE, None)
        self.uptempo_hardcore = GenreRow(2, 'Uptempo Hardcore', 'uptempo hardcore', WHITE, None)
        self.uptempo_alias = GenreRow(3, 'uptempo', 'uptempo', BLACK, 2)
        self.arts = GenreRow(4, 'Arts', 'arts', BLACK, None)
        self.pending = GenreRow(5, 'Tribecore', 'tribecore', UNKNOWN, None)
        self.raw_alias = GenreRow(6, 'rawstyle', 'rawstyle', WHITE, 7)
        self.raw_hardstyle = GenreRow(7, 'Raw Hardstyle', 'raw hardstyle', WHITE, None)
        self.helper = helper_with(
            [
                self.hardstyle,
                self.uptempo_hardcore,
                self.uptempo_alias,
                self.arts,
                self.pending,
                self.raw_alias,
                self.raw_hardstyle,
            ]
        )

    def test_white_genre_is_kept_with_database_casing(self):
        decision = self.helper.resolve('hardstyle')
        self.assertEqual(decision.state, WHITE)
        self.assertEqual(decision.values, ['Hardstyle'])

    def test_black_genre_is_dropped(self):
        decision = self.helper.resolve('Arts')
        self.assertEqual(decision.state, BLACK)
        self.assertEqual(decision.values, [])

    def test_black_genre_with_canonical_is_rewritten(self):
        decision = self.helper.resolve('uptempo')
        self.assertEqual(decision.state, BLACK)
        self.assertEqual(decision.values, ['Uptempo Hardcore'])

    def test_white_genre_with_canonical_is_rewritten(self):
        decision = self.helper.resolve('Rawstyle')
        self.assertEqual(decision.state, WHITE)
        self.assertEqual(decision.values, ['Raw Hardstyle'])

    def test_unseen_genre_is_unknown_and_keeps_its_value(self):
        decision = self.helper.resolve('Speedcore')
        self.assertEqual(decision.state, UNKNOWN)
        self.assertEqual(decision.values, ['Speedcore'])

    def test_registered_but_undecided_genre_stays_unknown(self):
        decision = self.helper.resolve('tribecore')
        self.assertEqual(decision.state, UNKNOWN)
        self.assertEqual(decision.values, ['tribecore'])

    def test_empty_genre_is_dropped(self):
        decision = self.helper.resolve('   ')
        self.assertEqual(decision.state, BLACK)
        self.assertEqual(decision.values, [])

    def test_lookup_ignores_casing_and_punctuation(self):
        self.assertEqual(self.helper.resolve('RAW-HARDSTYLE').values, ['Raw Hardstyle'])

    def test_canonical_pointing_at_itself_does_not_loop(self):
        self_referencing = GenreRow(1, 'Hardcore', 'hardcore', WHITE, 1)
        decision = helper_with([self_referencing]).resolve('hardcore')
        self.assertEqual(decision.values, ['Hardcore'])


class GenreRulesHelperExpansionTest(unittest.TestCase):
    """A contraction resolves to several genres at once."""

    def setUp(self):
        self.uptempo = GenreRow(1, 'Uptempo Hardcore', 'uptempo hardcore', WHITE, None)
        self.terror = GenreRow(2, 'Terror', 'terror', WHITE, None)
        self.upterror = GenreRow(3, 'Upterror', 'upterror', BLACK, None)
        self.helper = helper_with([self.uptempo, self.terror, self.upterror], expansions={3: [1, 2]})

    def test_contraction_expands_to_every_target(self):
        decision = self.helper.resolve('upterror')
        self.assertEqual(decision.state, BLACK)
        self.assertEqual(decision.values, ['Uptempo Hardcore', 'Terror'])

    def test_expansion_keeps_the_configured_order(self):
        reordered = helper_with([self.uptempo, self.terror, self.upterror], expansions={3: [2, 1]})
        self.assertEqual(reordered.resolve('Upterror').values, ['Terror', 'Uptempo Hardcore'])

    def test_expansion_wins_over_the_state(self):
        """A rejected genre with targets is rewritten, not dropped."""
        self.assertNotEqual(self.helper.resolve('Upterror').values, [])

    def test_target_that_no_longer_exists_is_skipped(self):
        stale = helper_with([self.uptempo, self.upterror], expansions={3: [1, 99]})
        self.assertEqual(stale.resolve('Upterror').values, ['Uptempo Hardcore'])

    def test_expansion_pointing_at_itself_is_ignored(self):
        looping = helper_with([self.upterror], expansions={3: [3]})
        self.assertEqual(looping.resolve('Upterror').values, [])


class GenreRulesHelperSplitTest(unittest.TestCase):
    """'Hardstyle/Hardcore' is two genres, not one."""

    def setUp(self):
        self.hardstyle = GenreRow(1, 'Hardstyle', 'hardstyle', WHITE, None)
        self.pending = GenreRow(2, 'Tribecore', 'tribecore', UNKNOWN, None)
        self.slashed = GenreRow(3, 'AC/DC Tribute', 'ac dc tribute', WHITE, None)
        self.helper = helper_with([self.hardstyle, self.pending, self.slashed])

    def test_splits_on_a_slash(self):
        self.assertEqual(self.helper.split_composite('Hardstyle/Hardcore'), ['Hardstyle', 'Hardcore'])

    def test_splits_more_than_two(self):
        self.assertEqual(
            self.helper.split_composite('Hardcore/Frenchcore/Hardmusic'), ['Hardcore', 'Frenchcore', 'Hardmusic']
        )

    def test_trims_the_parts(self):
        self.assertEqual(self.helper.split_composite('Hardstyle / Hardcore'), ['Hardstyle', 'Hardcore'])

    def test_leaves_a_plain_genre_alone(self):
        self.assertEqual(self.helper.split_composite('Hardstyle'), ['Hardstyle'])

    def test_a_decided_genre_is_never_split(self):
        """Approving a name that contains a slash protects it permanently."""
        self.assertEqual(self.helper.split_composite('AC/DC Tribute'), ['AC/DC Tribute'])

    def test_an_undecided_genre_is_still_split(self):
        """Sitting in the queue is not a decision, so the composite still splits."""
        self.assertEqual(self.helper.split_composite('Tribecore/Speedcore'), ['Tribecore', 'Speedcore'])

    def test_trailing_slash_is_cleaned_off(self):
        self.assertEqual(self.helper.split_composite('Hardcore/'), ['Hardcore'])

    def test_slash_only_input_is_left_alone(self):
        self.assertEqual(self.helper.split_composite('///'), ['///'])


if __name__ == '__main__':
    unittest.main()
