"""The tracks a downloader has decided not to fetch, and why.

Some tracks answer 403 every time: subscriber-only, geo-blocked, since made
private. Others are outside the duration range the source is configured for. Both
are decisions, and without a memory the sweep pays for each of them on every pass
-- which is what stops an account from ever being finished.

Nothing is written off forever. A 403 is retried once its window has passed,
because a Go+ track can go free. A duration verdict is not retried on a clock at
all: the duration is stored alongside it and the verdict is formed again from the
bounds in force, so widening the filter brings those tracks back without a single
request spent rediscovering what they are.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

# Verdicts about a track's duration. These are re-formed from the bounds in force
# rather than expiring on a clock, because the track is not going to change.
DURATION_REASONS = ('too_short', 'too_long')

# How many ids one IN (...) clause is allowed to carry.
_CHUNK = 500


@dataclass(frozen=True)
class WriteOff:
    """One recorded decision not to fetch a track."""

    reason: str
    last_seen: datetime
    duration: int | None = None
    attempts: int = 0


def is_still_written_off(last_seen: datetime, retry_days: int, now: datetime) -> bool:
    """Whether a track that failed at ``last_seen`` should still be skipped."""
    if retry_days <= 0:
        return False
    return now - last_seen < timedelta(days=retry_days)


def still_written_off(entry: WriteOff, retry_days: int, now: datetime, bounds: tuple[int, int] | None = None) -> bool:
    """Whether this recorded decision still stands.

    A duration verdict is re-formed from ``bounds`` rather than believed, so a
    widened filter is enough to bring the track back. A row with no duration
    stored predates that and is taken at its word.
    """
    if entry.reason in DURATION_REASONS:
        if entry.duration is None or bounds is None:
            return True
        low, high = bounds
        return not low <= entry.duration <= high
    return is_still_written_off(entry.last_seen, retry_days, now)


def chunked(values: list[str], size: int = _CHUNK):
    """Split a list of ids into blocks a single statement can carry."""
    for start in range(0, len(values), size):
        yield values[start : start + size]


class InMemoryWriteOffStore:
    """Keeps the write-offs in a dict. Used by tests."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str, str], WriteOff] = {}

    def load(self, source: str, account: str, track_id: str) -> WriteOff | None:
        return self.rows.get((source, account, track_id))

    def load_many(self, source: str, account: str, track_ids: Iterable[str]) -> dict[str, WriteOff]:
        wanted = set(track_ids)
        return {
            track_id: row
            for (row_source, row_account, track_id), row in self.rows.items()
            if row_source == source and row_account == account and track_id in wanted
        }

    def remember(
        self, source: str, account: str, track_id: str, reason: str, when: datetime, duration: int | None, attempts: int
    ) -> None:
        previous = self.rows.get((source, account, track_id))
        kept_duration = duration if duration is not None else (previous.duration if previous else None)
        self.rows[(source, account, track_id)] = WriteOff(reason, when, kept_duration, attempts)


