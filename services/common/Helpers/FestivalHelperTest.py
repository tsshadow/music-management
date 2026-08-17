import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from services.common.Helpers.FestivalHelper import Festival, FestivalHelper


def helper_with(*festivals: Festival) -> FestivalHelper:
    helper = FestivalHelper(preload=False)
    helper.set_festivals(list(festivals))
    return helper


DEFQON = Festival(name='Defqon', aliases=['Defqon', 'Defqon.1'], editions={2022: date(2022, 6, 24)})
QLIMAX = Festival(name='Qlimax', aliases=['Qlimax'], editions={})
REBIRTH = Festival(name='REBiRTH Festival', aliases=['Rebirth', 'Rebirth Festival'], editions={})
KARNAVAL = Festival(name='Karnaval Festival', aliases=['Karnaval Festival'], editions={})
INTENTS = Festival(name='Intents Festival', aliases=['Intents', 'Intents Festival'], editions={})


class NormalizeTest(unittest.TestCase):

    def test_strips_accents_and_case(self):
        self.assertEqual(FestivalHelper.normalize('Décibel'), ' decibel ')

    def test_collapses_punctuation_to_single_spaces(self):
        self.assertEqual(FestivalHelper.normalize('Defqon.1  Weekend-Festival'), ' defqon 1 weekend festival ')

    def test_pads_so_matching_lands_on_word_boundaries(self):
        self.assertTrue(FestivalHelper.normalize('Rise').startswith(' '))
        self.assertTrue(FestivalHelper.normalize('Rise').endswith(' '))


class FestivalHelperMatchTest(unittest.TestCase):

    def test_matches_an_alias_anywhere_in_the_text(self):
        result = helper_with(QLIMAX).get('Ran-D at Qlimax, full set')
        self.assertEqual(result['festival'], 'Qlimax')

    def test_returns_the_canonical_name_not_the_alias(self):
        result = helper_with(REBIRTH).get('liveset from rebirth 2023')
        self.assertEqual(result['festival'], 'REBiRTH Festival')

    def test_a_year_is_not_required(self):
        result = helper_with(QLIMAX).get('Qlimax warm up mix')
        self.assertEqual(result['festival'], 'Qlimax')
        self.assertNotIn('date', result)

    def test_adds_the_date_when_the_edition_is_known(self):
        result = helper_with(DEFQON).get('Rebelion | Defqon.1 Weekend Festival 2022 | RED')
        self.assertEqual(result['festival'], 'Defqon')
        self.assertEqual(result['year'], 2022)
        self.assertEqual(result['date'], '2022-06-24')

    def test_keeps_the_festival_when_the_edition_is_unknown(self):
        result = helper_with(DEFQON).get('Defqon.1 2019 endshow')
        self.assertEqual(result['festival'], 'Defqon')
        self.assertEqual(result['year'], 2019)
        self.assertNotIn('date', result)

    def test_prefers_the_longest_matching_alias(self):
        result = helper_with(INTENTS, KARNAVAL).get('VA - Intents Karnaval Festival 2021 (Warm Up Mix)')
        self.assertEqual(result['festival'], 'Karnaval Festival')

    def test_matches_on_word_boundaries_only(self):
        rise = Festival(name='Rise', aliases=['Rise'], editions={})
        self.assertIsNone(helper_with(rise).get('Sunrise Festival 2019'))

    def test_ignores_accents_and_punctuation_on_both_sides(self):
        decibel = Festival(name='Decibel', aliases=['Decibel'], editions={})
        self.assertEqual(helper_with(decibel).get('Décibel 2023')['festival'], 'Decibel')

    def test_tolerates_padding_in_the_stored_alias(self):
        padded = Festival(name='REBELLiON', aliases=['REBELLiON '], editions={})
        self.assertEqual(helper_with(padded).get('Rebellion')['festival'], 'REBELLiON')

    def test_returns_none_without_a_match(self):
        self.assertIsNone(helper_with(QLIMAX).get('Unknown Event 2021'))

    def test_returns_none_for_empty_input(self):
        self.assertIsNone(helper_with(QLIMAX).get(''))

    def test_require_year_skips_text_without_a_year(self):
        self.assertIsNone(helper_with(QLIMAX).get('Livesets/Qlimax', require_year=True))

    def test_require_year_matches_text_with_a_year(self):
        result = helper_with(QLIMAX).get('Livesets/Qlimax 2022/set.mp3', require_year=True)
        self.assertEqual(result['festival'], 'Qlimax')

    def test_uses_the_last_year_in_the_text(self):
        result = helper_with(DEFQON).get('Livesets/Defqon.1 2019/track from a 2022 album')
        self.assertEqual(result['year'], 2022)

    def test_ignores_numbers_that_are_not_years(self):
        self.assertNotIn('year', helper_with(QLIMAX).get('Qlimax 1080p x264'))


class FestivalHelperPreloadTest(unittest.TestCase):

    def setUp(self):
        patcher = patch('services.common.Helpers.FestivalHelper.DatabaseConnector')
        self.addCleanup(patcher.stop)
        self.mock_connector_cls = patcher.start()
        self.mock_connection = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_connection.cursor.return_value.__enter__.return_value = self.mock_cursor
        self.mock_connector_cls.return_value.connect.return_value = self.mock_connection

    def test_builds_festivals_from_the_three_tables(self):
        self.mock_cursor.fetchall.side_effect = [
            [(1, 'Qlimax'), (2, 'Defqon')],
            [(1, 'Qlimax'), (2, 'Defqon'), (2, 'Defqon.1')],
            [(2, 2022, date(2022, 6, 24))],
        ]
        helper = FestivalHelper()
        self.assertEqual(helper.get('Qlimax 2018')['festival'], 'Qlimax')
        self.assertEqual(helper.get('Defqon.1 2022')['date'], '2022-06-24')

    def test_a_failing_query_leaves_the_helper_usable(self):
        self.mock_cursor.execute.side_effect = Exception('DB error')
        helper = FestivalHelper()
        self.assertIsNone(helper.get('Defqon.1 2022'))
        self.mock_connection.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
