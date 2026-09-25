"""What one tagging round shares: a database connection per thread, and values built once.

Every helper the tagger calls per file (ProcessedFilesHelper, the download-info lookup,
the ingestion record, the ignore and genre lists, GenreRulesHelper.record_unknown) opened
its own pymysql connection through `DatabaseConnector.connect()` and closed it again.
At ~14 ms per connect (measured by `ProcessedFilesHelper.load_snapshot`) against well
under a millisecond per query, that was 3-6 connects and most of the database cost of
every file the pending pass handed out.

Inside `round_scope()` those connects are served by one connection per thread instead:

- A pymysql connection is not thread-safe, so the connection belongs to the thread that
  opened it and is never handed to another one. The tagger's worker threads join the
  round through `RoundScope.attach` (the thread pool's initializer); a thread that never
  joined -- the event writer, uvicorn's request threads -- keeps getting fresh ones.
- A helper still calls `close()` when it is done. Inside a round that ends the
  transaction (a rollback, exactly what closing the socket did to anything uncommitted)
  instead of the connection, so the next helper starts from a clean transaction and does
  not read a stale REPEATABLE READ snapshot.
- A helper that connects while its own thread's connection is still open -- one helper
  calling another -- gets a separate, real connection, so an inner `close()` can never roll
  back the outer caller's work.
- A connection that failed is dropped and the next connect opens a new one; one that sat
  idle for a while is pinged first.

`memo` is the other half: a value built once per round and shared by every thread, which
is what the tagger's rule stack uses (see services/tagger/Song/rule_stack.py).

Outside a round nothing changes: `connect` calls the opener and returns what it returns.
This module is deliberately separate from DatabaseConnector, which the unit tests replace
wholesale (services/tests/mock_base.py); this one they exercise for real.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

_current = threading.local()


class _Slot:
    """The connection one thread holds for the round, and whether it is lent out right now."""

    def __init__(self, connection: Any):
        self.connection = connection
        self.in_use = False
        self.broken = False
        self.last_used = time.monotonic()

    def close(self) -> None:
        """Close the socket itself; used when the slot is replaced and when the round ends."""
        try:
            self.connection.close()
        except Exception:  # noqa: BLE001 - a close that fails has nothing left to protect
            logging.debug('Ignoring failure while closing a round connection', exc_info=True)

    def release(self) -> None:
        """End the borrower's transaction and make the connection available to the thread again."""
        try:
            self.connection.rollback()
        except Exception:  # noqa: BLE001 - a dead connection is replaced on the next borrow
            self.broken = True
            self.close()
        self.in_use = False
        self.last_used = time.monotonic()


class _Borrowed:
    """What a helper gets inside a round: the thread's connection, with `close()` ending the
    transaction rather than the socket. Everything else is the real pymysql connection."""

    def __init__(self, slot: _Slot):
        self._slot = slot
        self._released = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._slot.connection, name)

    def close(self) -> None:
        """Give the connection back to the round; a second call does nothing."""
        if self._released:
            return
        self._released = True
        self._slot.release()

    def __enter__(self) -> _Borrowed:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


class RoundScope:
    """One round's connections (one per participating thread) and its memoized values."""

    #: A connection unused for longer than this is pinged before it is lent out again. A
    #: walk can spend minutes in folders where every file is up to date and nothing asks
    #: the database anything; MariaDB's own idle timeout is hours, so this is only about
    #: noticing a server restart before a helper does.
    IDLE_PING_SECONDS = 30.0

    def __init__(self) -> None:
        self._local = threading.local()
        self._lock = threading.RLock()
        self._slots: list[_Slot] = []
        self._memo: dict[Any, Any] = {}
        self.closed = False
        #: Connections actually opened during the round, reconnects and nested ones included.
        self.opened = 0
        #: Times a helper asked for a connection and was lent the thread's one.
        self.borrowed = 0

    def attach(self) -> None:
        """Make the calling thread part of this round. The thread pool's initializer."""
        _current.scope = self

    def connect(self, open_connection: Callable[[], Any]) -> Any:
        """The calling thread's connection, opened with `open_connection` when it has none."""
        slot: _Slot | None = getattr(self._local, 'slot', None)
        if slot is not None and slot.in_use:
            # A helper called from inside another helper's connection: its own, real one.
            connection = open_connection()
            self._count_open()
            return connection
        if slot is not None and not self._usable(slot):
            slot.close()
            slot = None
        if slot is None:
            slot = _Slot(open_connection())
            self._count_open()
            self._local.slot = slot
            with self._lock:
                self._slots.append(slot)
        slot.in_use = True
        with self._lock:
            self.borrowed += 1
        return _Borrowed(slot)

    def _usable(self, slot: _Slot) -> bool:
        if slot.broken:
            return False
        if time.monotonic() - slot.last_used < self.IDLE_PING_SECONDS:
            return True
        try:
            slot.connection.ping(reconnect=False)
            return True
        except Exception:  # noqa: BLE001 - any failure means: open a new one
            return False

    def _count_open(self) -> None:
        with self._lock:
            self.opened += 1

    def memo(self, key: Any, build: Callable[[], Any]) -> Any:
        """`build()` the first time `key` is asked for in this round, the same object after that."""
        with self._lock:
            if key not in self._memo:
                self._memo[key] = build()
            return self._memo[key]

    def close(self) -> None:
        """Close every connection the round opened. Called once the round's threads are done."""
        with self._lock:
            self.closed = True
            slots, self._slots = self._slots, []
            self._memo = {}
        for slot in slots:
            slot.close()


def current() -> RoundScope | None:
    """The round the calling thread takes part in, or None."""
    scope = getattr(_current, 'scope', None)
    if scope is None or scope.closed:
        return None
    return scope


@contextmanager
def round_scope() -> Iterator[RoundScope]:
    """Run the block as one round: the calling thread joins it, and it is closed afterwards."""
    scope = RoundScope()
    previous = getattr(_current, 'scope', None)
    _current.scope = scope
    try:
        yield scope
    finally:
        _current.scope = previous
        scope.close()


def connect(open_connection: Callable[[], Any]) -> Any:
    """A connection for the calling thread: the round's when it takes part in one, else a new one."""
    scope = current()
    if scope is None:
        return open_connection()
    return scope.connect(open_connection)
