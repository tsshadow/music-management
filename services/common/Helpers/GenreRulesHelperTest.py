import unittest
from services.common.Helpers.GenreRulesHelper import GenreRulesHelper, GenreRow, WHITE, BLACK, UNKNOWN


def helper_with(rows):
    return GenreRulesHelper(preload=False, rows=rows)


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
        self.helper = helper_with([self.hardstyle, self.uptempo_hardcore, self.uptempo_alias, self.arts, self.pending, self.raw_alias, self.raw_hardstyle])

    def test_white_genre_is_kept_with_database_casing(self):
        decision = self.helper.resolve('hardstyle')
        self.assertEqual(decision.state, WHITE)
        self.assertEqual(decision.value, 'Hardstyle')

    def test_black_genre_is_dropped(self):
        decision = self.helper.resolve('Arts')
        self.assertEqual(decision.state, BLACK)
        self.assertIsNone(decision.value)

    def test_black_genre_with_canonical_is_rewritten(self):
        decision = self.helper.resolve('uptempo')
        self.assertEqual(decision.state, BLACK)
        self.assertEqual(decision.value, 'Uptempo Hardcore')

    def test_white_genre_with_canonical_is_rewritten(self):
        decision = self.helper.resolve('Rawstyle')
        self.assertEqual(decision.state, WHITE)
        self.assertEqual(decision.value, 'Raw Hardstyle')

    def test_unseen_genre_is_unknown_and_keeps_its_value(self):
        decision = self.helper.resolve('Speedcore')
        self.assertEqual(decision.state, UNKNOWN)
        self.assertEqual(decision.value, 'Speedcore')

    def test_registered_but_undecided_genre_stays_unknown(self):
        decision = self.helper.resolve('tribecore')
        self.assertEqual(decision.state, UNKNOWN)
        self.assertEqual(decision.value, 'tribecore')

    def test_empty_genre_is_dropped(self):
        decision = self.helper.resolve('   ')
        self.assertEqual(decision.state, BLACK)
        self.assertIsNone(decision.value)

    def test_lookup_ignores_casing_and_punctuation(self):
        self.assertEqual(self.helper.resolve('RAW-HARDSTYLE').value, 'Raw Hardstyle')

    def test_canonical_pointing_at_itself_does_not_loop(self):
        self_referencing = GenreRow(1, 'Hardcore', 'hardcore', WHITE, 1)
        decision = helper_with([self_referencing]).resolve('hardcore')
        self.assertEqual(decision.value, 'Hardcore')


if __name__ == '__main__':
    unittest.main()
