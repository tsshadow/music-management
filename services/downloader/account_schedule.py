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
    from services.downloader.deep_sweep import AccountSnapshot
    from services.downloader.timing import DownloaderTiming

SECONDS_PER_DAY = 86400

# The tier boundaries, in days since the account's newest known upload. Week,
# month, quarter and year are calendar-meaningful and deliberately not settings;
# what an operator tunes is the cooldown each tier gets.
FRESH_DAYS = 7
RECENT_DAYS = 30
MONTHLY_DAYS = 90
OCCASIONAL_DAYS = 365


def cooldown_for(last_upload_at: datetime | None, now: datetime, timing: DownloaderTiming) -> int:
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
    last_deep_sweep_at: datetime | None = None
    # How complete the account was at the end of its last deep pass; None until
    # one has run. Written only by the deep pass, kept by everything else.
    snapshot: AccountSnapshot | None = None


def due_accounts(
    accounts: Iterable[str],
    checks: Mapping[str, AccountCheck],
    cooldown: int,
    now: datetime,
    cooldown_for_account: Callable[[AccountCheck | None], int] | None = None,
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

    def mark(
        self,
        source: str,
        account: str,
        when: datetime,
        last_upload_at: datetime | None = None,
        last_seen_track_id: str | None = None,
        last_deep_sweep_at: datetime | None = None,
    ) -> None:
        rows = self._rows.setdefault(source, {})
        previous = rows.get(account)
        rows[account] = AccountCheck(
            last_checked_at=when,
            last_upload_at=_kept(last_upload_at, previous, 'last_upload_at'),
            last_seen_track_id=_kept(last_seen_track_id, previous, 'last_seen_track_id'),
            last_deep_sweep_at=_kept(last_deep_sweep_at, previous, 'last_deep_sweep_at'),
            snapshot=previous.snapshot if previous else None,
        )

    def mark_deep(self, source: str, account: str, when: datetime) -> None:
        rows = self._rows.setdefault(source, {})
        previous = rows.get(account)
        rows[account] = AccountCheck(
            last_checked_at=previous.last_checked_at if previous else when,
            last_upload_at=previous.last_upload_at if previous else None,
            last_seen_track_id=previous.last_seen_track_id if previous else None,
            last_deep_sweep_at=when,
            snapshot=previous.snapshot if previous else None,
        )

    def mark_snapshot(self, source: str, account: str, snapshot: AccountSnapshot) -> None:
        rows = self._rows.setdefault(source, {})
        previous = rows.get(account)
        rows[account] = AccountCheck(
            last_checked_at=previous.last_checked_at if previous else snapshot.taken_at,
            last_upload_at=previous.last_upload_at if previous else None,
            last_seen_track_id=previous.last_seen_track_id if previous else None,
            last_deep_sweep_at=previous.last_deep_sweep_at if previous else None,
            snapshot=snapshot,
        )


def _kept(new_value, previous: AccountCheck | None, attribute: str):
    """The new value, or what was already stored when there is no new one.

    Mirrors the ``COALESCE`` in the database store: an ordinary check knows only
    the time, and must not wipe a date the account had already earned.
    """
    if new_value is not None:
        return new_value
    return getattr(previous, attribute) if previous is not None else None


def _snapshot_from_row(values) -> AccountSnapshot | None:
    """The stored snapshot, or None for a row that predates the count."""
    from services.downloader.deep_sweep import AccountSnapshot

    listed, held, excluded, remaining, state, taken_at = values
    if listed is None or taken_at is None:
        return None
    return AccountSnapshot(
        listed=int(listed),
        held=int(held or 0),
        excluded=int(excluded or 0),
        remaining=int(remaining or 0),
        state=str(state or ''),
        taken_at=taken_at,
    )


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
                    'SELECT account, last_checked_at, last_upload_at, last_seen_track_id, '
                    '       last_deep_sweep_at, snapshot_listed, snapshot_held, snapshot_excluded, '
                    '       snapshot_remaining, snapshot_state, snapshot_at '
                    'FROM downloads_account_checks WHERE source = %s',
                    (source,),
                )
                return {
                    row[0]: AccountCheck(row[1], row[2], row[3], row[4], snapshot=_snapshot_from_row(row[5:]))
                    for row in cursor.fetchall()
                }
        finally:
            connection.close()

    def mark(
        self,
        source: str,
        account: str,
        when: datetime,
        last_upload_at: datetime | None = None,
        last_seen_track_id: str | None = None,
        last_deep_sweep_at: datetime | None = None,
    ) -> None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                # COALESCE, not a plain assignment: an ordinary check passes NULL
                # for the two upload columns and must leave them as they were.
                cursor.execute(
                    'INSERT INTO downloads_account_checks '
                    '(source, account, last_checked_at, last_upload_at, last_seen_track_id, '
                    ' last_deep_sweep_at) '
                    'VALUES (%s, %s, %s, %s, %s, %s) '
                    'ON DUPLICATE KEY UPDATE '
                    '  last_checked_at = VALUES(last_checked_at), '
                    '  last_upload_at = COALESCE(VALUES(last_upload_at), last_upload_at), '
                    '  last_seen_track_id = COALESCE(VALUES(last_seen_track_id), last_seen_track_id), '
                    '  last_deep_sweep_at = COALESCE(VALUES(last_deep_sweep_at), last_deep_sweep_at)',
                    (source, account, when, last_upload_at, last_seen_track_id, last_deep_sweep_at),
                )
            connection.commit()
        finally:
            connection.close()

    def mark_deep(self, source: str, account: str, when: datetime) -> None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                # last_checked_at is NOT NULL, so a row that does not exist yet is
                # created carrying the same timestamp; an existing row keeps the
                # check time it already had.
                cursor.execute(
                    'INSERT INTO downloads_account_checks '
                    '(source, account, last_checked_at, last_deep_sweep_at) '
                    'VALUES (%s, %s, %s, %s) '
                    'ON DUPLICATE KEY UPDATE '
                    '  last_deep_sweep_at = VALUES(last_deep_sweep_at)',
                    (source, account, when, when),
                )
            connection.commit()
        finally:
            connection.close()

    def mark_snapshot(self, source: str, account: str, snapshot: AccountSnapshot) -> None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                # The six snapshot columns move together and nothing else does: the
                # check time, the upload date and the deep-sweep date belong to the
                # sweep that is running, not to the count it produced.
                cursor.execute(
                    'INSERT INTO downloads_account_checks '
                    '(source, account, last_checked_at, snapshot_listed, snapshot_held, snapshot_excluded, '
                    ' snapshot_remaining, snapshot_state, snapshot_at) '
                    'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) '
                    'ON DUPLICATE KEY UPDATE '
                    '  snapshot_listed = VALUES(snapshot_listed), '
                    '  snapshot_held = VALUES(snapshot_held), '
                    '  snapshot_excluded = VALUES(snapshot_excluded), '
                    '  snapshot_remaining = VALUES(snapshot_remaining), '
                    '  snapshot_state = VALUES(snapshot_state), '
                    '  snapshot_at = VALUES(snapshot_at)',
                    (
                        source,
                        account,
                        snapshot.taken_at,
                        snapshot.listed,
                        snapshot.held,
                        snapshot.excluded,
                        snapshot.remaining,
                        snapshot.state,
                        snapshot.taken_at,
                    ),
                )
            connection.commit()
        finally:
            connection.close()


