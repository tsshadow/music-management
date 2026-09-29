"""What the bpm-analyzer container last said about itself, for music-manager's /health.

The worker (worker.py) runs in its own container and writes a small JSON status file into a
directory music-manager also mounts (`/app/data/bpm-analyzer/status.json` here). /health reports
it under `bpm_analysis`, and as a `bpm-analyzer` entry in `heartbeats` shaped like a loop's.

It is deliberately not one of `threads`: those decide /health's status code, which is also
music-manager's own container healthcheck, and another container being down must not make
music-manager itself look unhealthy (and get restarted for it). A missing file means the worker
is not deployed or has never run, which is reported as `null`, not as a failure.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

STATUS_PATH = Path(os.getenv('BPM_ANALYZER_STATUS', '/app/data/bpm-analyzer/status.json'))
#: The worker writes at least every few minutes (OFF_SECONDS / IDLE_SECONDS, or per batch).
STALE_AFTER_SECONDS = 1800.0


def read_status(path: Path | None = None, now: float | None = None) -> dict[str, Any] | None:
    """The status file (STATUS_PATH by default) with `age_seconds` and `stale` added, or None."""
    try:
        payload = json.loads(Path(STATUS_PATH if path is None else path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    now = time.time() if now is None else now
    try:
        age = max(0.0, now - float(payload.get('heartbeat_at')))
    except (TypeError, ValueError):
        age = None
    payload['age_seconds'] = None if age is None else round(age, 1)
    payload['stale'] = age is None or age > STALE_AFTER_SECONDS
    return payload


def heartbeat_entry(status: dict[str, Any] | None) -> dict[str, Any] | None:
    """The status in the shape of a `heartbeats` entry (thread_registry.thread_heartbeats)."""
    if status is None:
        return None
    return {
        'alive': not status['stale'],
        'stale': status['stale'],
        'last_tick_age_seconds': status['age_seconds'],
        'stale_after_seconds': STALE_AFTER_SECONDS,
        'ticks': status.get('analyzed', 0),
        'failures': status.get('failed', 0),
    }
