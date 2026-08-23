import unittest
from unittest.mock import MagicMock, patch

from services.common.Helpers.LookupTableHelper import LookupTableHelper


class LookupTableHelperTest(unittest.TestCase):

    def setUp(self):
        patcher = patch('services.common.Helpers.LookupTableHelper.DatabaseConnector')
        self.addCleanup(patcher.stop)
        self.mock_connector_cls = patcher.start()
        self.mock_connection = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_connection.cursor.return_value.__enter__.return_value = self.mock_cursor
        self.mock_connector_cls.return_value.connect.return_value = self.mock_connection
        self.helper = LookupTableHelper('rules_artist_genre', 'artist', 'genre', preload=False)

    def test_get_success(self):
        self.mock_cursor.fetchall.return_value = [('Hardcore',), ('Terror',)]
        result = self.helper.get('Evil Activities')
        self.assertEqual(result, ['Hardcore', 'Terror'])
        self.mock_cursor.execute.assert_called_once_with('SELECT genre FROM rules_artist_genre WHERE LOWER(artist) = LOWER(%s)', ('Evil Activities',))

    def test_get_empty(self):
        self.mock_cursor.fetchall.return_value = []
        result = self.helper.get('Unknown Artist')
        self.assertEqual(result, [])
        self.mock_connection.close.assert_called_once()

    def test_get_exception(self):
        self.mock_cursor.execute.side_effect = Exception('DB Error')
        result = self.helper.get('Evil Activities')
        self.assertEqual(result, [])
        self.mock_connection.close.assert_called_once()

    def test_get_substring_success(self):
        self.mock_cursor.fetchall.return_value = [('Hardcore', 'NL'), ('Hard Bass', 'NL'), ('Speedcore', 'DE'), ('House', 'FR')]
        result = self.helper.get_substring('The rise of hardcore and speedcore music')
        expected = ['DE', 'NL']
        self.assertEqual(result, expected)
        self.mock_connection.close.assert_called_once()

    def test_get_substring_exception(self):
        self.mock_cursor.execute.side_effect = Exception('DB Fail')
        result = self.helper.get_substring('any text')
        self.assertEqual(result, [])
        self.mock_connection.close.assert_called_once()
class LookupTableHelperReloadTest(unittest.TestCase):
    """A preloaded helper has to notice rules written after it was built.

    `databaseHelpers` (Cache.py) constructs every helper once at import and each one
    reads its whole table into memory there and then. Without these two escapes a rule
    added through the API is invisible until the process restarts.
    """

    def setUp(self):
        patcher = patch('services.common.Helpers.LookupTableHelper.DatabaseConnector')
        self.addCleanup(patcher.stop)
        self.mock_connector_cls = patcher.start()
        self.mock_connection = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_connection.cursor.return_value.__enter__.return_value = self.mock_cursor
        self.mock_connector_cls.return_value.connect.return_value = self.mock_connection
        self.rows = [('Angerfist', 'Hardcore')]
        self.mock_cursor.fetchall.side_effect = lambda: list(self.rows)

        clock = patch('services.common.Helpers.LookupTableHelper.time.monotonic')
        self.addCleanup(clock.stop)
        self.now = 1000.0
        clock.start().side_effect = lambda: self.now

    def _helper(self):
        return LookupTableHelper('rules_artist_genre', 'artist', 'genre')

    def test_preloaded_helper_misses_a_row_added_after_construction(self):
        helper = self._helper()
        self.rows.append(('Radical Redemption', 'Hardstyle'))
        self.assertEqual(helper.get('Radical Redemption'), [])

    def test_reload_picks_up_a_row_added_after_construction(self):
        helper = self._helper()
        self.rows.append(('Radical Redemption', 'Hardstyle'))
        helper.reload()
        self.assertEqual(helper.get('Radical Redemption'), ['Hardstyle'])

    def test_get_refreshes_itself_once_the_cache_is_stale(self):
        helper = self._helper()
        self.rows.append(('Radical Redemption', 'Hardstyle'))
        self.now += LookupTableHelper.STALE_AFTER_SECONDS + 1
        self.assertEqual(helper.get('Radical Redemption'), ['Hardstyle'])

    def test_get_does_not_query_again_while_the_cache_is_fresh(self):
        helper = self._helper()
        calls_after_preload = self.mock_cursor.execute.call_count
        self.now += LookupTableHelper.STALE_AFTER_SECONDS - 1
        helper.get('Angerfist')
        self.assertEqual(self.mock_cursor.execute.call_count, calls_after_preload)

    def test_an_uncached_helper_never_reloads(self):
        helper = LookupTableHelper('rules_artist_genre', 'artist', 'genre', preload=False)
        self.now += LookupTableHelper.STALE_AFTER_SECONDS + 1
        self.mock_cursor.fetchall.side_effect = lambda: [('Hardstyle',)]
        self.assertEqual(helper.get('Radical Redemption'), ['Hardstyle'])


unittest.TextTestRunner().run(unittest.TestLoader().loadTestsFromTestCase(LookupTableHelperTest))