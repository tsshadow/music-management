"""Writing into a server database whose write lock somebody else holds (bug report 129).

Against real SQLite files in WAL mode with two real connections, because what is under test is
SQLite's locking itself: a second connection standing in for LMS's scanner holds the write lock,
and the claims are that a batch waits for it without holding anything, that a batch it cannot get
is kept rather than lost, and that the kept rows land once the lock is free.
"""

import os
import sqlite3
import tempfile
import threading
import time
import unittest

from services.music_manager import lms_writes
from services.music_manager.lms_writes import PendingWrites, is_lock_error

UPDATE = 'UPDATE track SET form = ?1 WHERE id = ?2 AND form IS NOT ?1'


class LmsWritesTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.mkdtemp()
        self.path = os.path.join(directory, 'lms.db')
        setup = sqlite3.connect(self.path)
        setup.execute('PRAGMA journal_mode=WAL')
        setup.execute("CREATE TABLE track (id INTEGER PRIMARY KEY, form TEXT NOT NULL DEFAULT '')")
        setup.executemany('INSERT INTO track (id) VALUES (?)', [(i,) for i in range(1, 6)])
        setup.commit()
        setup.close()
        # The scanner's connection, and ours.
        self.scanner = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self.ours = sqlite3.connect(self.path)
        self.addCleanup(self.scanner.close)
        self.addCleanup(self.ours.close)

    def forms(self):
        return [row[0] for row in self.scanner.execute('SELECT form FROM track ORDER BY id')]

    def test_a_held_lock_defers_the_rows_instead_of_dropping_them(self):
        self.ours.execute('PRAGMA busy_timeout = 50')
        self.scanner.execute('BEGIN IMMEDIATE')
        writes = PendingWrites(UPDATE)

        matched = writes.write(self.ours, self.ours.cursor(), [(('set',), 1), (('set',), 2)])

        self.assertEqual(matched, 0)
        self.assertTrue(writes.busy)
        self.assertEqual(writes.rows, [(('set',), 1), (('set',), 2)])
        self.assertFalse(self.ours.in_transaction, 'a refused batch leaves no transaction behind')
        self.scanner.execute('COMMIT')
        self.assertEqual(self.forms(), [''] * 5)

    def test_the_deferred_rows_land_once_the_lock_is_free(self):
        self.ours.execute('PRAGMA busy_timeout = 50')
        self.scanner.execute('BEGIN IMMEDIATE')
        writes = PendingWrites(UPDATE)
        writes.write(self.ours, self.ours.cursor(), [(('set',), 1), (('set',), 2)])
        self.scanner.execute('COMMIT')

        self.assertEqual(writes.retry(self.ours), 2)

        self.assertEqual((writes.rows, writes.busy), ([], False))
        self.assertEqual(self.forms(), ['set', 'set', '', '', ''])

    def test_a_retry_that_is_refused_again_keeps_every_row(self):
        self.ours.execute('PRAGMA busy_timeout = 50')
        self.scanner.execute('BEGIN IMMEDIATE')
        writes = PendingWrites(UPDATE)
        writes.write(self.ours, self.ours.cursor(), [(('set',), 1)])

        self.assertEqual(writes.retry(self.ours), 0)

        self.assertEqual(writes.rows, [(('set',), 1)])
        self.scanner.execute('COMMIT')

    def test_a_batch_waits_for_a_lock_that_is_let_go_within_the_timeout(self):
        # The busy timeout is honoured because the lock is asked for up front (BEGIN IMMEDIATE)
        # while this connection holds nothing. A deferred transaction that read first would be
        # refused at once instead -- SQLite does not wait on a read-to-write upgrade.
        self.ours.execute('PRAGMA busy_timeout = 5000')
        self.scanner.execute('BEGIN IMMEDIATE')
        release = threading.Timer(0.2, lambda: self.scanner.execute('COMMIT'))
        release.start()
        self.addCleanup(release.cancel)
        writes = PendingWrites(UPDATE)
        started = time.monotonic()

        matched = writes.write(self.ours, self.ours.cursor(), [(('set',), 3)])

        self.assertEqual(matched, 1)
        self.assertGreaterEqual(time.monotonic() - started, 0.15)
        self.assertEqual(writes.rows, [])

    def test_rows_are_written_in_transactions_of_write_batch(self):
        writes = PendingWrites(UPDATE)
        rows = [(('set',), i) for i in range(1, 6)]
        commits = []
        original = lms_writes.WRITE_BATCH
        lms_writes.WRITE_BATCH = 2
        self.addCleanup(setattr, lms_writes, 'WRITE_BATCH', original)

        class Counting:
            """Our connection, counting commits (sqlite3.Connection takes no patched attributes)."""

            def __init__(self, conn):
                self.conn = conn

            def commit(self):
                commits.append(1)
                self.conn.commit()

            def rollback(self):
                self.conn.rollback()

        self.assertEqual(writes.write(Counting(self.ours), self.ours.cursor(), rows), 5)
        self.assertEqual(len(commits), 3)

    def test_an_error_that_is_not_a_lock_is_raised(self):
        writes = PendingWrites('UPDATE nowhere SET x = ?1 WHERE id = ?2')
        with self.assertRaises(sqlite3.OperationalError):
            writes.write(self.ours, self.ours.cursor(), [(('set',), 1)])
        self.assertEqual(writes.rows, [])

    def test_lock_errors_are_recognised_by_either_word(self):
        self.assertTrue(is_lock_error(sqlite3.OperationalError('database is locked')))
        self.assertTrue(is_lock_error(sqlite3.OperationalError('database is busy')))
        self.assertFalse(is_lock_error(sqlite3.OperationalError('no such table: track')))

    def test_the_timeout_statement_says_what_the_constant_says(self):
        # A literal, because PRAGMA takes no bound parameter; only this test keeps the two in step.
        self.assertEqual(lms_writes.BUSY_TIMEOUT_STATEMENT, f'PRAGMA busy_timeout = {lms_writes.BUSY_TIMEOUT_MS}')

    def test_what_is_held_stays_short_even_though_the_wait_is_longer(self):
        # Waiting for the lock costs the player nothing; holding it costs it a rating. So the
        # batch that bounds the hold stays small, whatever the wait is.
        self.assertLessEqual(lms_writes.WRITE_BATCH, 100)


if __name__ == '__main__':
    unittest.main()
