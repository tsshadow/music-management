import unittest
from unittest.mock import MagicMock, patch

from services.common.Helpers.BrokenSongHelper import BrokenSongHelper


class BrokenSongHelperTest(unittest.TestCase):
    def setUp(self):
        patcher = patch('services.common.Helpers.BrokenSongHelper.DatabaseConnector')
        self.addCleanup(patcher.stop)
        self.mock_connector_cls = patcher.start()
        self.mock_connection = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_connection.cursor.return_value.__enter__.return_value = self.mock_cursor
        self.mock_connector_cls.return_value.connect.return_value = self.mock_connection
        self.helper = BrokenSongHelper()

    def test_add_inserts_path_and_error_code(self):
        self.helper.add('/music/broken.m4a', 'MP4StreamInfoError')

        query, params = self.mock_cursor.execute.call_args[0]
        self.assertIn('INSERT INTO library_broken_songs', query)
        self.assertEqual(params, ('/music/broken.m4a', 'MP4StreamInfoError'))
        self.mock_connection.commit.assert_called_once()
        self.mock_connection.close.assert_called_once()

    def test_add_uses_the_configured_table_name(self):
        helper = BrokenSongHelper('other_broken_table')

        helper.add('/music/broken.m4a', 'Boom')

        self.assertIn('INSERT INTO other_broken_table', self.mock_cursor.execute.call_args[0][0])

    def test_add_swallows_database_errors_but_still_closes(self):
        self.mock_cursor.execute.side_effect = Exception('DB Error')

        self.helper.add('/music/broken.m4a', 'Boom')

        self.mock_connection.commit.assert_not_called()
        self.mock_connection.close.assert_called_once()

    def test_remove_deletes_by_id(self):
        self.helper.remove(42)

        query, params = self.mock_cursor.execute.call_args[0]
        self.assertEqual(query, 'DELETE FROM library_broken_songs WHERE id = %s')
        self.assertEqual(params, (42,))
        self.mock_connection.commit.assert_called_once()
        self.mock_connection.close.assert_called_once()

    def test_remove_swallows_database_errors_but_still_closes(self):
        self.mock_cursor.execute.side_effect = Exception('DB Error')

        self.helper.remove(42)

        self.mock_connection.commit.assert_not_called()
        self.mock_connection.close.assert_called_once()

    def test_get_all_returns_the_rows(self):
        self.mock_cursor.fetchall.return_value = [(1, '/music/a.m4a', 'MP4StreamInfoError')]

        result = self.helper.get_all()

        self.assertEqual(result, [(1, '/music/a.m4a', 'MP4StreamInfoError')])
        self.mock_cursor.execute.assert_called_once_with('SELECT id, path, error_code FROM library_broken_songs')
        self.mock_connection.close.assert_called_once()

    def test_get_all_returns_empty_list_on_error(self):
        self.mock_cursor.execute.side_effect = Exception('DB Error')

        self.assertEqual(self.helper.get_all(), [])
        self.mock_connection.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
