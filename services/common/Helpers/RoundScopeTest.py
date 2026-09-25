"""RoundScope: one connection per thread for a tagging round, and values built once per round."""

import importlib.util
import os
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.common.Helpers import RoundScope


class CountingOpener:
    """A connection factory that records every connection it opened, and on which thread."""

    def __init__(self):
        self.opened = []
        self.threads = []
        self._lock = threading.Lock()

    def __call__(self):
        connection = MagicMock(name=f'connection-{len(self.opened)}')
        with self._lock:
            self.opened.append(connection)
            self.threads.append(threading.get_ident())
        return connection


def use_like_a_helper(opener):
    """What every helper does per call: connect, run a query, close."""
    connection = RoundScope.connect(opener)
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    finally:
        connection.close()


class OutsideARoundTest(unittest.TestCase):
    def test_every_connect_opens_a_new_connection_and_close_closes_it(self):
        opener = CountingOpener()
        for _ in range(3):
            use_like_a_helper(opener)
        self.assertEqual(len(opener.opened), 3)
        for connection in opener.opened:
            connection.close.assert_called_once()
            connection.rollback.assert_not_called()

    def test_after_the_round_every_connect_is_fresh_again(self):
        opener = CountingOpener()
        with RoundScope.round_scope():
            use_like_a_helper(opener)
        self.assertIsNone(RoundScope.current())
        use_like_a_helper(opener)
        self.assertEqual(len(opener.opened), 2)


class InsideARoundTest(unittest.TestCase):
    def test_n_helper_calls_share_one_connection(self):
        opener = CountingOpener()
        with RoundScope.round_scope() as scope:
            for _ in range(25):
                use_like_a_helper(opener)
        self.assertEqual(len(opener.opened), 1)
        self.assertEqual(scope.opened, 1)
        self.assertEqual(scope.borrowed, 25)

    def test_close_ends_the_transaction_and_the_round_closes_the_socket(self):
        """A helper's close() used to throw away anything uncommitted along with the socket.
        Inside a round it must still end the transaction, or the next helper would read a
        stale REPEATABLE READ snapshot."""
        opener = CountingOpener()
        with RoundScope.round_scope():
            use_like_a_helper(opener)
            use_like_a_helper(opener)
            connection = opener.opened[0]
            self.assertEqual(connection.rollback.call_count, 2)
            connection.close.assert_not_called()
        connection.close.assert_called_once()

    def test_a_second_close_from_the_same_borrower_does_nothing(self):
        opener = CountingOpener()
        with RoundScope.round_scope():
            connection = RoundScope.connect(opener)
            connection.close()
            connection.close()
            self.assertEqual(opener.opened[0].rollback.call_count, 1)

    def test_the_connection_works_as_its_own_context_manager(self):
        opener = CountingOpener()
        with RoundScope.round_scope():
            with RoundScope.connect(opener) as connection:
                connection.commit()
            opener.opened[0].commit.assert_called_once()
            opener.opened[0].rollback.assert_called_once()

    def test_a_nested_connect_gets_its_own_connection(self):
        """One helper calling another while its connection is open: the inner close must
        not roll back the outer caller's work, so the inner one gets a real connection."""
        opener = CountingOpener()
        with RoundScope.round_scope() as scope:
            outer = RoundScope.connect(opener)
            inner = RoundScope.connect(opener)
            inner.close()
            opener.opened[0].rollback.assert_not_called()
            opener.opened[1].close.assert_called_once()
            outer.close()
            self.assertEqual(scope.opened, 2)
            # The outer connection is available again for the next helper.
            use_like_a_helper(opener)
        self.assertEqual(len(opener.opened), 2)

    def test_a_connection_whose_rollback_fails_is_replaced(self):
        opener = CountingOpener()
        with RoundScope.round_scope() as scope:
            use_like_a_helper(opener)
            opener.opened[0].rollback.side_effect = RuntimeError('gone away')
            use_like_a_helper(opener)
            use_like_a_helper(opener)
        self.assertEqual(len(opener.opened), 2)
        self.assertEqual(scope.opened, 2)
        opener.opened[0].close.assert_called()

    def test_an_idle_connection_that_no_longer_answers_is_replaced(self):
        opener = CountingOpener()
        with (
            RoundScope.round_scope(),
            patch.object(RoundScope.RoundScope, 'IDLE_PING_SECONDS', 0.0),
        ):
            use_like_a_helper(opener)
            opener.opened[0].ping.side_effect = RuntimeError('server restarted')
            use_like_a_helper(opener)
        self.assertEqual(len(opener.opened), 2)

    def test_an_idle_connection_that_answers_is_kept(self):
        opener = CountingOpener()
        with (
            RoundScope.round_scope(),
            patch.object(RoundScope.RoundScope, 'IDLE_PING_SECONDS', 0.0),
        ):
            use_like_a_helper(opener)
            use_like_a_helper(opener)
        self.assertEqual(len(opener.opened), 1)
        opener.opened[0].ping.assert_called_with(reconnect=False)

    def test_a_failed_connect_propagates_and_the_next_one_retries(self):
        calls = []

        def opener():
            calls.append(1)
            if len(calls) == 1:
                raise ConnectionError('refused')
            return MagicMock()

        with RoundScope.round_scope():
            with self.assertRaises(ConnectionError):
                RoundScope.connect(opener)
            RoundScope.connect(opener).close()
        self.assertEqual(len(calls), 2)


