import unittest
from unittest.mock import MagicMock, patch

from services.common.Helpers.FilterTableHelper import FilterTableHelper


class FilterTableHelperTest(unittest.TestCase):

    def setUp(self):
        patcher = patch('services.common.Helpers.FilterTableHelper.DatabaseConnector')
        self.addCleanup(patcher.stop)
        self.mock_connector_cls = patcher.start()
        self.mock_connection = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_connection.cursor.return_value.__enter__.return_value = self.mock_cursor
        self.mock_connector_cls.return_value.connect.return_value = self.mock_connection
        self.helper = FilterTableHelper('rules_genres', 'name', 'corrected_genre', preload=False)

    def test_exists_true(self):
        self.mock_cursor.fetchone.return_value = (1,)
        self.assertTrue(self.helper.exists('Hardcore'))
        self.mock_cursor.execute.assert_called_once()

    def test_exists_false(self):
        self.mock_cursor.fetchone.return_value = None
        self.assertFalse(self.helper.exists('UnknownGenre'))

    def test_get_corrected_found(self):
        self.mock_cursor.fetchone.return_value = ('Uptempo Hardcore',)
        result = self.helper.get_corrected('uptempo hardcore')
        self.assertEqual(result, 'Uptempo Hardcore')

    def test_get_corrected_not_found(self):
        self.mock_cursor.fetchone.return_value = None
        result = self.helper.get_corrected('ambient')
        self.assertEqual(result, '')

    def test_get_corrected_or_exists_corrected(self):
        self.mock_cursor.fetchone.return_value = ('speedcore', 'Speedcore')
        result = self.helper.get_corrected_or_exists('speedcore')
        self.assertEqual(result, 'Speedcore')

    def test_get_corrected_or_exists_only_exists(self):
        self.mock_cursor.fetchone.return_value = ('rave', '')
        result = self.helper.get_corrected_or_exists('rave')
        self.assertEqual(result, 'rave')

    def test_get_corrected_or_exists_returns_the_stored_spelling(self):
        self.mock_cursor.fetchone.return_value = ('uptempo', '')
        result = self.helper.get_corrected_or_exists('UPTEMPO')
        self.assertEqual(result, 'uptempo')

    def test_get_corrected_or_exists_asks_the_database_case_insensitively(self):
        self.mock_cursor.fetchone.return_value = ('uptempo', '')
        self.helper.get_corrected_or_exists('Uptempo')
        query = self.mock_cursor.execute.call_args[0][0]
        self.assertIn('LOWER(name) = LOWER(%s)', query)

    def test_get_corrected_or_exists_not_found(self):
        self.mock_cursor.fetchone.return_value = None
        result = self.helper.get_corrected_or_exists('jazz')
        self.assertFalse(result)

    def test_add_with_correction_success(self):
        self.assertTrue(self.helper.add('Hard Tek', 'Hardtek'))
        self.mock_connection.commit.assert_called_once()

    def test_add_with_correction_failure(self):
        self.mock_cursor.execute.side_effect = Exception('Insert error')
        result = self.helper.add('Terror', 'Terrorcore')
        self.assertFalse(result)
        self.mock_connection.rollback.assert_called_once()

    def test_get_all(self):
        self.mock_cursor.fetchall.return_value = [('Hardcore',), ('Terror',), ('Speedcore',)]
        result = self.helper.get_all()
        self.assertEqual(result, ['Hardcore', 'Speedcore', 'Terror'])


    def test_update_writes_the_correction_for_an_existing_name(self):
        helper = FilterTableHelper('rules_ignored_artists', 'name', 'corrected_name', preload=False)
        self.assertTrue(helper.update('Ran D', 'Ran-D'))
        query = self.mock_cursor.execute.call_args.args[0]
        self.assertIn('UPDATE rules_ignored_artists', query)
        self.assertEqual(self.mock_cursor.execute.call_args.args[1], ('Ran-D', 'Ran D'))

    def test_update_can_clear_the_correction(self):
        helper = FilterTableHelper('rules_ignored_artists', 'name', 'corrected_name', preload=False)
        helper.update('Ran D', None)
        self.assertEqual(self.mock_cursor.execute.call_args.args[1], (None, 'Ran D'))

    def test_delete_removes_the_row(self):
        helper = FilterTableHelper('rules_ignored_artists', 'name', 'corrected_name', preload=False)
        self.assertTrue(helper.delete('Ran D'))
        query = self.mock_cursor.execute.call_args.args[0]
        self.assertIn('DELETE FROM rules_ignored_artists', query)

    def test_a_failing_delete_reports_false(self):
        helper = FilterTableHelper('rules_ignored_artists', 'name', 'corrected_name', preload=False)
        self.mock_cursor.execute.side_effect = RuntimeError('database gone')
        self.assertFalse(helper.delete('Ran D'))

    def test_reload_replaces_the_cached_values(self):
        helper = FilterTableHelper('rules_ignored_artists', 'name', 'corrected_name', preload=False)
        helper.cache_enabled = True
        helper._canonical_map = {'old': 'Old'}
        helper._corrected_map = {'old': 'Older'}
        self.mock_cursor.fetchall.return_value = [('Typo Name', 'Correct Name')]
        helper.reload()
        self.assertEqual(helper.get_corrected('Typo Name'), 'Correct Name')
        self.assertEqual(helper.get_corrected('old'), '')

    def test_reload_does_nothing_when_the_helper_is_not_cached(self):
        self.helper.reload()
        self.mock_cursor.execute.assert_not_called()

class FilterTableHelperCachedTest(unittest.TestCase):
    """The preloaded path, which is the one every long-running service uses.

    SoundCloud hands out genres in whatever casing the uploader typed, so a
    lookup that only matches the stored spelling silently throws away genres
    that are in `rules_genres` under a different casing.
    """

    def setUp(self):
        patcher = patch('services.common.Helpers.FilterTableHelper.DatabaseConnector')
        self.addCleanup(patcher.stop)
        self.mock_connector_cls = patcher.start()
        self.mock_connection = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_connection.cursor.return_value.__enter__.return_value = self.mock_cursor
        self.mock_connector_cls.return_value.connect.return_value = self.mock_connection
        self.mock_cursor.fetchall.return_value = [
            ('uptempo', None),
            ('Hardcore', ''),
            ('uptempo hardcore', 'Uptempo Hardcore'),
        ]
        self.helper = FilterTableHelper('rules_genres', 'name', 'corrected_genre')

    def test_exists_ignores_case(self):
        self.assertTrue(self.helper.exists('HARDCORE'))

    def test_get_corrected_or_exists_ignores_case(self):
        self.assertEqual(self.helper.get_corrected_or_exists('Uptempo'), 'uptempo')

    def test_get_corrected_or_exists_returns_the_stored_spelling(self):
        self.assertEqual(self.helper.get_corrected_or_exists('hardcore'), 'Hardcore')

    def test_get_corrected_or_exists_prefers_the_correction(self):
        self.assertEqual(self.helper.get_corrected_or_exists('UPTEMPO HARDCORE'), 'Uptempo Hardcore')

    def test_get_corrected_ignores_case(self):
        self.assertEqual(self.helper.get_corrected('Uptempo Hardcore'), 'Uptempo Hardcore')

    def test_unknown_genre_is_still_rejected(self):
        self.assertFalse(self.helper.get_corrected_or_exists('jazz'))
unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(FilterTableHelperTest))