#!/usr/bin/env python3
"""Daily check of the music mirror: turn its status file into events and alerts.

The mirror job runs on the mirror NAS, which has no database access, so it cannot write the
event log. This check runs on the production host (``muma-music-mirror-check.timer``), reads
the same ``latest.json`` that ``GET /health/music-mirror`` reads, and records what it finds:

- every unhealthy status: an ``ERROR`` row and a push to the alerts topic, the push first
  (``NtfySink`` is synchronous and needs no database), the row second;
- a good run that finished in the last 24 hours: one ``INFO`` row with the counts, no push.

It is also the check that fires when the job on the NAS did not run at all: the status then
goes stale. Design: docs/designs/music-mirror/technical.md.

Usage:
    python tools/music_mirror_check.py
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from services.common import music_mirror_status  # noqa: E402  # pylint: disable=wrong-import-position
from services.common.Helpers.EventService import (  # noqa: E402  # pylint: disable=wrong-import-position
    Event,
    event_service,
)
from services.common.Helpers.ntfy_sink import NtfySink  # noqa: E402  # pylint: disable=wrong-import-position

SOURCE = 'music-mirror'
LOGGER = 'music-mirror.check'
# A good run is reported once: the check runs daily, the mirror nightly.
REPORT_WINDOW_HOURS = 24


def _gigabytes(value: Any) -> str:
    """Bytes as gigabytes with one decimal, or a dash for a missing number."""
    return f'{value / 1e9:.1f} GB' if isinstance(value, int | float) else '-'


def summary(details: dict[str, Any]) -> str:
    """One line with the counts of a run, for the INFO event."""
    orphans = details.get('orphans') or {}
    return (
        f'{details.get("files_total")} files, {details.get("files_transferred")} copied '
        f'({_gigabytes(details.get("bytes_transferred"))}), snapshot {details.get("snapshot")}, '
        f'pool {details.get("pool_used_percent")}% used, '
        f'{orphans.get("files", "-")} files only on the mirror ({_gigabytes(orphans.get("bytes"))})'
    )


def alert(title: str, message: str) -> None:
    """Push first, record second, as ``tools/db_backup.py`` does."""
    event = Event(level='ERROR', title=title, message=message, source=SOURCE, logger=LOGGER, push=True)
    try:
        NtfySink().handle(event)
    except Exception as exc:  # noqa: BLE001 - the row must still be tried
        print(f'music_mirror_check: pushing the alert failed: {exc}', file=sys.stderr)
    try:
        event_service.record_now(event)
    except Exception as exc:  # noqa: BLE001 - defensive, the push already went
        print(f'music_mirror_check: recording the alert failed: {exc}', file=sys.stderr)


def run(directory: str | None, now: datetime | None = None) -> int:
    """Check once. Returns 0 for a healthy mirror and 1 otherwise, for the systemd unit."""
    current = now or datetime.now(UTC)
    verdict = music_mirror_status.evaluate(directory, now=current)
    if not verdict.healthy:
        title = f'Music mirror {verdict.status}'
        message = verdict.reason or verdict.status
        if verdict.files:
            message += ': ' + ', '.join(verdict.files[:10])
        alert(title, message)
        print(f'music_mirror_check: {title}: {verdict.reason}', file=sys.stderr)
        return 1

    age = verdict.details.get('age_hours')
    if isinstance(age, int | float) and age <= REPORT_WINDOW_HOURS:
        message = summary(verdict.details)
        event_service.record_now(
            Event(level='INFO', title='Music mirror ok', message=message, source=SOURCE, logger=LOGGER, push=False)
        )
        print(f'music_mirror_check: ok: {message}')
    return 0


def main() -> int:
    """Entry point of the systemd unit."""
    return run(os.getenv('MIRROR_STATUS_PATH'))


if __name__ == '__main__':
    sys.exit(main())
