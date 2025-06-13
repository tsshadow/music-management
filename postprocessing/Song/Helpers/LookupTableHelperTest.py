import unittest
from unittest.mock import MagicMock, patch
from postprocessing.Song.Helpers.LookupTableHelper import LookupTableHelper

class LookupTableHelperTest(unittest.TestCase):

    def setUp(self):
        patcher = patch("postprocessing.Song.Helpers.LookupTableHelper.DatabaseConnector")
        self.addCleanup(patcher.stop)
        self.mock_connector_cls = patcher.start()

        self.mock_connection = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_connection.cursor.return_value.__enter__.return_value = self.mock_cursor
        self.mock_connector_cls.return_value.connect.return_value = self.mock_connection

        self.helper = LookupTableHelper("artist_genre", "artist", "genre")

    def test_get_success(self):
        self.mock_cursor.fetchall.return_value = [("Hardcore",), ("Uptempo",)]
        result = self.helper.get("Evil Activities")
        self.mock_cursor.execute.assert_called_once_with(
            "SELECT genre FROM artist_genre WHERE artist = %s", ("Evil Activities",)
        )
        self.assertEqual(result, ["Hardcore", "Uptempo"])
        self.mock_connection.close.assert_called_once()

    def test_get_empty(self):
        self.mock_cursor.fetchall.return_value = []
        result = self.helper.get("Unknown Artist")
        self.assertEqual(result, [])
        self.mock_connection.close.assert_called_once()

    def test_get_exception(self):
        self.mock_cursor.execute.side_effect = Exception("DB Error")
        result = self.helper.get("Evil Activities")
        self.assertEqual(result, [])
        self.mock_connection.close.assert_called_once()

    def test_get_substring_success(self):
        self.mock_cursor.fetchall.return_value = [
            ("Hardcore", "NL"),
            ("Hard Bass", "NL"),
            ("Speedcore", "DE"),
            ("House", "FR")
        ]
        result = self.helper.get_substring("The rise of hardcore and speedcore music")
        expected = ["DE", "NL"]
        self.assertEqual(result, expected)
        self.mock_connection.close.assert_called_once()

    def test_get_substring_exception(self):
        self.mock_cursor.execute.side_effect = Exception("DB Fail")
        result = self.helper.get_substring("any text")
        self.assertEqual(result, [])
        self.mock_connection.close.assert_called_once()

unittest.TextTestRunner().run(unittest.TestLoader().loadTestsFromTestCase(LookupTableHelperTest))
