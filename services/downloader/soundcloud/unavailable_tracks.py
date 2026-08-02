"""The tracks SoundCloud will not hand over.

Some tracks answer 403 every single time: subscriber-only, geo-blocked, since
made private. Without a memory the sweep pays for each of them on every pass,
and every one of those 403s used to be read as SoundCloud pushing back. Writing
them down turns a permanent cost into a one-off one.

Nothing is written off forever -- a Go+ track can go free and a private track can
be published -- so an entry is retried once its window has passed.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta


def is_still_written_off(last_seen: datetime, retry_days: int, now: datetime) -> bool:
    """Whether a track that failed at ``last_seen`` should still be skipped."""
    if retry_days <= 0:
        return False
    return now - last_seen < timedelta(days=retry_days)


class InMemoryUnavailableStore:
    """Keeps the write-offs in a dict. Used by tests."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict] = {}

    def load(self, account: str, track_id: str) -> datetime | None:
        row = self.rows.get((account, track_id))
        return row['last_seen'] if row else None

    def remember(self, account: str, track_id: str, reason: str, when: datetime) -> None:
        row = self.rows.get((account, track_id))
        first_seen = row['first_seen'] if row else when
        self.rows[(account, track_id)] = {
            'reason': reason, 'first_seen': first_seen, 'last_seen': when,
        }


class DatabaseUnavailableStore:
    """Persists the write-offs in ``downloads_soundcloud_unavailable``."""

    def _connect(self):
        from services.common.Helpers.DatabaseConnector import DatabaseConnector
        from services.downloader.db_schema import ensure_once
        connection = DatabaseConnector().connect()
        ensure_once(connection)
        return connection

    def load(self, account: str, track_id: str) -> datetime | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    'SELECT last_seen FROM downloads_soundcloud_unavailable '
                    'WHERE account = %s AND track_id = %s',
                    (account, track_id))
                row = cursor.fetchone()
                if not row:
                    return None
                return row[0] if isinstance(row, (tuple, list)) else row['last_seen']
        finally:
            connection.close()

    def remember(self, account: str, track_id: str, reason: str, when: datetime) -> None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    'INSERT INTO downloads_soundcloud_unavailable '
                    '(account, track_id, reason, first_seen, last_seen) '
                    'VALUES (%s, %s, %s, %s, %s) '
                    'ON DUPLICATE KEY UPDATE reason = %s, last_seen = %s',
                    (account, track_id, reason, when, when, reason, when))
            connection.commit()
        finally:
            connection.close()


class UnavailableTracks:
    """Decides whether a track is worth asking SoundCloud about again.

    A store that cannot be read is treated as "nothing is written off": losing the
    memory costs a wasted request, while refusing to download because the database
    blinked costs the whole point of the sweep.
    """

    def __init__(self, store=None, retry_days: int = 30,
                 now: Callable[[], datetime] = datetime.now) -> None:
        self._store = store if store is not None else DatabaseUnavailableStore()
        self.retry_days = retry_days
        self._now = now

    def should_skip(self, account: str, track_id: str | None) -> bool:
        if not track_id:
            return False
        try:
            last_seen = self._store.load(account, str(track_id))
            if last_seen is None:
                return False
            return is_still_written_off(last_seen, self.retry_days, self._now())
        except Exception as exc:
            logging.warning('Could not read the SoundCloud write-offs for %s: %s', account, exc)
            return False

    def remember(self, account: str, track_id: str | None, reason: str) -> None:
        if not track_id:
            return
        try:
            self._store.remember(account, str(track_id), reason, self._now())
        except Exception as exc:
            logging.warning('Could not write off %s/%s: %s', account, track_id, exc)
