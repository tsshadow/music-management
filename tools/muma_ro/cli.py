"""The two entry points: ``muma-ro`` (the forced command) and ``muma-ro-priv`` (the root helper).

``muma-ro --key NAME`` reads the agent's text from ``SSH_ORIGINAL_COMMAND``; ``--command`` takes its
place for the Proxmox relay. ``muma-ro-priv --key NAME --command TEXT`` runs only as root, through
``sudo``, parses the text again against the same root-owned policy, and runs only privileged verbs.
Neither takes a policy path: the policy is always ``/etc/muma-ro/policy.json``.
"""

from __future__ import annotations

import argparse
import io
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TextIO

from tools.muma_ro import audit, run
from tools.muma_ro.parse import Refused, tokenize
from tools.muma_ro.policy import Policy, PolicyError, load
from tools.muma_ro.verbs import Context, Plan, build

REFUSED_EXIT = 2
_KEY = re.compile(r'^[A-Za-z0-9_.-]{1,64}$')


@dataclass
class Runtime:
    """What a request depends on outside the text, so a test can replace each part."""

    load_policy: Callable[[], Policy] = load
    popen: run.Popen = subprocess.Popen
    sink: Callable[[str], None] = audit._syslog  # pylint: disable=protected-access  # the default sink
    is_root: Callable[[], bool] = field(default=lambda: os.geteuid() == 0)


def _client() -> str:
    """The address of the SSH client, or ``local``."""
    connection = os.environ.get('SSH_CONNECTION', '').split()
    return connection[0] if connection else 'local'


def serve(  # pylint: disable=too-many-arguments,too-many-locals  # one request, start to end
    command: str,
    key: str,
    *,
    helper: bool,
    out: TextIO,
    err: TextIO,
    runtime: Runtime | None = None,
) -> int:
    """Check one command, run it, write its output, log one line, and return the exit code."""
    rt = runtime or Runtime()
    started = time.monotonic()
    host_class, argv0 = '?', ''

    def finish(decision: str, reason: str | None, code: int, size: int) -> int:
        ms = int((time.monotonic() - started) * 1000)
        audit.record(audit.Entry(key, _client(), host_class, argv0, command, decision, reason, code, size, ms), rt.sink)
        return code

    try:
        policy = rt.load_policy()
        host_class = policy.host_class
        tokens = tokenize(command)
        argv0 = tokens[0].text[:32]
        plan: Plan = build(tokens, Context(policy, key, command))
        if helper and not plan.privileged:
            raise Refused('the helper runs only verbs that need root')
    except (Refused, PolicyError) as exc:
        reason = f'policy: {exc}' if isinstance(exc, PolicyError) else str(exc)
        err.write(f'muma-ro: refused: {reason}\n')
        return finish('refused', reason, REFUSED_EXIT, 0)

    argv0 = plan.verb
    if plan.text is not None:
        out.write(plan.text)
        return finish('allowed', None, 0, len(plan.text))
    if plan.privileged and not rt.is_root():
        result = run.run_through_helper(key, command, plan.timeout, rt.popen)
    else:
        result = run.run_plan(plan, rt.popen)
    out.write(result.stdout)
    err.write(result.stderr)
    return finish('allowed', None, result.exit_code, len(result.stdout.encode('utf-8')))


# --- self-test -----------------------------------------------------------------------------------

MUST_REFUSE = (
    '',
    'sh',
    'bash -c id',
    'python3',
    'rm -rf /tmp/x',
    'cat /etc/shadow',
    'ls /etc',
    'ls /tmp;id',
    'ls /tmp|id',
    'ls /tmp && id',
    'ls $(id)',
    'ls `id`',
    'ls /tmp > /tmp/x',
    'ls < /etc/passwd',
    'ls "/tmp"',
    'ls \\tmp',
    'ls /tmp\nid',
    'ls /tmp\x00',
    'ls ../..',
    'docker run alpine',
    'docker exec x sh',
    'docker logs -f x',
    'find /tmp -exec id',
    'find /tmp -delete',
    'zfs destroy x',
    'pct set 100',
    'pvesh get /nodes',
    'a' * 4097,
)