class AccountSchedule:
    """Decides which accounts of one source are due for a check.

    A store that cannot be read is treated as "nothing was ever checked", which
    keeps the downloader working when the database is briefly unavailable.
    """

    def __init__(self, source: str, store=None, now: Callable[[], datetime] = datetime.now) -> None:
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
        """The accounts whose own tier cooldown has passed, most overdue first.

        Overdue-ness is measured against each account's own tier, so a dormant
        account is not permanently last merely for having a long cooldown. It
        also means a sweep cut short by `burst_size` or a 403 leaves behind the
        accounts that have waited least, rather than the same tail every time.
        """
        now = self._now()
        checks = self._checks()

        def wait_for(record: AccountCheck | None) -> int:
            return cooldown_for(record.last_upload_at if record else None, now, timing)

        ready = due_accounts(accounts, checks, timing.account_cooldown, now, cooldown_for_account=wait_for)

        def overdue_by(account: str) -> float:
            record = checks.get(account)
            if record is None:
                return float('inf')
            waited = (now - record.last_checked_at).total_seconds()
            return waited - wait_for(record)

        return sorted(ready, key=overdue_by, reverse=True)

    def deep_due(self, account: str, deep_sweep_days: int) -> bool:
        """Whether this account is due a full listing rather than a probe.

        Zero turns the deep sweep off. An account that has never had one is due
        immediately, which is what backfills the ledger for the accounts that
        exist today.
        """
        if deep_sweep_days <= 0:
            return False
        record = self._checks().get(account)
        if record is None or record.last_deep_sweep_at is None:
            return True
        age_days = (self._now() - record.last_deep_sweep_at).total_seconds() / SECONDS_PER_DAY
        return age_days >= deep_sweep_days

    def mark_deep_swept(self, account: str, when: datetime | None = None) -> None:
        try:
            self._store.mark_deep(self.source, account, when or self._now())
        except Exception as exc:
            logging.warning('Could not record the deep sweep of %s/%s: %s', self.source, account, exc)

    def record_snapshot(self, account: str, snapshot: AccountSnapshot) -> None:
        """Store how complete the account is; a store that is down loses one count, not the sweep."""
        try:
            self._store.mark_snapshot(self.source, account, snapshot)
        except Exception as exc:
            logging.warning('Could not record the snapshot of %s/%s: %s', self.source, account, exc)

    def mark_checked(
        self,
        account: str,
        when: datetime | None = None,
        last_upload_at: datetime | None = None,
        last_seen_track_id: str | None = None,
    ) -> None:
        try:
            self._store.mark(self.source, account, when or self._now(), last_upload_at, last_seen_track_id)
        except Exception as exc:
            logging.warning('Could not record the check of %s/%s: %s', self.source, account, exc)
