"""database.transaction: commit on success, rollback on failure, the original error re-raised.

Loaded as a fresh module copy, like test_database_pool, because several other test modules
replace attributes of the shared database module at import time.
"""

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import HTTPException

_SPEC = importlib.util.spec_from_file_location(
    'database_transaction_under_test', Path(__file__).resolve().parent.parent / 'database.py'
)
assert _SPEC is not None and _SPEC.loader is not None
database = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(database)


def a_connection():
    """A connection whose begin/commit/rollback calls, and its cursor's statements, land in one list."""
    conn = MagicMock()
    conn.calls = []
    conn.begin.side_effect = lambda: conn.calls.append('begin')
    conn.commit.side_effect = lambda: conn.calls.append('commit')
    conn.rollback.side_effect = lambda: conn.calls.append('rollback')
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.execute.side_effect = lambda sql, *_args: conn.calls.append(sql)
    return conn


class TransactionTest(unittest.TestCase):
    def test_begins_before_the_writes_and_commits_after_them(self):
        conn = a_connection()
        with database.transaction(conn), conn.cursor() as cursor:
            cursor.execute('DELETE FROM t')
            cursor.execute('INSERT INTO t VALUES (1)')
        self.assertEqual(conn.calls, ['begin', 'DELETE FROM t', 'INSERT INTO t VALUES (1)', 'commit'])

    def test_yields_the_connection(self):
        conn = a_connection()
        with database.transaction(conn) as inside:
            self.assertIs(inside, conn)

    def test_a_failure_rolls_back_and_re_raises_the_original_error(self):
        conn = a_connection()
        error = RuntimeError('lock wait timeout')
        with self.assertRaises(RuntimeError) as raised, database.transaction(conn), conn.cursor() as cursor:
            cursor.execute('DELETE FROM t')
            raise error
        self.assertIs(raised.exception, error)
        self.assertEqual(conn.calls, ['begin', 'DELETE FROM t', 'rollback'])

    def test_an_http_error_inside_the_block_rolls_back_too(self):
        # A router raising 404 half-way must not leave the half it already wrote.
        conn = a_connection()
        with self.assertRaises(HTTPException), database.transaction(conn):
            raise HTTPException(status_code=404)
        self.assertEqual(conn.calls, ['begin', 'rollback'])

    def test_a_failing_rollback_does_not_hide_the_original_error(self):
        conn = a_connection()
        conn.rollback.side_effect = ConnectionError('server has gone away')
        with self.assertRaises(RuntimeError), self.assertLogs('music-manager.database', 'WARNING') as logs:
            with database.transaction(conn):
                raise RuntimeError('deadlock')
        self.assertIn('server has gone away', logs.output[0])

    def test_a_failing_begin_writes_nothing_and_commits_nothing(self):
        conn = a_connection()
        conn.begin.side_effect = ConnectionError('server has gone away')
        body = MagicMock()
        with self.assertRaises(ConnectionError), database.transaction(conn):
            body()
        body.assert_not_called()
        conn.commit.assert_not_called()

    def test_a_failing_commit_propagates(self):
        conn = a_connection()
        conn.commit.side_effect = ConnectionError('server has gone away')
        with self.assertRaises(ConnectionError), database.transaction(conn):
            pass
        conn.rollback.assert_not_called()


if __name__ == '__main__':
    unittest.main()
