"""Per-account scheduling for the downloaders.

Sweeping every account on every run is what generates the traffic that gets a
downloader rate limited. The cooldown here spreads that out: a sweep only touches
the accounts that have not been looked at recently, so raising the sweep frequency
no longer means raising the request count.

How long "recently" is depends on the account. One that uploaded this week is
worth coming back to today; one whose newest track is from 2019 is not. The
ladder in `cooldown_for` turns the age of an account's newest upload into its own
cooldown, which is what stops the quiet majority from setting the request budget
for everyone.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - for type checkers only
    from services.downloader.timing import DownloaderTiming

SECONDS_PER_DAY = 86400

# The tier boundaries, in days since the account's newest known upload. Week,
# month, quarter and year are calendar-meaningful and deliberately not settings;
# what an operator tunes is the cooldown each tier gets.
FRESH_DAYS = 7
RECENT_DAYS = 30
MONTHLY_DAYS = 90
OCCASIONAL_DAYS = 365


def cooldown_for(last_upload_at: datetime | None, now: datetime,
                 timing: DownloaderTiming) -> int:
    """How long to leave an account alone, given when it last uploaded.

    An unknown date counts as fresh. A newly added account has to be checked
    promptly, and one look is enough to place it in the tier it belongs in.
    """
    if last_upload_at is None:
        return timing.account_cooldown
    age_days = (now - last_upload_at).total_seconds() / SECONDS_PER_DAY
    if age_days < FRESH_DAYS:
        return timing.account_cooldown
    if age_days < RECENT_DAYS:
        return timing.recent_cooldown
    if age_days < MONTHLY_DAYS:
        return timing.monthly_cooldown
    if age_days < OCCASIONAL_DAYS:
        return timing.occasional_cooldown
    return timing.dormant_cooldown


@dataclass(frozen=True)
class AccountCheck:
    """What we know about one account after the last time we looked at it."""
    last_checked_at: datetime
    last_upload_at: datetime | None = None
    last_seen_track_id: str | None = None


def due_accounts(accounts: Iterable[str], checks: Mapping[str, AccountCheck],
                 cooldown: int, now: datetime,
                 cooldown_for_account: Callable[[AccountCheck | None], int] | None = None
                 ) -> list[str]:
    """Return the accounts that may be checked again, in their original order.

    ``cooldown_for_account`` decides the wait per account. Without it every
    account gets the same flat ``cooldown``.
    """
    due = []
    for account in accounts:
        record = checks.get(account)
        wait = cooldown if cooldown_for_account is None else cooldown_for_account(record)
        if wait <= 0:
            due.append(account)
            continue
        if record is None or (now - record.last_checked_at).total_seconds() >= wait:
            due.append(account)
    return due


class InMemoryCheckStore:
    """Keeps the check records in a dict. Used by tests."""

    def __init__(self) -> None:
        self._rows: dict[str, dict[str, AccountCheck]] = {}

    def load(self, source: str) -> dict[str, AccountCheck]:
        return dict(self._rows.get(source, {}))

    def mark(self, source: str, account: str, when: datetime,
             last_upload_at: datetime | None = None,
             last_seen_track_id: str | None = None) -> None:
        rows = self._rows.setdefault(source, {})
        previous = rows.get(account)
        rows[account] = AccountCheck(
            last_checked_at=when,
            last_upload_at=_kept(last_upload_at, previous, 'last_upload_at'),
            last_seen_track_id=_kept(last_seen_track_id, previous, 'last_seen_track_id'),
        )


def _kept(new_value, previous: AccountCheck | None, attribute: str):
    """The new value, or what was already stored when there is no new one.

    Mirrors the ``COALESCE`` in the database store: an ordinary check knows only
    the time, and must not wipe a date the account had already earned.
    """
    if new_value is not None:
        return new_value
    return getattr(previous, attribute) if previous is not None else None


class DatabaseCheckStore:
    """Persists the check records in ``downloads_account_checks``."""

    def _connect(self):
        from services.common.Helpers.DatabaseConnector import DatabaseConnector
        from services.downloader.db_schema import ensure_once
        connection = DatabaseConnector().connect()
        ensure_once(connection)
        return connection

    def load(self, source: str) -> dict[str, AccountCheck]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    'SELECT account, last_checked_at, last_upload_at, last_seen_track_id '
                    'FROM downloads_account_checks WHERE source = %s',
                    (source,))
                return {
                    account: AccountCheck(checked_at, upload_at, track_id)
                    for account, checked_at, upload_at, track_id in cursor.fetchall()
                }
        finally:
            connection.close()

    def mark(self, source: str, account: str, when: datetime,
             last_upload_at: datetime | None = None,
             last_seen_track_id: str | None = None) -> None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                # COALESCE, not a plain assignment: an ordinary check passes NULL
                # for the two upload columns and must leave them as they were.
                cursor.execute(
                    'INSERT INTO downloads_account_checks '
                    '(source, account, last_checked_at, last_upload_at, last_seen_track_id) '
                    'VALUES (%s, %s, %s, %s, %s) '
                    'ON DUPLICATE KEY UPDATE '
                    '  last_checked_at = VALUES(last_checked_at), '
                    '  last_upload_at = COALESCE(VALUES(last_upload_at), last_upload_at), '
                    '  last_seen_track_id = COALESCE(VALUES(last_seen_track_id), last_seen_track_id)',
                    (source, account, when, last_upload_at, last_seen_track_id))
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

    def _checks(self) -> dict[str, AccountCheck]:
        try:
            return self._store.load(self.source)
        except Exception as exc:
            logging.warning('Could not read the check schedule for %s: %s', self.source, exc)
            return {}

    def due(self, accounts: Iterable[str], timing: DownloaderTiming) -> list[str]:
        """The accounts whose own tier cooldown has passed."""
        now = self._now()

        def wait_for(record: AccountCheck | None) -> int:
            return cooldown_for(record.last_upload_at if record else None, now, timing)

        return due_accounts(accounts, self._checks(), timing.account_cooldown, now,
                            cooldown_for_account=wait_for)

    def mark_checked(self, account: str, when: datetime | None = None,
                     last_upload_at: datetime | None = None,
                     last_seen_track_id: str | None = None) -> None:
        try:
            self._store.mark(self.source, account, when or self._now(),
                             last_upload_at, last_seen_track_id)
        except Exception as exc:
            logging.warning('Could not record the check of %s/%s: %s', self.source, account, exc)
