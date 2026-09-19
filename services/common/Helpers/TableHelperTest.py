import unittest
from unittest.mock import MagicMock, patch

from services.common.Helpers.TableHelper import TableHelper


class TableHelperTest(unittest.TestCase):
    def setUp(self):
        patcher = patch('services.common.Helpers.TableHelper.DatabaseConnector')
        self.addCleanup(patcher.stop)
        self.mock_connector_cls = patcher.start()
        self.mock_connection = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_connection.cursor.return_value.__enter__.return_value = self.mock_cursor
        self.mock_connector_cls.return_value.connect.return_value = self.mock_connection
        self.helper = TableHelper('rules_genres', 'name', preload=False)

    def test_exists_found(self):
        self.mock_cursor.fetchone.return_value = (1,)
        self.assertTrue(self.helper.exists('Hardcore'))
        self.mock_cursor.execute.assert_called_once()

    def test_exists_not_found(self):
        self.mock_cursor.fetchone.return_value = None
        self.assertFalse(self.helper.exists('Nonexistent'))

    def test_get_hit(self):
        self.mock_cursor.fetchone.return_value = ('Hardcore',)
        result = self.helper.get('hardcore')
        self.assertEqual(result, 'Hardcore')

    def test_get_miss(self):
        self.mock_cursor.fetchone.return_value = None
        result = self.helper.get('unknown')
        self.assertEqual(result, 'Unknown')

    def test_add_success(self):
        self.assertTrue(self.helper.add('Frenchcore'))
        self.mock_cursor.execute.assert_called_once()
        self.mock_connection.commit.assert_called_once()

    def test_add_failure(self):
        self.mock_cursor.execute.side_effect = Exception('Insert error')
        result = self.helper.add('BadInput')
        self.assertFalse(result)
        self.mock_connection.rollback.assert_called_once()

    def test_get_all_values(self):
        self.mock_cursor.fetchall.return_value = [('Hardcore',), ('Uptempo',)]
        values = self.helper.get_all_values()
        self.assertEqual(values, ['Hardcore', 'Uptempo'])

    def test_reload_replaces_the_cached_values(self):
        helper = TableHelper('library_artists', 'name', preload=False)
        helper.cache_enabled = True
        helper._values = {'Old Artist'}
        helper._canonical_map = {'old artist': 'Old Artist'}
        self.mock_cursor.fetchall.return_value = [('New Artist',)]
        helper.reload()
        self.assertTrue(helper.exists('New Artist'))
        self.assertFalse(helper.exists('Old Artist'))

    def test_reload_does_nothing_when_the_helper_is_not_cached(self):
        self.helper.reload()
        self.mock_cursor.execute.assert_not_called()


class CachedTableHelperTest(unittest.TestCase):
    """With preload on, every read is the in-memory snapshot; see the class docstring."""

    def setUp(self):
        patcher = patch('services.common.Helpers.TableHelper.DatabaseConnector')
        self.addCleanup(patcher.stop)
        connector_cls = patcher.start()
        self.connection = MagicMock()
        self.cursor = MagicMock()
        self.connection.cursor.return_value.__enter__.return_value = self.cursor
        connector_cls.return_value.connect.return_value = self.connection
        self.cursor.fetchall.return_value = [('Angerfist',), ('Miss K8',)]
        self.helper = TableHelper('library_artists', 'name')
        self.cursor.execute.reset_mock()

    def test_get_all_values_is_served_from_the_cache(self):
        # This used to be a full read of library_artists, three times per tagged file.
        self.assertEqual(sorted(self.helper.get_all_values()), ['Angerfist', 'Miss K8'])
        self.assertEqual(self.helper.lowercase_map(), {'angerfist': 'Angerfist', 'miss k8': 'Miss K8'})
        self.assertTrue(self.helper.exists('miss k8'))
        self.cursor.execute.assert_not_called()

    def test_the_table_is_re_read_once_it_is_stale(self):
        self.cursor.fetchall.return_value = [('Angerfist',), ('Miss K8',), ('Dr. Peacock',)]
        self.helper._loaded_at -= TableHelper.STALE_AFTER_SECONDS + 1
        self.assertTrue(self.helper.exists('Dr. Peacock'))
        self.cursor.execute.assert_called_once()

    def test_a_failed_refresh_keeps_the_old_snapshot_and_does_not_retry_at_once(self):
        self.connection.cursor.side_effect = RuntimeError('db down')
        self.helper._loaded_at -= TableHelper.STALE_AFTER_SECONDS + 1
        with self.assertLogs(level='ERROR'):
            self.assertTrue(self.helper.exists('Angerfist'))
        self.connection.cursor.reset_mock()
        self.assertTrue(self.helper.exists('Angerfist'))
        self.connection.cursor.assert_not_called()

    def test_a_snapshot_handed_out_is_never_mutated_afterwards(self):
        before = self.helper.lowercase_map()
        self.helper.add('Partyraiser')
        self.assertNotIn('partyraiser', before)
        self.assertIn('partyraiser', self.helper.lowercase_map())

    def test_a_failed_insert_does_not_reach_the_cache(self):
        self.connection.commit.side_effect = RuntimeError('deadlock')
        with self.assertLogs(level='ERROR'):
            self.assertFalse(self.helper.add('Partyraiser'))
        self.assertFalse(self.helper.exists('Partyraiser'))

    def test_delete_drops_the_value_from_both_indexes(self):
        self.assertTrue(self.helper.delete('angerfist'))
        self.assertFalse(self.helper.exists('Angerfist'))
        self.assertNotIn('Angerfist', self.helper.get_all_values())


if __name__ == '__main__':
    unittest.main()
