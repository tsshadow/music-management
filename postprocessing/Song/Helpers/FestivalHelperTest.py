import unittest
from unittest.mock import MagicMock, patch
from datetime import date

from postprocessing.Song.Helpers.FestivalHelper import FestivalHelper


class FestivalHelperTest(unittest.TestCase):

    def setUp(self):
        patcher = patch("postprocessing.Song.Helpers.FestivalHelper.DatabaseConnector")
        self.addCleanup(patcher.stop)
        self.mock_connector_cls = patcher.start()

        self.mock_connection = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_connection.cursor.return_value.__enter__.return_value = self.mock_cursor
        self.mock_connector_cls.return_value.connect.return_value = self.mock_connection

        self.helper = FestivalHelper()

    def test_extract_year_valid(self):
        self.assertEqual(self.helper._extract_year("Defqon.1 Weekend Festival 2022"), 2022)

    def test_extract_year_missing(self):
        self.assertIsNone(self.helper._extract_year("Summer Beats Vol. 3"))

    def test_get_match_found(self):
        self.mock_cursor.fetchall.return_value = [
            ("Defqon.1", date(2022, 6, 24)),
            ("Qlimax", date(2022, 11, 19))
        ]

        result = self.helper.get("MyLiveSet Defqon.1 2022.mp3")

        self.mock_cursor.execute.assert_called_once_with(
            "SELECT festival, date FROM festival_data WHERE year = %s", (2022,)
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["festival"], "Defqon.1")
        self.assertEqual(result["year"], 2022)
        self.assertEqual(result["date"], "2022-06-24")

    def test_get_no_year(self):
        result = self.helper.get("hardcore-legends.mp3")
        self.assertIsNone(result)
        self.mock_cursor.execute.assert_not_called()

    def test_get_no_matches(self):
        self.mock_cursor.fetchall.return_value = [
            ("Thunderdome", date(2021, 10, 30))
        ]
        result = self.helper.get("Unknown_Event_2021.mp3")
        self.assertIsNone(result)

    def test_get_returns_most_specific_match(self):
        self.mock_cursor.fetchall.return_value = [
            ("Rebirth", date(2023, 4, 8)),
            ("Rebirth Festival", date(2023, 4, 9))
        ]
        result = self.helper.get("liveset from rebirth festival 2023")
        self.assertIsNotNone(result)
        self.assertEqual(result["festival"], "Rebirth Festival")
        self.assertEqual(result["year"], 2023)
        self.assertEqual(result["date"], "2023-04-09")

    def test_get_query_exception(self):
        self.mock_cursor.execute.side_effect = Exception("DB error")
        result = self.helper.get("Dominator 2022")
        self.assertIsNone(result)
        self.mock_connection.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