def self_test_commands(policy: Policy) -> list[str]:
    """One harmless command per enabled verb, with the policy's own first values as arguments."""
    first_root = policy.roots[0].path if policy.roots else None
    container = sorted(policy.containers)[0] if policy.containers else None
    unit = sorted(policy.units)[0] if policy.units else None
    ctid = sorted(policy.ctids)[0] if policy.ctids else None
    candidates = {
        'help': 'help',
        'ls': f"ls '{first_root}'" if first_root else None,
        'stat': f"stat '{first_root}'" if first_root else None,
        'find': f"find '{first_root}' -maxdepth 1 -type d" if first_root else None,
        'df': 'df -h',
        'free': 'free -m',
        'uptime': 'uptime',
        'getfacl': f"getfacl '{first_root}'" if first_root else None,
        'docker-ps': 'docker ps',
        'docker-logs': f'docker logs --tail 1 {container}' if container else None,
        'docker-inspect': f'docker inspect {container}' if container else None,
        'docker-system-df': 'docker system df',
        'systemctl-status': f'systemctl status {unit}' if unit else None,
        'systemctl-timers': 'systemctl list-timers',
        'journalctl': f'journalctl -u {unit} -n 1' if unit else None,
        'zfs-list': 'zfs list',
        'zpool-status': 'zpool status -x',
        'zpool-list': 'zpool list',
        'pct-list': 'pct list',
        'qm-list': 'qm list',
        'pvesm-status': 'pvesm status',
        'pct-config': f'pct config {ctid}' if ctid else None,
    }
    return [cmd for verb, cmd in candidates.items() if cmd and verb in policy.verbs]


def self_test(key: str, out: TextIO, runtime: Runtime | None = None) -> int:
    """Run every allowed command (must not be refused) and every refused one (must exit 2)."""
    rt = runtime or Runtime()
    try:
        policy = rt.load_policy()
    except PolicyError as exc:
        out.write(f'FAIL policy: {exc}\n')
        return 1
    failures = 0
    for command in self_test_commands(policy):
        sink_out, sink_err = io.StringIO(), io.StringIO()
        code = serve(command, key, helper=False, out=sink_out, err=sink_err, runtime=rt)
        # A refusal, a timeout, a missing tool or a sudo that asks for a password is a broken
        # install. Any other exit code is the tool's own answer (ls exits 2 for a missing path).
        ok = code not in (run.TIMEOUT_EXIT, run.NOT_STARTED_EXIT) and not re.search(
            r'^muma-ro: refused|^sudo:', sink_err.getvalue(), re.M
        )
        failures += not ok
        out.write(f'{"ok  " if ok else "FAIL"} allowed  {command} (exit {code})\n')
    for command in MUST_REFUSE:
        sink_out, sink_err = io.StringIO(), io.StringIO()
        code = serve(command, key, helper=False, out=sink_out, err=sink_err, runtime=rt)
        ok = code == REFUSED_EXIT and sink_err.getvalue().startswith('muma-ro: refused:')
        failures += not ok
        out.write(f'{"ok  " if ok else "FAIL"} refused  {command[:40]!r} (exit {code})\n')
    out.write(f'{failures} failure(s)\n')
    return 1 if failures else 0


# --- entry points --------------------------------------------------------------------------------


def _key(value: str) -> str:
    if not _KEY.match(value):
        raise argparse.ArgumentTypeError('a key name is letters, digits, _, . and -')
    return value


def main(argv: Sequence[str] | None = None, runtime: Runtime | None = None) -> int:
    """``muma-ro --key NAME [--command TEXT] [--self-test]``."""
    parser = argparse.ArgumentParser(prog='muma-ro', description='Read-only command wrapper.')
    parser.add_argument('--key', type=_key, required=True)
    parser.add_argument('--command')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test(args.key, sys.stdout, runtime)
    command = args.command if args.command is not None else os.environ.get('SSH_ORIGINAL_COMMAND', '')
    return serve(command, args.key, helper=False, out=sys.stdout, err=sys.stderr, runtime=runtime)


def main_priv(argv: Sequence[str] | None = None, runtime: Runtime | None = None) -> int:
    """``muma-ro-priv --key NAME --command TEXT``, as root through sudo."""
    parser = argparse.ArgumentParser(prog='muma-ro-priv', description='Root helper of muma-ro.')
    parser.add_argument('--key', type=_key, required=True)
    parser.add_argument('--command', required=True)
    args = parser.parse_args(argv)
    rt = runtime or Runtime()
    if not rt.is_root():
        sys.stderr.write('muma-ro: refused: the helper must run as root\n')
        return REFUSED_EXIT
    return serve(args.command, args.key, helper=True, out=sys.stdout, err=sys.stderr, runtime=rt)
