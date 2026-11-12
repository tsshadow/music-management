"""One JSON line per request to syslog (``LOG_AUTH``, tag ``muma-ro``). The output is never logged.

journald keeps the line, and the ``muma-ro`` account cannot change it. The command is cut at 512
characters and masked, so a ``token=...`` the agent typed does not end up in the log.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass

from tools.muma_mcp.redact import redact

MAX_COMMAND_CHARS = 512
FIELDS = ('ts', 'key', 'client', 'class', 'argv0', 'command', 'decision', 'reason', 'exit', 'bytes', 'ms')


@dataclass(frozen=True)
class Entry:  # pylint: disable=too-many-instance-attributes  # one per audit field
    """The facts of one request."""

    key: str
    client: str
    host_class: str
    argv0: str
    command: str
    decision: str  # 'allowed' or 'refused'
    reason: str | None
    exit_code: int
    output_bytes: int
    ms: int


def line(entry: Entry, now: float | None = None) -> str:
    """The JSON line for ``entry``, with the command cut and masked."""
    stamp = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() if now is None else now))
    values = {
        'ts': stamp,
        'key': entry.key,
        'client': entry.client,
        'class': entry.host_class,
        'argv0': entry.argv0,
        'command': redact(entry.command[:MAX_COMMAND_CHARS]),
        'decision': entry.decision,
        'reason': entry.reason,
        'exit': entry.exit_code,
        'bytes': entry.output_bytes,
        'ms': entry.ms,
    }
    return json.dumps(values, ensure_ascii=True)


def _syslog(text: str) -> None:
    """Write one line to syslog under LOG_AUTH. A host without syslog loses the line, not the command."""
    try:
        import syslog  # pylint: disable=import-outside-toplevel  # absent on some platforms

        syslog.openlog('muma-ro', syslog.LOG_PID, syslog.LOG_AUTH)
        syslog.syslog(syslog.LOG_INFO, text)
    except (ImportError, OSError):
        pass


def record(entry: Entry, sink: Callable[[str], None] = _syslog) -> str:
    """Log ``entry`` and return the line."""
    text = line(entry)
    sink(text)
    return text
