"""Read-only access to the homelab hosts: ``muma-ro`` over SSH, and three read-only HTTP tokens.

Each host runs ``muma-ro`` as the forced command of a key that belongs to this client (issue #176,
docs/designs/claude-readonly-access/technical.md). This module builds the command string from typed
arguments, checks its characters with the wrapper's own parser so a refusal comes back before a
connection is made, and runs ``ssh`` with a fixed set of options. The host decides what runs.

Portainer, GitLab and the Proxmox API get no wrapper: their tokens are read-only by the service's
own rights, and ``api_get`` adds a GET-only, prefix-allowlisted path on top.

Every setting is optional. A host or a token that is not configured makes its tools answer with
the name of the missing variable; the six production tools keep working.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import requests

from tools.muma_mcp.config import config_path, parse_env_file
from tools.muma_mcp.redact import redact
from tools.muma_ro.parse import Refused, check_characters

SSH = '/usr/bin/ssh'
SSH_TIMEOUT_SECONDS = 60
HTTP_TIMEOUT_SECONDS = 15
MAX_OUTPUT_CHARS = 200_000
HOST_CLASSES = ('prod', 'devvm', 'runner', 'nas', 'proxmox')
_TARGET = re.compile(r'^[a-z_][a-z0-9_-]{0,31}@[A-Za-z0-9.-]+$')
_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.@:-]{0,127}$')

# GET only, and only below these prefixes (the design's allowlist).
PORTAINER_PREFIXES = ('/api/endpoints', '/api/stacks')
GITLAB_PATTERNS = (
    re.compile(r'^/projects/[^/]+/(pipelines|jobs|merge_requests|issues)(/|\?|$)'),
    re.compile(r'^/runners(/|\?|$)'),
)
PVE_PREFIXES = ('/nodes', '/cluster/resources', '/cluster/backup', '/cluster/status', '/version')


class HostError(RuntimeError):
    """A host or token is not configured, a path is outside the allowlist, or a call failed."""


@dataclass(frozen=True)
class HostsConfig:  # pylint: disable=too-many-instance-attributes  # one per setting
    """The optional settings for the host tools, resolved once at startup."""

    key_dir: str = '~/.ssh'
    known_hosts: str = '~/.config/muma-mcp/known_hosts'
    hosts: dict[str, str] = field(default_factory=dict)
    portainer_url: str = ''
    portainer_token: str = ''
    gitlab_url: str = ''
    gitlab_token: str = ''
    pve_url: str = ''
    pve_token: str = ''

    @property
    def secrets(self) -> tuple[str, ...]:
        """The token values, masked by exact match in every answer."""
        return tuple(t for t in (self.portainer_token, self.gitlab_token, self.pve_token) if t)


def parse_hosts(raw: str) -> dict[str, str]:
    """``prod=muma-ro@prod.example.com,nas=...`` to a mapping; refuses an unknown class or target."""
    hosts: dict[str, str] = {}
    for part in filter(None, (p.strip() for p in raw.split(','))):
        host_class, sep, target = part.partition('=')
        host_class, target = host_class.strip(), target.strip()
        if not sep or host_class not in HOST_CLASSES or not _TARGET.match(target):
            raise HostError(f'MUMA_RO_HOSTS: {part!r} is not class=user@host with a class from {HOST_CLASSES}')
        hosts[host_class] = target
    return hosts


def load(environ: dict[str, str] | None = None) -> HostsConfig:
    """Read the same env file as config.py; the environment wins. Nothing here is required."""
    env = dict(os.environ if environ is None else environ)
    path = config_path()
    if path.is_file():
        for key, value in parse_env_file(path.read_text(encoding='utf-8')).items():
            env.setdefault(key, value)
    return HostsConfig(
        key_dir=env.get('MUMA_RO_SSH_KEY_DIR') or '~/.ssh',
        known_hosts=str(path.parent / 'known_hosts'),
        hosts=parse_hosts(env.get('MUMA_RO_HOSTS', '')),
        portainer_url=env.get('MUMA_PORTAINER_URL', '').rstrip('/'),
        portainer_token=env.get('MUMA_PORTAINER_RO_TOKEN', ''),
        gitlab_url=env.get('MUMA_GITLAB_URL', '').rstrip('/'),
        gitlab_token=env.get('MUMA_GITLAB_RO_TOKEN', ''),
        pve_url=env.get('MUMA_PVE_URL', '').rstrip('/'),
        pve_token=env.get('MUMA_PVE_RO_TOKEN', ''),
    )


# --- SSH -----------------------------------------------------------------------------------------


def ssh_argv(config: HostsConfig, host: str, command: str) -> list[str]:
    """The fixed ``ssh`` argument list for one command on ``host``."""
    target = config.hosts.get(host)
    if not target:
        raise HostError(f'host {host!r} is not configured; set it in MUMA_RO_HOSTS')
    key = os.path.join(os.path.expanduser(config.key_dir), f'muma-ro-{host}_ed25519')
    return [
        SSH,
        '-i',
        key,
        '-o',
        'BatchMode=yes',
        '-o',
        'IdentitiesOnly=yes',
        '-o',
        'StrictHostKeyChecking=yes',
        '-o',
        f'UserKnownHostsFile={os.path.expanduser(config.known_hosts)}',
        '-o',
        'ConnectTimeout=10',
        '-T',
        target,
        '--',
        command,
    ]


def run_on(config: HostsConfig, host: str, command: str, runner: Callable[..., Any] = subprocess.run) -> str:
    """Check ``command`` like the host would, run it over SSH and return the masked answer."""
    try:
        check_characters(command)
    except Refused as exc:
        return f'refused before connecting: {exc}'
    argv = ssh_argv(config, host, command)
    try:
        done = runner(
            argv, shell=False, stdin=subprocess.DEVNULL, capture_output=True, timeout=SSH_TIMEOUT_SECONDS, check=False
        )
    except subprocess.TimeoutExpired:
        return f'no answer from {host} within {SSH_TIMEOUT_SECONDS} s'
    out = (done.stdout or b'').decode('utf-8', errors='replace')
    err = (done.stderr or b'').decode('utf-8', errors='replace')
    text = out + (f'\n[stderr]\n{err}' if err.strip() else '') + f'\n[exit {done.returncode}]'
    if len(text) > MAX_OUTPUT_CHARS:
        text = text[:MAX_OUTPUT_CHARS] + '\n[cut]'
    return redact(text, config.secrets)


def quote(value: str) -> str:
    """A path or a glob in single quotes. A single quote inside cannot be expressed, so it is refused."""
    if "'" in value:
        raise HostError('a path with a single quote in it cannot be sent')
    return f"'{value}'"


def name(value: str, what: str) -> str:
    """A container, unit, key, dataset or file name: plain characters only."""
    if not _NAME.match(value):
        raise HostError(f'{what} {value!r} has characters muma-ro does not accept')
    return value


def number(value: int, what: str, low: int, high: int) -> str:
    """An integer within bounds, as text."""
    if not isinstance(value, int) or not low <= value <= high:
        raise HostError(f'{what} must be a whole number from {low} to {high}')
    return str(value)


# Command builders: one per tool, so the agent never writes a raw command.


def cmd_ls(path: str, long: bool = False) -> str:
    """``ls [-l] PATH``."""
    return f'ls {"-l " if long else ""}{quote(path)}'


def cmd_find(path: str, maxdepth: int = 1, kind: str | None = None, pattern: str | None = None) -> str:
    """``find PATH -maxdepth N [-type f|d] [-name GLOB]``."""
    parts = ['find', quote(path), '-maxdepth', number(maxdepth, 'maxdepth', 0, 3)]
    if kind:
        if kind not in ('f', 'd'):
            raise HostError('type is f or d')
        parts += ['-type', kind]
    if pattern:
        parts += ['-name', quote(pattern)]
    return ' '.join(parts)


def cmd_head(path: str, lines: int = 50) -> str:
    """``head -n N PATH``."""
    return f'head -n {number(lines, "lines", 1, 200)} {quote(path)}'


def cmd_container_logs(container: str, tail: int = 200, since: str | None = None) -> str:
    """``docker logs --tail N [--since D] C``."""
    parts = ['docker', 'logs', '--tail', number(tail, 'tail', 1, 2000)]
    if since:
        if not re.fullmatch(r'[0-9]{1,6}[smhd]', since):
            raise HostError('since looks like 30m, 2h or 1d')
        parts += ['--since', since]
    parts.append(name(container, 'container'))
    return ' '.join(parts)


def cmd_journal(unit: str, lines: int = 200) -> str:
    """``journalctl -u UNIT -n N``."""
    return f'journalctl -u {name(unit, "unit")} -n {number(lines, "lines", 1, 500)}'


def cmd_relay(ctid: int, command: str) -> str:
    """``pct exec ID -- COMMAND``: the container's own muma-ro decides COMMAND."""
    return f'pct exec {number(ctid, "ctid", 100, 999_999_999)} -- {command}'


