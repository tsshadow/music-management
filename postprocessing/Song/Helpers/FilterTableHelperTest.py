import unittest
from unittest.mock import MagicMock, patch
from postprocessing.Song.Helpers.FilterTableHelper import FilterTableHelper


class FilterTableHelperTest(unittest.TestCase):

    def setUp(self):
        patcher = patch("postprocessing.Song.Helpers.FilterTableHelper.DatabaseConnector")
        self.addCleanup(patcher.stop)
        self.mock_connector_cls = patcher.start()

        self.mock_connection = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_connection.cursor.return_value.__enter__.return_value = self.mock_cursor
        self.mock_connector_cls.return_value.connect.return_value = self.mock_connection

        self.helper = FilterTableHelper("genres", "name", "corrected_name")

    def test_exists_true(self):
        self.mock_cursor.fetchone.return_value = (1,)
        self.assertTrue(self.helper.exists("Hardcore"))
        self.mock_cursor.execute.assert_called_once()

    def test_exists_false(self):
        self.mock_cursor.fetchone.return_value = None
        self.assertFalse(self.helper.exists("UnknownGenre"))

    def test_get_corrected_found(self):
        self.mock_cursor.fetchone.return_value = ("Uptempo Hardcore",)
        result = self.helper.get_corrected("uptempo hardcore")
        self.assertEqual(result, "Uptempo Hardcore")

    def test_get_corrected_not_found(self):
        self.mock_cursor.fetchone.return_value = None
        result = self.helper.get_corrected("ambient")
        self.assertEqual(result, "")

    def test_get_corrected_or_exists_corrected(self):
        self.mock_cursor.fetchone.return_value = ("Speedcore",)
        result = self.helper.get_corrected_or_exists("speedcore")
        self.assertEqual(result, "Speedcore")

    def test_get_corrected_or_exists_only_exists(self):
        self.mock_cursor.fetchone.return_value = ("",)
        result = self.helper.get_corrected_or_exists("rave")
        self.assertEqual(result, "rave")

    def test_get_corrected_or_exists_not_found(self):
        self.mock_cursor.fetchone.return_value = None
        result = self.helper.get_corrected_or_exists("jazz")
        self.assertFalse(result)

    def test_add_with_correction_success(self):
        self.assertTrue(self.helper.add("Hard Tek", "Hardtek"))
        self.mock_connection.commit.assert_called_once()

    def test_add_with_correction_failure(self):
        self.mock_cursor.execute.side_effect = Exception("Insert error")
        result = self.helper.add("Terror", "Terrorcore")
        self.assertFalse(result)
        self.mock_connection.rollback.assert_called_once()

    def test_get_all(self):
        self.mock_cursor.fetchall.return_value = [("Hardcore",), ("Terror",), ("Speedcore",)]
        result = self.helper.get_all()
        self.assertEqual(result, ["Hardcore", "Speedcore", "Terror"])


unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(FilterTableHelperTest))
