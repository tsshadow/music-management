"""Self-regulating backoff state for the downloaders.

A downloader that hits HTTP 429 has to slow down, and it has to still be slow
after a restart -- otherwise a container restart wipes the lesson and the hammering
starts over. The multiplier and the cooldown therefore live in the database.

The arithmetic is kept in plain functions so the ladders can be tested without a
database anywhere near them.
"""
from __future__ import annotations

import logging
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from services.downloader.timing import DownloaderTiming


class RateLimited(Exception):
    """Raised when a source told us to go away, so the sweep can stop early."""

    def __init__(self, source: str, wait: int, reason: str) -> None:
        super().__init__(f'{source} is rate limited ({reason}); staying away for {wait}s')
        self.source = source
        self.wait = wait
        self.reason = reason


class SweepAborted(Exception):
    """Raised for accounts that were skipped because the sweep was already stopping."""


def next_multiplier_on_429(multiplier: int, max_multiplier: int) -> int:
    """Double the multiplier, never past the ceiling."""
    return min(max(1, multiplier) * 2, max_multiplier)


def wait_after_429(base: int, multiplier: int, jitter: float) -> int:
    """How long to stay away after a 429."""
    return int(base * max(1, multiplier) * jitter)


def backoff_403_wait(count: int, base: int, factor: int, cap: int) -> int:
    """The 403 ladder: the base, multiplied by the factor once per repeat, capped."""
    steps = max(1, count) - 1
    return min(base * factor ** steps, cap)


def recover(multiplier: int, clean_runs: int, recovery_runs: int) -> tuple[int, int]:
    """Register one clean run and return the new multiplier and clean-run count."""
    runs = clean_runs + 1
    if runs >= recovery_runs:
        return (max(1, multiplier // 2), 0)
    return (multiplier, runs)


@dataclass
class RateSnapshot:
    """Everything that is remembered about how a source is currently behaving."""
    source: str
    multiplier: int = 1
    consecutive_403: int = 0
    consecutive_429: int = 0
    clean_runs: int = 0
    last_403_at: datetime | None = None
    last_429_at: datetime | None = None
    cooldown_until: datetime | None = None


class InMemoryRateStateStore:
    """Keeps state in a dict. Used by tests and as a fallback when there is no database."""

    def __init__(self) -> None:
        self._rows: dict[str, RateSnapshot] = {}

    def load(self, source: str) -> RateSnapshot | None:
        stored = self._rows.get(source)
        if stored is None:
            return None
        return RateSnapshot(**vars(stored))

    def save(self, snapshot: RateSnapshot) -> None:
        self._rows[snapshot.source] = RateSnapshot(**vars(snapshot))


class DatabaseRateStateStore:
    """Persists the state in ``downloads_rate_state``."""

    _COLUMNS = ('multiplier', 'consecutive_403', 'consecutive_429', 'clean_runs',
                'last_403_at', 'last_429_at', 'cooldown_until')

    def _connect(self):
        from services.common.Helpers.DatabaseConnector import DatabaseConnector
        from services.downloader.db_schema import ensure_once
        connection = DatabaseConnector().connect()
        ensure_once(connection)
        return connection

    def load(self, source: str) -> RateSnapshot | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f'SELECT {", ".join(self._COLUMNS)} FROM downloads_rate_state WHERE source = %s',
                    (source,))
                row = cursor.fetchone()
            if row is None:
                return None
            return RateSnapshot(source=source, **dict(zip(self._COLUMNS, row, strict=True)))
        finally:
            connection.close()

    def save(self, snapshot: RateSnapshot) -> None:
        assignments = ', '.join(f'{column} = %s' for column in self._COLUMNS)
        values = tuple(getattr(snapshot, column) for column in self._COLUMNS)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f'INSERT INTO downloads_rate_state (source, {", ".join(self._COLUMNS)}) '
                    f'VALUES (%s, {", ".join(["%s"] * len(self._COLUMNS))}) '
                    f'ON DUPLICATE KEY UPDATE {assignments}',
                    (snapshot.source,) + values + values)
            connection.commit()
        finally:
            connection.close()


def _default_jitter() -> float:
    return random.uniform(1.0, 1.5)


class RateState:
    """Reads, updates and persists the backoff state of one source.

    Storage failures are logged and swallowed: a downloader that cannot reach the
    database should still back off in-process rather than fall over.
    """

    def __init__(self, source: str, timing: DownloaderTiming, store=None,
                 now: Callable[[], datetime] = datetime.now,
                 jitter: Callable[[], float] = _default_jitter) -> None:
        self.source = source
        self.timing = timing
        self._store = store if store is not None else DatabaseRateStateStore()
        self._now = now
        self._jitter = jitter
        self._snapshot = self._load()

    def _load(self) -> RateSnapshot:
        try:
            stored = self._store.load(self.source)
        except Exception as exc:
            logging.warning('Could not read rate state for %s: %s', self.source, exc)
            return RateSnapshot(source=self.source)
        return stored if stored is not None else RateSnapshot(source=self.source)

    def _persist(self) -> None:
        try:
            self._store.save(self._snapshot)
        except Exception as exc:
            logging.warning('Could not persist rate state for %s: %s', self.source, exc)

    def snapshot(self) -> RateSnapshot:
        return RateSnapshot(**vars(self._snapshot))

    @property
    def multiplier(self) -> int:
        return max(1, self._snapshot.multiplier or 1)

    def cooldown_remaining(self) -> int:
        """Seconds left before this source may be touched again."""
        until = self._snapshot.cooldown_until
        if until is None:
            return 0
        remaining = (until - self._now()).total_seconds()
        return max(0, int(remaining))

    def record_429(self) -> int:
        """Register a 429 and return how long to stay away."""
        now = self._now()
        self._snapshot.multiplier = next_multiplier_on_429(self.multiplier, self.timing.max_multiplier)
        self._snapshot.consecutive_429 += 1
        self._snapshot.clean_runs = 0
        self._snapshot.last_429_at = now
        wait = wait_after_429(self.timing.backoff_429_base, self._snapshot.multiplier, self._jitter())
        self._snapshot.cooldown_until = now + timedelta(seconds=wait)
        self._persist()
        return wait

    def record_403(self) -> int:
        """Register a 403 and return how long to stay away."""
        now = self._now()
        self._snapshot.consecutive_403 += 1
        self._snapshot.last_403_at = now
        wait = backoff_403_wait(self._snapshot.consecutive_403, self.timing.backoff_403_base,
                                self.timing.backoff_403_factor, self.timing.backoff_403_cap)
        self._snapshot.cooldown_until = now + timedelta(seconds=wait)
        self._persist()
        return wait

    def record_success(self) -> None:
        """Register a clean run, which slowly walks the multiplier back down."""
        multiplier, clean_runs = recover(self.multiplier, self._snapshot.clean_runs,
                                        self.timing.recovery_runs)
        self._snapshot.multiplier = multiplier
        self._snapshot.clean_runs = clean_runs
        self._snapshot.consecutive_403 = 0
        self._snapshot.consecutive_429 = 0
        self._persist()

    def reset(self) -> None:
        """Forget everything and start at full speed again."""
        self._snapshot = RateSnapshot(source=self.source)
        self._persist()
