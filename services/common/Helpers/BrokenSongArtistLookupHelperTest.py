import unittest
from unittest.mock import MagicMock, patch

from services.common.Helpers.BrokenSongArtistLookupHelper import BrokenSongArtistLookupHelper


class BrokenSongArtistLookupHelperTest(unittest.TestCase):

    def setUp(self):
        patcher = patch('services.common.Helpers.BrokenSongArtistLookupHelper.DatabaseConnector')
        self.addCleanup(patcher.stop)
        self.mock_connector_cls = patcher.start()
        self.mock_connection = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_connection.cursor.return_value.__enter__.return_value = self.mock_cursor
        self.mock_connector_cls.return_value.connect.return_value = self.mock_connection
        self.helper = BrokenSongArtistLookupHelper()

    def test_returns_the_stored_normalized_name(self):
        self.mock_cursor.fetchone.return_value = ('evil-activities',)

        self.assertEqual(self.helper.get_normalized_name('Evil Activities'), 'evil-activities')
        self.mock_connection.close.assert_called_once()

    def test_falls_back_to_a_slug_when_the_name_is_unknown(self):
        self.mock_cursor.fetchone.return_value = None

        self.assertEqual(self.helper.get_normalized_name('  Angerfist Live  '), 'angerfist-live')

    def test_falls_back_to_a_slug_on_a_database_error(self):
        self.mock_cursor.execute.side_effect = Exception('DB Error')

        self.assertEqual(self.helper.get_normalized_name('Evil Activities'), 'evil-activities')
        self.mock_connection.close.assert_called_once()

    def test_lookup_is_case_insensitive_on_the_raw_name(self):
        self.mock_cursor.fetchone.return_value = ('evil-activities',)

        self.helper.get_normalized_name('EVIL ACTIVITIES')

        query, params = self.mock_cursor.execute.call_args[0]
        self.assertIn('LOWER(raw_name) = LOWER(%s)', query)
        self.assertEqual(params, ('EVIL ACTIVITIES',))

    def test_insert_if_missing_inserts_when_the_name_is_new(self):
        self.mock_cursor.fetchone.return_value = None

        self.helper.insert_if_missing('Evil Activities', 'evil-activities')

        insert_query, params = self.mock_cursor.execute.call_args_list[1][0]
        self.assertIn('INSERT INTO library_broken_song_artist_lookup', insert_query)
        self.assertEqual(params, ('Evil Activities', 'evil-activities'))
        self.mock_connection.commit.assert_called_once()
        self.mock_connection.close.assert_called_once()

    def test_insert_if_missing_defaults_the_normalized_name_to_empty(self):
        self.mock_cursor.fetchone.return_value = None

        self.helper.insert_if_missing('Evil Activities')

        self.assertEqual(self.mock_cursor.execute.call_args_list[1][0][1], ('Evil Activities', ''))

    def test_insert_if_missing_skips_an_existing_name(self):
        self.mock_cursor.fetchone.return_value = (1,)

        self.helper.insert_if_missing('Evil Activities', 'evil-activities')

        self.assertEqual(self.mock_cursor.execute.call_count, 1)
        self.mock_connection.commit.assert_not_called()
        self.mock_connection.close.assert_called_once()

    def test_insert_if_missing_swallows_database_errors(self):
        self.mock_cursor.execute.side_effect = Exception('DB Error')

        self.helper.insert_if_missing('Evil Activities')

        self.mock_connection.commit.assert_not_called()
        self.mock_connection.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
