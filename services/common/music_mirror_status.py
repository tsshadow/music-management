"""The state of the music mirror, read from the status file its nightly job writes.

The job runs on the mirror NAS (``tools/music_mirror.py``) and writes ``latest.json`` into a
directory that production mounts read-only. Two readers decide what that file means:
``GET /health/music-mirror`` in music-manager and the daily check
``tools/music_mirror_check.py``. Both call :func:`evaluate`, so they cannot disagree.

Design: docs/designs/music-mirror/technical.md.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

STATUS_NAME = 'latest.json'
DEFAULT_STALE_AFTER_HOURS = 36

# Every status except OK makes the endpoint answer 503 and the check raise an alert.
OK = 'ok'
UNCONFIGURED = 'unconfigured'
MISSING = 'missing'
UNREADABLE = 'unreadable'
FAILED = 'failed'
REFUSED = 'refused'
STALE = 'stale'
DIFFERING = 'differing'


@dataclass(frozen=True)
class MirrorStatus:
    """The verdict on one status file: a status word, a reason and the fields worth showing."""

    status: str
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    # The differing file names. Kept out of the public answer, because the endpoint needs no key
    # and a library path says more about its owner than a count does; the daily check sends them.
    files: tuple[str, ...] = ()

    @property
    def healthy(self) -> bool:
        """True only for a recent, successful run whose sample matched."""
        return self.status == OK

    def as_dict(self) -> dict[str, Any]:
        """The response body of ``/health/music-mirror``."""
        return {'status': self.status, 'reason': self.reason, **self.details}


def stale_after_hours() -> int:
    """``MIRROR_STALE_AFTER_HOURS``, default 36: the age at which a good run counts as stale."""
    raw = os.getenv('MIRROR_STALE_AFTER_HOURS', '')
    try:
        return int(raw) if raw else DEFAULT_STALE_AFTER_HOURS
    except ValueError:
        return DEFAULT_STALE_AFTER_HOURS


def _details(payload: dict[str, Any], age_hours: float | None, limit_hours: int) -> dict[str, Any]:
    """The fields of a status file that a person reading the answer wants to see."""
    sample = payload.get('sample') or {}
    full = payload.get('full_checksum') or {}
    return {
        'run_id': payload.get('run_id'),
        'finished_at': payload.get('finished_at'),
        'age_hours': None if age_hours is None else round(age_hours, 1),
        'limit_hours': limit_hours,
        'files_total': payload.get('files_total'),
        'files_transferred': payload.get('files_transferred'),
        'bytes_transferred': payload.get('bytes_transferred'),
        'snapshot': payload.get('snapshot'),
        'sample_differing': len(sample.get('differing') or []),
        'orphans': payload.get('orphans'),
        # Without its list of names: the answer is public, see MirrorStatus.files.
        'full_checksum': {key: full.get(key) for key in ('at', 'differing_count')},
        'pool_used_percent': payload.get('pool_used_percent'),
    }


def evaluate(  # pylint: disable=too-many-return-statements,too-many-locals  # one return per status row
    directory: str | None, now: datetime | None = None, limit_hours: int | None = None
) -> MirrorStatus:
    """Read ``<directory>/latest.json`` and decide the mirror's status.

    The order matters: a failed or refused last run is reported as such even when it is
    recent, and a differing sample is worse news than an old run.
    """
    limit = stale_after_hours() if limit_hours is None else limit_hours
    if not directory:
        return MirrorStatus(UNCONFIGURED, 'MIRROR_STATUS_PATH is not set', {'limit_hours': limit})

    path = Path(directory) / STATUS_NAME
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(payload, dict):
            raise ValueError('not a JSON object')
        finished = datetime.fromisoformat(payload['finished_at'])
        if finished.tzinfo is None:
            raise ValueError('finished_at has no time zone')
    except FileNotFoundError:
        return MirrorStatus(MISSING, f'{path} does not exist', {'limit_hours': limit})
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return MirrorStatus(UNREADABLE, f'{path}: {exc}', {'limit_hours': limit})

    current = now or datetime.now(UTC)
    age_hours = (current - finished).total_seconds() / 3600
    details = _details(payload, age_hours, limit)

    result = payload.get('result')
    if result == FAILED:
        return MirrorStatus(FAILED, payload.get('reason') or 'the last run failed', details)
    if result == REFUSED:
        return MirrorStatus(REFUSED, payload.get('reason') or 'the last run was refused', details)
    if result != OK:
        return MirrorStatus(UNREADABLE, f'{path}: unknown result {result!r}', details)

    differing = (payload.get('sample') or {}).get('differing') or []
    if differing:
        names = tuple(str(name) for name in differing)
        return MirrorStatus(DIFFERING, f'{len(differing)} sampled file(s) differ', details, names)

    full = payload.get('full_checksum') or {}
    if full.get('differing_count'):
        names = tuple(str(name) for name in full.get('differing') or [])
        reason = f'the monthly checksum compare found {full["differing_count"]} differing file(s)'
        return MirrorStatus(DIFFERING, reason, details, names)

    if age_hours > limit:
        return MirrorStatus(STALE, f'the last good run finished {age_hours:.1f} h ago, limit {limit} h', details)

    return MirrorStatus(OK, None, details)