class DatabaseWriteOffStore:
    """Persists the write-offs in ``downloads_soundcloud_unavailable``.

    The table keeps its old name so the 403s already recorded in it stay
    meaningful; it now carries a ``source`` column and serves both downloaders.
    """

    def _connect(self):
        from services.common.Helpers.DatabaseConnector import DatabaseConnector
        from services.downloader.db_schema import ensure_once

        connection = DatabaseConnector().connect()
        ensure_once(connection)
        return connection

    @staticmethod
    def _write_off(row) -> WriteOff:
        reason, last_seen, duration, attempts = row
        return WriteOff(
            reason=reason,
            last_seen=last_seen,
            duration=None if duration is None else int(duration),
            attempts=int(attempts or 0),
        )

    def load(self, source: str, account: str, track_id: str) -> WriteOff | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    'SELECT reason, last_seen, duration_seconds, attempts '
                    'FROM downloads_soundcloud_unavailable '
                    'WHERE source = %s AND account = %s AND track_id = %s',
                    (source, account, track_id),
                )
                row = cursor.fetchone()
                return self._write_off(row) if row else None
        finally:
            connection.close()

    def load_many(self, source: str, account: str, track_ids: Iterable[str]) -> dict[str, WriteOff]:
        ids = [str(track_id) for track_id in track_ids]
        if not ids:
            return {}
        found: dict[str, WriteOff] = {}
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                for chunk in chunked(ids):
                    placeholders = ', '.join(['%s'] * len(chunk))
                    cursor.execute(
                        'SELECT track_id, reason, last_seen, duration_seconds, attempts '
                        'FROM downloads_soundcloud_unavailable '
                        'WHERE source = %s AND account = %s '
                        f'AND track_id IN ({placeholders})',
                        (source, account, *chunk),
                    )
                    for row in cursor.fetchall():
                        found[str(row[0])] = self._write_off(row[1:])
        finally:
            connection.close()
        return found

    def remember(
        self, source: str, account: str, track_id: str, reason: str, when: datetime, duration: int | None, attempts: int
    ) -> None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                # COALESCE on the duration: a later 403 on a track we once
                # measured must not erase the measurement, or the verdict can
                # never be re-formed from the bounds.
                cursor.execute(
                    'INSERT INTO downloads_soundcloud_unavailable '
                    '(source, account, track_id, reason, first_seen, last_seen, '
                    ' duration_seconds, attempts) '
                    'VALUES (%s, %s, %s, %s, %s, %s, %s, %s) '
                    'ON DUPLICATE KEY UPDATE reason = %s, last_seen = %s, '
                    '  duration_seconds = COALESCE(%s, duration_seconds), attempts = %s',
                    (
                        source,
                        account,
                        track_id,
                        reason,
                        when,
                        when,
                        duration,
                        attempts,
                        reason,
                        when,
                        duration,
                        attempts,
                    ),
                )
            connection.commit()
        finally:
            connection.close()


class WriteOffs:
    """Decides whether a track is worth asking the source about again.

    A store that cannot be read is treated as "nothing is written off": losing the
    memory costs a wasted request, while refusing to download because the database
    blinked costs the whole point of the sweep.
    """

    def __init__(
        self, source: str, store=None, retry_days: int = 30, now: Callable[[], datetime] = datetime.now
    ) -> None:
        self.source = source
        self._store = store if store is not None else DatabaseWriteOffStore()
        self.retry_days = retry_days
        self._now = now

    def now(self) -> datetime:
        """The clock this ledger judges its windows by -- injected in tests, the wall clock otherwise."""
        return self._now()

    def should_skip(self, account: str, track_id: str | None, bounds: tuple[int, int] | None = None) -> bool:
        if not track_id:
            return False
        try:
            entry = self._store.load(self.source, account, str(track_id))
        except Exception as exc:
            logging.warning('Could not read the %s write-offs for %s: %s', self.source, account, exc)
            return False
        if entry is None:
            return False
        return still_written_off(entry, self.retry_days, self._now(), bounds)

    def load_many(self, account: str, track_ids: Iterable[str]) -> dict[str, WriteOff]:
        """Every write-off held for these tracks.

        Raises rather than guessing. The deep pass uses this to decide what to
        download, so an unreadable store has to stop the pass instead of quietly
        enlarging it into a re-download of the whole account.
        """
        return self._store.load_many(self.source, account, [str(track_id) for track_id in track_ids])

    def remember(self, account: str, track_id: str | None, reason: str, duration: int | None = None) -> None:
        if not track_id:
            return
        try:
            self._store.remember(self.source, account, str(track_id), reason, self._now(), duration, 0)
        except Exception as exc:
            logging.warning('Could not write off %s/%s: %s', account, track_id, exc)

    def note_failure(self, account: str, track_id: str | None, max_attempts: int = 3) -> bool:
        """Count one failed attempt, and write the track off once it runs out.

        A track that neither downloads nor rejects would otherwise keep its
        account incomplete forever, and an incomplete account is swept again the
        next day. `failing` holds it back for one retry window at a time; `failed`
        settles it.
        """
        if not track_id:
            return False
        try:
            entry = self._store.load(self.source, account, str(track_id))
            attempts = (entry.attempts if entry else 0) + 1
            reason = 'failed' if attempts >= max_attempts else 'failing'
            self._store.remember(self.source, account, str(track_id), reason, self._now(), None, attempts)
            return reason == 'failed'
        except Exception as exc:
            logging.warning('Could not record the failure of %s/%s: %s', account, track_id, exc)
            return False
