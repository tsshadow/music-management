"""Run one fixed argument list: no shell, no stdin, a small environment, a time limit, an output cap.

Every process starts in its own session, so a timeout kills the whole group, not only the first
process. The output is decoded, cut at 1 MiB, stripped of the lines a verb drops, and masked when
the verb's output can hold a secret (logs and the Proxmox config).
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from tools.muma_mcp.redact import redact
from tools.muma_ro.verbs import Plan

MAX_OUTPUT_BYTES = 1024 * 1024
TIMEOUT_EXIT = 124
NOT_STARTED_EXIT = 127
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C.UTF-8'}
SUDO = '/usr/bin/sudo'
HELPER = '/usr/local/libexec/muma-ro-priv'

Popen = Callable[..., Any]


@dataclass(frozen=True)
class Result:
    """What a command wrote and how it ended."""

    exit_code: int
    stdout: str
    stderr: str


def _cap(data: bytes) -> str:
    """Decode, and cut at MAX_OUTPUT_BYTES with a last line that says so."""
    if len(data) > MAX_OUTPUT_BYTES:
        text = data[:MAX_OUTPUT_BYTES].decode('utf-8', errors='replace')
        return text.rstrip('\n') + '\nmuma-ro: output cut at 1 MiB\n'
    return data.decode('utf-8', errors='replace')


def execute(argv: Sequence[str], timeout: int, popen: Popen = subprocess.Popen) -> Result:
    """Start ``argv`` without a shell and wait at most ``timeout`` seconds.

    On a timeout the process group is killed and the output so far comes back with exit 124.
    """
    try:
        proc = popen(
            list(argv),
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(ENV),
            start_new_session=True,
            close_fds=True,
        )
    except OSError as exc:
        return Result(NOT_STARTED_EXIT, '', f'muma-ro: cannot start {argv[0]}: {exc.strerror}\n')
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        out, err = proc.communicate()
        note = f'muma-ro: timed out after {timeout} s\n'
        return Result(TIMEOUT_EXIT, _cap(out or b''), _cap(err or b'') + note)
    return Result(proc.returncode, _cap(out or b''), _cap(err or b''))


def finish(plan: Plan, result: Result) -> Result:
    """Drop the lines the verb drops, and mask the output of a verb whose output can hold a secret."""
    stdout, stderr = result.stdout, result.stderr
    if plan.drop_prefixes:
        kept = [line for line in stdout.splitlines(keepends=True) if not line.lstrip().startswith(plan.drop_prefixes)]
        stdout = ''.join(kept)
    if plan.redact:
        stdout, stderr = redact(stdout), redact(stderr)
    return Result(result.exit_code, stdout, stderr)


def run_plan(plan: Plan, popen: Popen = subprocess.Popen) -> Result:
    """Run the plan's own argument list and process its output."""
    return finish(plan, execute(plan.argv, plan.timeout, popen))


def run_through_helper(key: str, command: str, timeout: int, popen: Popen = subprocess.Popen) -> Result:
    """Hand the original string to the root helper, which parses it again before it runs anything."""
    argv = (SUDO, '-n', HELPER, '--key', key, '--command', command)
    return execute(argv, timeout + 5, popen)
