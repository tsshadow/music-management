"""Per-account scheduling for the downloaders.

Sweeping every account on every run is what generates the traffic that gets a
downloader rate limited. The cooldown here spreads that out: a sweep only touches
the accounts that have not been looked at recently, so raising the sweep frequency
no longer means raising the request count.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Mapping, Optional


def due_accounts(accounts: Iterable[str], last_checked: Mapping[str, datetime],
                 cooldown: int, now: datetime) -> List[str]:
    """Return the accounts that may be checked again, in their original order."""
    if cooldown <= 0:
        return list(accounts)
    due = []
    for account in accounts:
        checked_at = last_checked.get(account)
        if checked_at is None or (now - checked_at).total_seconds() >= cooldown:
            due.append(account)
    return due


class InMemoryCheckStore:
    """Keeps the check times in a dict. Used by tests."""

    def __init__(self) -> None:
        self._rows: Dict[str, Dict[str, datetime]] = {}

    def load(self, source: str) -> Dict[str, datetime]:
        return dict(self._rows.get(source, {}))

    def mark(self, source: str, account: str, when: datetime) -> None:
        self._rows.setdefault(source, {})[account] = when


class DatabaseCheckStore:
    """Persists the check times in ``downloads_account_checks``."""

    def _connect(self):
        from services.common.Helpers.DatabaseConnector import DatabaseConnector
        from services.downloader.db_schema import ensure_once
        connection = DatabaseConnector().connect()
        ensure_once(connection)
        return connection

    def load(self, source: str) -> Dict[str, datetime]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    'SELECT account, last_checked_at FROM downloads_account_checks WHERE source = %s',
                    (source,))
                return dict(cursor.fetchall())
        finally:
            connection.close()

    def mark(self, source: str, account: str, when: datetime) -> None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    'INSERT INTO downloads_account_checks (source, account, last_checked_at) '
                    'VALUES (%s, %s, %s) '
                    'ON DUPLICATE KEY UPDATE last_checked_at = %s',
                    (source, account, when, when))
            connection.commit()
        finally:
            connection.close()


class AccountSchedule:
    """Decides which accounts of one source are due for a check.

    A store that cannot be read is treated as "nothing was ever checked", which
    keeps the downloader working when the database is briefly unavailable.
    """

    def __init__(self, source: str, store=None,
                 now: Callable[[], datetime] = datetime.now) -> None:
        self.source = source
        self._store = store if store is not None else DatabaseCheckStore()
        self._now = now

    def _last_checked(self) -> Dict[str, datetime]:
        try:
            return self._store.load(self.source)
        except Exception as exc:
            logging.warning('Could not read the check schedule for %s: %s', self.source, exc)
            return {}

    def due(self, accounts: Iterable[str], cooldown: int) -> List[str]:
        return due_accounts(accounts, self._last_checked(), cooldown, self._now())

    def mark_checked(self, account: str, when: Optional[datetime] = None) -> None:
        try:
            self._store.mark(self.source, account, when or self._now())
        except Exception as exc:
            logging.warning('Could not record the check of %s/%s: %s', self.source, account, exc)
