"""get_db_connection: an exhausted pool waits a bounded time and then says so, and the API answers 503.

Loaded as a fresh module copy, because several other test modules replace
database.get_db_connection with a MagicMock at import time.
"""

import importlib.util
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('mutagen', 'markdown', 'pymysql', 'dbutils', 'DatabaseConnector')


_SPEC = importlib.util.spec_from_file_location(
    'database_under_test', Path(__file__).resolve().parent.parent / 'database.py'
)
database = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(database)


class ExhaustedPool:
    """A pool that is out of connections for its first `busy_for` calls."""

    def __init__(self, busy_for: int):
        self.busy_for = busy_for
        self.calls = 0

    def connection(self):
        self.calls += 1
        if self.calls <= self.busy_for:
            raise database._PoolExhausted()
        return 'connection'


class GetDbConnectionTest(unittest.TestCase):
    def setUp(self):
        self.original_pool = database._pool
        self.addCleanup(setattr, database, '_pool', self.original_pool)

    def test_waits_for_a_connection_to_come_free(self):
        database._pool = ExhaustedPool(busy_for=3)
        self.assertEqual(database.get_db_connection(wait_seconds=2), 'connection')
        self.assertEqual(database._pool.calls, 4)

    def test_gives_up_with_a_clear_error_after_the_wait(self):
        database._pool = ExhaustedPool(busy_for=10**9)
        started = time.monotonic()
        with self.assertRaises(database.DatabaseBusyError):
            database.get_db_connection(wait_seconds=0.2)
        self.assertLess(time.monotonic() - started, 1.5)

    def test_other_connect_errors_are_not_retried(self):
        pool = MagicMock()
        pool.connection.side_effect = ConnectionRefusedError('2003')
        database._pool = pool
        with self.assertRaises(ConnectionRefusedError):
            database.get_db_connection(wait_seconds=5)
        self.assertEqual(pool.connection.call_count, 1)

    def test_the_pool_no_longer_blocks_without_a_timeout(self):
        with patch.object(database, 'PooledDB') as pooled:
            database._pool = None
            database.get_db_pool()
        self.assertIs(pooled.call_args.kwargs['blocking'], False)


class CheckDatabaseTest(unittest.TestCase):
    def test_false_when_connect_fails(self):
        with patch.object(database.pymysql, 'connect', side_effect=OSError('refused')):
            self.assertFalse(database.check_database())

    def test_true_when_select_1_answers(self):
        conn = MagicMock()
        with patch.object(database.pymysql, 'connect', return_value=conn):
            self.assertTrue(database.check_database())
        conn.close.assert_called_once()


class DatabaseBusyResponseTest(unittest.TestCase):
    """The API turns DatabaseBusyError into a 503 rather than a 500 or a hung request."""

    def test_busy_pool_answers_503(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from services.music_manager import main
        from services.music_manager.database import DatabaseBusyError

        app = FastAPI()
        app.add_exception_handler(DatabaseBusyError, main.database_busy_handler)

        @app.get('/busy')
        def busy():
            raise DatabaseBusyError('No free database connection: the pool is exhausted')

        response = TestClient(app).get('/busy')
        self.assertEqual(response.status_code, 503)
        self.assertIn('pool is exhausted', response.json()['detail'])
        self.assertEqual(response.headers['Retry-After'], '5')

    def test_main_registers_the_handler(self):
        from services.music_manager import main
        from services.music_manager.database import DatabaseBusyError

        self.assertIn(DatabaseBusyError, main.app.exception_handlers)


if __name__ == '__main__':
    unittest.main()
