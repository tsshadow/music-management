import unittest
from unittest.mock import MagicMock, patch
from postprocessing.Song.Helpers.TableHelper import TableHelper

class TableHelperTest(unittest.TestCase):
    def setUp(self):
        patcher = patch("postprocessing.Song.Helpers.TableHelper.DatabaseConnector")
        self.addCleanup(patcher.stop)
        self.mock_connector_cls = patcher.start()

        self.mock_connection = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_connection.cursor.return_value.__enter__.return_value = self.mock_cursor
        self.mock_connector_cls.return_value.connect.return_value = self.mock_connection

        self.helper = TableHelper("genres", "name", preload=False)

    def test_exists_found(self):
        self.mock_cursor.fetchone.return_value = (1,)
        self.assertTrue(self.helper.exists("Hardcore"))
        self.mock_cursor.execute.assert_called_once()

    def test_exists_not_found(self):
        self.mock_cursor.fetchone.return_value = None
        self.assertFalse(self.helper.exists("Nonexistent"))

    def test_get_hit(self):
        self.mock_cursor.fetchone.return_value = ("Hardcore",)
        result = self.helper.get("hardcore")
        self.assertEqual(result, "Hardcore")

    def test_get_miss(self):
        self.mock_cursor.fetchone.return_value = None
        result = self.helper.get("unknown")
        self.assertEqual(result, "Unknown")

    def test_add_success(self):
        self.assertTrue(self.helper.add("Frenchcore"))
        self.mock_cursor.execute.assert_called_once()
        self.mock_connection.commit.assert_called_once()

    def test_add_failure(self):
        self.mock_cursor.execute.side_effect = Exception("Insert error")
        result = self.helper.add("BadInput")
        self.assertFalse(result)
        self.mock_connection.rollback.assert_called_once()

    def test_get_all_values(self):
        self.mock_cursor.fetchall.return_value = [("Hardcore",), ("Uptempo",)]
        values = self.helper.get_all_values()
        self.assertEqual(values, ["Hardcore", "Uptempo"])

if __name__ == "__main__":
    unittest.main()
