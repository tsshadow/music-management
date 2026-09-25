"""Insert the listens LMS recorded but never relayed to muma (bug report 075).

LMS relays every listen to `POST /api/scrobble/event` through an in-memory queue with two
back-to-back retries, drops anything that is not a 200 and forgets the queue on a restart. Every
music-manager outage -- each deploy -- therefore loses the listens made during it. LMS's own
`listen` table keeps them, so rather than making LMS's relay durable, muma pulls: this loop runs
the reconcile's classification (`scrobble_reconcile.backfill`) over a bounded recent window every
few minutes and inserts the `insertable` LMS-only listens under source `lms-backfill`, with LMS's
start time, where the `(username, listened_at, track_id)` key makes a repeat a no-op.

It never applies `shifted`: restoring times moved by bug 039 stays a manual, admin-triggered
repair (`POST /api/scrobble/reconcile/lms`), as does inserting the historical backlog older than
the window.

Settings (Beheer > Config, group "Scrobbling"), read again every round so a change takes effect
without a restart:

- `lms_listen_backfill_enabled` -- the on/off switch, on by default.
- `lms_listen_backfill_interval_minutes` -- time between rounds, 15 by default.
- `lms_listen_backfill_window_hours` -- how far back LMS's listens are read, 48 by default.

Logging: one INFO line per round that inserted something, DEBUG otherwise. A failing round is a
single WARNING for the whole run of failures, not one per round -- an unreachable LMS file or a
zone mismatch would otherwise page the alerts topic every quarter of an hour.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from services.common.config_store import ConfigStore
from services.music_manager import scrobble_reconcile
from services.music_manager.database import get_db_connection
from services.music_manager.thread_registry import default_stale_after, run_forever

logger = logging.getLogger('music-manager.lms-listen-backfill')

#: The name under which the loop appears in `/health` `threads`.
THREAD_NAME = 'lms-listen-backfill'
DEFAULT_INTERVAL_MINUTES = 15
DEFAULT_WINDOW_HOURS = 48
#: A listen LMS recorded less than this long ago is left alone for now: its own relay, or the
#: app's own scrobble about a minute after the start, may still be on its way, and inserting it
#: first would race them. The next round after this has passed picks it up.
SETTLE_SECONDS = 1800
#: `/health` counts the loop stuck when no round completed within this long. Generous, because the
#: interval can be raised on the config page after the thread has registered its heartbeat.
STALE_AFTER_SECONDS = default_stale_after(24 * 3600)

#: Set to end the loop; the tests use it, the process never needs to.
stop_event = threading.Event()

#: Whether the previous round failed, so a run of failures warns once.
_state: dict[str, bool] = {'failing': False}


def _positive_int(value: Any, default: int) -> int:
    """`value` as a positive integer, or `default` when it is missing, unparsable or not positive."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _enabled(value: Any) -> bool:
    """The switch's value as a bool; strings from the environment read as a boolean would."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() not in ('0', 'false', 'no', 'off', '')
    return bool(value)


def settings_snapshot(settings: Any = None) -> dict[str, Any]:
    """The three settings, validated, as this round will use them."""
    settings = settings if settings is not None else ConfigStore()
    return {
        'enabled': _enabled(settings.get('lms_listen_backfill_enabled')),
        'interval_seconds': 60
        * _positive_int(settings.get('lms_listen_backfill_interval_minutes'), DEFAULT_INTERVAL_MINUTES),
        'window_seconds': 3600 * _positive_int(settings.get('lms_listen_backfill_window_hours'), DEFAULT_WINDOW_HOURS),
    }


def _open_servers() -> list:
    """Every LMS database this process can see, opened read-only (possibly none)."""
    from services.music_manager.routers.users import lms_db_targets

    return scrobble_reconcile.open_servers(lms_db_targets())


def run_once(now: int, window_seconds: int, servers_factory: Callable[[], list] | None = None) -> dict | None:
    """One backfill over `[now - window_seconds, now - SETTLE_SECONDS]`; None when there is no LMS database."""
    servers = (servers_factory or _open_servers)()
    if not servers:
        return None
    try:
        conn = get_db_connection()
        if not conn:
            raise RuntimeError('Database connection failed')
        try:
            return scrobble_reconcile.backfill(conn, servers, since=now - window_seconds, until=now - SETTLE_SECONDS)
        finally:
            conn.close()
    finally:
        for server_conn, _ in servers:
            with contextlib.suppress(Exception):
                server_conn.close()


def _report(result: dict | None) -> None:
    """One INFO line when the round inserted something, DEBUG otherwise."""
    if result is None:
        logger.debug('%s: no LMS database visible, nothing to backfill', THREAD_NAME)
        return
    written = result['written']
    if written['lms_only_inserted']:
        per_user = ', '.join(f"{user} {totals['lms_only_inserted']}" for user, totals in result['users'].items())
        logger.info(
            '%s: inserted %d listens LMS recorded but never relayed (%s; %d already present) since %s',
            THREAD_NAME,
            written['lms_only_inserted'],
            per_user,
            written['collisions'],
            result['since'],
        )
    else:
        logger.debug(
            '%s: nothing to insert since %s (%d LMS-only, %d insertable, %d already present)',
            THREAD_NAME,
            result['since'],
            result['found']['lms_only'],
            result['found']['lms_only_insertable'],
            written['collisions'],
        )


def backfill_tick(settings: Any = None, clock: Callable[[], float] = time.time) -> float:
    """One round of the loop; returns the seconds until the next one. Never raises.

    A failure is caught here rather than left to `run_forever`, which would log every failed
    round at ERROR: this loop warns once per run of failures and keeps its heartbeat, since a
    missing LMS file is not a reason to mark the whole service unhealthy.
    """
    config = settings_snapshot(settings)
    if not config['enabled']:
        logger.debug('%s: switched off on the config page', THREAD_NAME)
        return config['interval_seconds']
    try:
        result = run_once(int(clock()), config['window_seconds'])
    except Exception as exc:  # pylint: disable=broad-except  # one round must not end the loop
        if not _state['failing']:
            logger.warning('%s: a round failed, retrying every %ds: %s', THREAD_NAME, config['interval_seconds'], exc)
        else:
            logger.debug('%s: still failing: %s', THREAD_NAME, exc)
        _state['failing'] = True
        return config['interval_seconds']
    if _state['failing']:
        logger.debug('%s: recovered', THREAD_NAME)
    _state['failing'] = False
    _report(result)
    return config['interval_seconds']


def run_lms_listen_backfill() -> None:
    """The `lms-listen-backfill` thread: a round on start, then every configured interval."""
    run_forever(
        THREAD_NAME,
        backfill_tick,
        DEFAULT_INTERVAL_MINUTES * 60,
        stale_after=STALE_AFTER_SECONDS,
        stop=stop_event,
    )
