"""Short write transactions into a server's lms.db, and the rows a busy server made wait.

Shared by the two pushes that write muma's own columns into LMS's `track` table: the song
versions (`song_version_sync`) and the form and performance date (`track_form_sync`). Both read
every row without a transaction, keep what the server disagrees with, and hand that here.

**Who holds the lock.** Measured on production on 2026-09-29 (bug report 129): while LMS scans,
its scanner holds SQLite's WAL write lock for runs of up to twenty seconds with gaps of a few
milliseconds between them -- 5,853 of 5,855 samples over thirty seconds found it held. Scans run
for hours (a library-wide walk) or a minute (a folder the downloader announced, hundreds of them a
day). No lock wait a background job can afford outlasts that, and the old handling -- two seconds
of patience, a minute of sleep, three tries per batch, then a WARNING and the batch dropped from
the pass -- met it 40 times a day and parked the hourly sync for up to eleven minutes at a time.

**What this does instead.**

- Every batch opens with `BEGIN IMMEDIATE`, so the write lock is taken up front while the
  connection holds nothing. A deferred transaction would read first and then upgrade, and SQLite
  refuses an upgrade at once, busy timeout or not; taking the lock first is the only shape in which
  the busy timeout is honoured. Waiting in that state costs LMS nothing -- a connection waiting for
  the write lock holds no lock of its own -- so the timeout can be longer than the two seconds it
  was. What must stay short is how long the lock is *held* once taken, and that is WRITE_BATCH
  indexed UPDATEs: milliseconds.
- The first batch that still finds the server busy ends the writing for that pass. Every row not
  written -- that batch and every later one -- is kept in a `PendingWrites`, never dropped, so the
  caller can write exactly those rows again a few minutes later (`routers/users.py`) instead of
  sleeping through the scan batch by batch.
"""

import contextlib
import sqlite3
from typing import Any

#: How long one batch waits for the server's write lock before the pass defers its rows.
#: Waiting holds nothing (see the module docstring), so this only bounds how long the sync thread
#: sits on one attempt. Spelled out as a literal statement rather than built from the number:
#: PRAGMA takes no bound parameter, so any computed form is a formatted SQL string -- a shape
#: worth not having at all. LmsWritesTest keeps the two in step.
BUSY_TIMEOUT_MS = 10000
BUSY_TIMEOUT_STATEMENT = 'PRAGMA busy_timeout = 10000'

#: How many UPDATEs share one write transaction. The player aborts a request -- a rating, a
#: scrobble, a token bump -- the instant it meets this job's lock (its transactions read before
#: they write), so every transaction opened here has to be a blink. A hundred indexed UPDATEs
#: commit in milliseconds.
WRITE_BATCH = 100

#: One pending write: the values to store and the key the UPDATE's last parameter binds to --
#: the server row id for the song versions, the path for the track form.
Row = tuple[tuple[Any, ...], Any]


def is_lock_error(error: sqlite3.OperationalError) -> bool:
    """Whether this error is SQLite saying another connection holds the lock ("locked"/"busy")."""
    message = str(error).lower()
    return 'locked' in message or 'busy' in message


class PendingWrites:
    """The rows one push still has to write into one server, and whether that server was busy.

    `update_sql` takes `values + (key,)`. Once `busy` is set, `write` stops opening transactions
    and only collects: the server is scanning, and every further attempt in this pass would wait
    out the same scan. `rows` is what is left, for `write` to be called with again later.
    """

    def __init__(self, update_sql: str) -> None:
        """An empty set of pending writes for `update_sql`."""
        self.update_sql = update_sql
        self.rows: list[Row] = []
        self.busy = False

    def write(self, server_conn: Any, server_cursor: Any, rows: list[Row]) -> int:
        """Write `rows` in batches of WRITE_BATCH; returns how many server rows changed.

        A batch that finds the server busy, and every batch after it, is kept in `self.rows`
        rather than written. Any error that is not a lock is raised: waiting on a broken schema
        helps nobody and buries the real message.

        `server_cursor` should be the cursor the rows were read with. Executing on it resets the
        last read statement, so the connection holds no read transaction when BEGIN IMMEDIATE
        asks for the write lock -- a connection that does gets SQLITE_BUSY at once, without
        waiting (the same upgrade rule the module docstring describes).
        """
        matched = 0
        for start in range(0, len(rows), WRITE_BATCH):
            batch = rows[start : start + WRITE_BATCH]
            if self.busy:
                self.rows.extend(batch)
                continue
            written = _write_batch(server_conn, server_cursor, batch, self.update_sql)
            if written is None:
                self.busy = True
                self.rows.extend(batch)
            else:
                matched += written
        return matched

    def retry(self, server_conn: Any) -> int:
        """Try the rows left over once more, on a fresh connection; returns rows changed.

        Clears `busy` first: this is a new attempt, minutes after the one that deferred them.
        Whatever is still refused stays in `self.rows`.
        """
        rows, self.rows, self.busy = self.rows, [], False
        return self.write(server_conn, server_conn.cursor(), rows)


def _write_batch(server_conn: Any, server_cursor: Any, batch: list[Row], update_sql: str) -> int | None:
    """One short write transaction, lock taken up front. Returns rows changed, or None if busy."""
    try:
        server_cursor.execute('BEGIN IMMEDIATE')
        matched = 0
        for values, key in batch:
            server_cursor.execute(update_sql, values + (key,))
            matched += server_cursor.rowcount
        server_conn.commit()
        return matched
    except sqlite3.OperationalError as e:
        # In a suppress, because a failed BEGIN leaves nothing to roll back and a rollback
        # that fails must not replace the error that explains what happened.
        with contextlib.suppress(Exception):
            server_conn.rollback()
        if not is_lock_error(e):
            raise
        return None