class ThreadsTest(unittest.TestCase):
    def test_each_attached_thread_gets_its_own_connection_and_keeps_it(self):
        """A pymysql connection is not thread-safe: never lend one thread's to another."""
        opener = CountingOpener()
        used_by: dict[int, set[int]] = {}
        lock = threading.Lock()

        def work(_):
            connection = RoundScope.connect(opener)
            with lock:
                used_by.setdefault(id(connection._slot.connection), set()).add(threading.get_ident())
            connection.close()

        with RoundScope.round_scope() as scope:
            with ThreadPoolExecutor(max_workers=4, initializer=scope.attach) as pool:
                list(pool.map(work, range(200)))
        self.assertLessEqual(len(opener.opened), 4)
        self.assertEqual(scope.borrowed, 200)
        for threads in used_by.values():
            self.assertEqual(len(threads), 1)
        for connection in opener.opened:
            connection.close.assert_called_once()

    def test_a_thread_that_did_not_join_the_round_gets_fresh_connections(self):
        """The event writer and uvicorn's threads share the process with a round and must
        not be handed its connections."""
        opener = CountingOpener()
        with RoundScope.round_scope():
            outsider = threading.Thread(target=lambda: [use_like_a_helper(opener) for _ in range(3)])
            outsider.start()
            outsider.join()
        self.assertEqual(len(opener.opened), 3)


class MemoTest(unittest.TestCase):
    def test_a_value_is_built_once_per_round(self):
        build = MagicMock(side_effect=lambda: object())
        with RoundScope.round_scope() as scope:
            first = scope.memo('key', build)
            self.assertIs(scope.memo('key', build), first)
        with RoundScope.round_scope() as scope:
            self.assertIsNot(scope.memo('key', build), first)
        self.assertEqual(build.call_count, 2)


_REAL_SOURCE = Path(__file__).resolve().parent / 'DatabaseConnector.py'


class RealDatabaseConnectorTest(unittest.TestCase):
    """mock_base replaces DatabaseConnector wholesale, so load the real file to prove it goes through the round."""

    def setUp(self):
        spec = importlib.util.spec_from_file_location('_real_database_connector_round', _REAL_SOURCE)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'pymysql': MagicMock()}):
            spec.loader.exec_module(self.module)
        env = {'DB_HOST': 'localhost', 'DB_USER': 'user', 'DB_PORT': '3306', 'DB_PASS': 'x', 'DB_DB': 'db'}
        patcher = patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_round_of_helper_calls_connects_once(self):
        with patch.object(self.module, 'pymysql') as pymysql:
            with RoundScope.round_scope():
                for _ in range(10):
                    connection = self.module.DatabaseConnector().connect()
                    connection.close()
                with self.module.DatabaseConnector().connection() as connection:
                    connection.commit()
            self.assertEqual(pymysql.connect.call_count, 1)
            pymysql.connect.return_value.close.assert_called_once()

    def test_outside_a_round_every_call_connects(self):
        with patch.object(self.module, 'pymysql') as pymysql:
            for _ in range(3):
                self.module.DatabaseConnector().connect().close()
            self.assertEqual(pymysql.connect.call_count, 3)


if __name__ == '__main__':
    unittest.main()