# --- read-only HTTP ------------------------------------------------------------------------------


def _checked_path(path: str) -> str:
    if not path.startswith('/') or '..' in path or '#' in path or any(c.isspace() for c in path):
        raise HostError('the path must be absolute, without .., # or spaces')
    return path


def api_get(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # one GET with its own allowlist and secret
    service: str,
    base: str,
    token: str,
    headers: dict[str, str],
    path: str,
    allowed: Callable[[str], bool],
    secrets: tuple[str, ...],
    get: Callable[..., Any] = requests.get,
) -> str:
    """GET ``base + path`` with a read-only token, when ``path`` passes ``allowed``."""
    if not base or not token:
        raise HostError(f'{service} is not configured')
    path = _checked_path(path)
    if not allowed(path):
        raise HostError(f'{path} is not on the {service} allowlist')
    try:
        response = get(f'{base}{path}', headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise HostError(f'{service} is not reachable: {type(exc).__name__}') from exc
    text = response.text[:MAX_OUTPUT_CHARS]
    if not response.ok:
        return redact(f'HTTP {response.status_code}: {text[:500]}', secrets)
    return redact(text, secrets)


def portainer_get(config: HostsConfig, path: str, get: Callable[..., Any] = requests.get) -> str:
    """GET a Portainer path under ``/api/endpoints`` or ``/api/stacks``, as the view-only user."""
    return api_get(
        'Portainer',
        config.portainer_url,
        config.portainer_token,
        {'X-API-Key': config.portainer_token},
        path,
        lambda p: p.startswith(PORTAINER_PREFIXES),
        config.secrets,
        get,
    )


def gitlab_get(config: HostsConfig, path: str, get: Callable[..., Any] = requests.get) -> str:
    """GET a GitLab API v4 path: pipelines, jobs, merge requests, issues of a project, or runners."""
    return api_get(
        'GitLab',
        config.gitlab_url,
        config.gitlab_token,
        {'PRIVATE-TOKEN': config.gitlab_token},
        path,
        lambda p: any(r.match(p) for r in GITLAB_PATTERNS),
        config.secrets,
        get,
    )


def pve_get(config: HostsConfig, path: str, get: Callable[..., Any] = requests.get) -> str:
    """GET a Proxmox API path (``/api2/json`` is added) with the PVEAuditor token."""
    return api_get(
        'Proxmox',
        f'{config.pve_url}/api2/json' if config.pve_url else '',
        config.pve_token,
        {'Authorization': f'PVEAPIToken={config.pve_token}'},
        path,
        lambda p: p.startswith(PVE_PREFIXES),
        config.secrets,
        get,
    )
