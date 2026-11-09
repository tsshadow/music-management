"""Tests for services/common/db_init.py: a failed create pass is an ERROR and is remembered."""

import unittest
from unittest import mock

from services.common import db_init


def _connector_with(cursor):
    """A DatabaseConnector stand-in whose connection hands out `cursor`."""
    conn = mock.MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    connector = mock.MagicMock()
    connector.return_value.connect.return_value = conn
    return connector, conn


class EnsureTablesExistTest(unittest.TestCase):
    """ensure_tables_exist() keeps start-up going, but says when it failed."""

    def setUp(self):
        patcher = mock.patch.object(db_init, '_status', 'unknown')
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_create_that_raises_is_logged_at_error_and_reported_as_failed(self):
        cursor = mock.MagicMock()
        cursor.execute.side_effect = [None, RuntimeError('table full')]
        connector, conn = _connector_with(cursor)

        with (
            mock.patch.object(db_init, 'DatabaseConnector', connector),
            self.assertLogs(level='ERROR') as logs,
        ):
            self.assertFalse(db_init.ensure_tables_exist())

        self.assertIn('table full', logs.output[0])
        self.assertEqual(db_init.schema_status(), 'failed')
        self.assertEqual(cursor.execute.call_count, 2)
        conn.commit.assert_not_called()
        conn.close.assert_called_once()

    def test_a_clean_pass_is_reported_as_ok(self):
        connector, conn = _connector_with(mock.MagicMock())

        with (
            mock.patch.object(db_init, 'DatabaseConnector', connector),
            mock.patch.object(db_init.db_seeds, 'seed'),
        ):
            self.assertTrue(db_init.ensure_tables_exist())

        self.assertEqual(db_init.schema_status(), 'ok')
        conn.commit.assert_called_once()

    def test_a_connection_that_fails_counts_as_a_failed_pass(self):
        connector = mock.MagicMock()
        connector.return_value.connect.side_effect = ConnectionError('no route')

        with mock.patch.object(db_init, 'DatabaseConnector', connector), self.assertLogs(level='ERROR'):
            self.assertFalse(db_init.ensure_tables_exist())

        self.assertEqual(db_init.schema_status(), 'failed')

    def test_before_any_pass_the_status_is_unknown(self):
        self.assertEqual(db_init.schema_status(), 'unknown')


if __name__ == '__main__':
    unittest.main()
