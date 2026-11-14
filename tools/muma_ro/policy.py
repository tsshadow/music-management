"""Load and check ``/etc/muma-ro/policy.json``, the host's list of what may be read.

A policy that fails a check refuses every command: a bad edit fails closed. The checks are the
ones in the Policy section of the technical design.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

POLICY_PATH = '/etc/muma-ro/policy.json'

CLASSES = ('prod', 'devvm', 'runner', 'nas', 'proxmox')

# Every verb the wrapper knows; verbs.py has one builder for each (a test keeps the two equal).
VERB_NAMES = (
    'help', 'ls', 'stat', 'find', 'head', 'du', 'df', 'free', 'uptime',
    'docker-ps', 'docker-logs', 'docker-inspect', 'docker-stats', 'docker-system-df', 'docker-printenv',
    'systemctl-status', 'systemctl-timers', 'journalctl',
    'zfs-list', 'zfs-get', 'zpool-status', 'zpool-list', 'getfacl',
    'pct-list', 'qm-list', 'pvesm-status', 'pct-config', 'qm-config', 'vzdump-log', 'pct-exec',
)  # fmt: skip
MODES = ('list', 'read')
# A misspelled field would otherwise be ignored without a word; refusing it fails closed.
KNOWN_FIELDS = frozenset(
    {'_comment', 'class', 'verbs', 'roots', 'containers', 'container_patterns', 'env_keys', 'units',
     'head_extensions', 'datasets', 'zfs_properties', 'ctids', 'binaries'}
)  # fmt: skip

# A root may not be one of these, or below one: they hold keys, tokens and Docker's own state.
FORBIDDEN_ROOTS = ('/etc', '/root', '/var/lib/docker', '/etc/gitlab-runner', '/proc', '/sys', '/dev', '/boot')
_SSH_DIR = re.compile(r'^/home/[^/]+/\.ssh(/|$)')
# An env key that names a secret. printenv of such a key would hand the value to the agent.
_SECRET_KEY = re.compile(r'PASS|SECRET|TOKEN|KEY$|_KEY_|PRIVATE|CREDENTIAL', re.IGNORECASE)
_UNIT = re.compile(r'^[A-Za-z0-9@_.:-]+\.(service|timer|socket|mount)$')
_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')
_DATASET = re.compile(r'^[A-Za-z0-9_.:-]+(/[A-Za-z0-9_.:-]+)*$')


class PolicyError(ValueError):
    """The policy file is missing, unreadable or fails a check."""


@dataclass(frozen=True)
class Root:
    """A directory tree the agent may look at, and how far: ``list`` or ``read``."""

    path: str
    mode: str


@dataclass(frozen=True)
class Policy:  # pylint: disable=too-many-instance-attributes  # one per policy field
    """What one host allows. Built only through :func:`from_dict`, which checks every field."""

    host_class: str
    verbs: frozenset[str]
    roots: tuple[Root, ...] = ()
    containers: frozenset[str] = frozenset()
    container_patterns: tuple[re.Pattern[str], ...] = ()
    env_keys: frozenset[str] = frozenset()
    units: frozenset[str] = frozenset()
    head_extensions: tuple[str, ...] = ()
    datasets: tuple[str, ...] = ()
    zfs_properties: frozenset[str] = frozenset()
    ctids: frozenset[str] = frozenset()
    binaries: dict[str, str] = field(default_factory=dict)

    def allows_container(self, name: str) -> bool:
        """True when ``name`` is listed or matches one of the patterns."""
        return name in self.containers or any(p.fullmatch(name) for p in self.container_patterns)

    def allows_dataset(self, name: str) -> bool:
        """True when ``name`` is a listed dataset or below one."""
        return any(name == d or name.startswith(d + '/') for d in self.datasets)


def _strings(raw: Any, name: str) -> list[str]:
    """A list of strings, or a PolicyError naming the field."""
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(v, str) for v in raw):
        raise PolicyError(f'{name} must be a list of strings')
    return raw


def check_root(path: str) -> None:
    """Refuse a root that is relative, the file system root, or a place that holds secrets."""
    if not path.startswith('/') or path != os.path.normpath(path):
        raise PolicyError(f'root {path!r} must be an absolute, normalized path')
    if path == '/':
        raise PolicyError('/ cannot be a root')
    for forbidden in FORBIDDEN_ROOTS:
        if path == forbidden or path.startswith(forbidden + '/'):
            raise PolicyError(f'root {path} is under {forbidden}')
    if _SSH_DIR.match(path):
        raise PolicyError(f'root {path} is an .ssh directory')


def from_dict(data: Any) -> Policy:  # pylint: disable=too-many-locals,too-many-branches  # one check per field
    """Check every field and build the policy, or raise PolicyError."""
    if not isinstance(data, dict):
        raise PolicyError('the policy must be a JSON object')
    unknown_fields = sorted(set(data) - KNOWN_FIELDS)
    if unknown_fields:
        raise PolicyError(f'unknown fields: {", ".join(unknown_fields)}')
    host_class = data.get('class')
    if host_class not in CLASSES:
        raise PolicyError(f'class must be one of {", ".join(CLASSES)}')

    verbs = _strings(data.get('verbs'), 'verbs')
    unknown = sorted(set(verbs) - set(VERB_NAMES))
    if unknown:
        raise PolicyError(f'unknown verbs: {", ".join(unknown)}')

    roots = []
    for raw in data.get('roots') or []:
        if not isinstance(raw, dict) or raw.get('mode') not in MODES or not isinstance(raw.get('path'), str):
            raise PolicyError('each root needs a path and a mode of list or read')
        check_root(raw['path'])
        roots.append(Root(raw['path'], raw['mode']))

    env_keys = _strings(data.get('env_keys'), 'env_keys')
    for key in env_keys:
        if _SECRET_KEY.search(key) or not _NAME.match(key):
            raise PolicyError(f'env key {key!r} looks like a secret or is not a plain name')

    units = _strings(data.get('units'), 'units')
    for unit in units:
        if not _UNIT.match(unit):
            raise PolicyError(f'unit {unit!r} is not a unit name')

    containers = _strings(data.get('containers'), 'containers')
    for name in containers:
        if not _NAME.match(name):
            raise PolicyError(f'container {name!r} is not a plain name')
    try:
        patterns = tuple(re.compile(p) for p in _strings(data.get('container_patterns'), 'container_patterns'))
    except re.error as exc:
        raise PolicyError(f'a container pattern does not compile: {exc}') from exc
    for pattern in patterns:
        if not pattern.pattern.startswith('^') or not pattern.pattern.endswith('$'):
            raise PolicyError(f'container pattern {pattern.pattern!r} must be anchored with ^ and $')

    datasets = _strings(data.get('datasets'), 'datasets')
    for name in datasets:
        if not _DATASET.match(name) or '..' in name.split('/'):
            raise PolicyError(f'dataset {name!r} is not a dataset name')

    extensions = _strings(data.get('head_extensions'), 'head_extensions')
    for ext in extensions:
        if not re.fullmatch(r'\.[a-z0-9]{1,8}', ext):
            raise PolicyError(f'extension {ext!r} must look like .nfo')

    ctids = _strings(data.get('ctids'), 'ctids')
    if any(not c.isdigit() for c in ctids):
        raise PolicyError('ctids must be numbers')

    binaries = data.get('binaries') or {}
    if not isinstance(binaries, dict) or not all(
        isinstance(k, str) and isinstance(v, str) and v.startswith('/') for k, v in binaries.items()
    ):
        raise PolicyError('binaries maps a tool name to an absolute path')

    return Policy(
        host_class=host_class,
        verbs=frozenset(verbs) | {'help'},
        roots=tuple(roots),
        containers=frozenset(containers),
        container_patterns=patterns,
        env_keys=frozenset(env_keys),
        units=frozenset(units),
        head_extensions=tuple(extensions),
        datasets=tuple(datasets),
        zfs_properties=frozenset(_strings(data.get('zfs_properties'), 'zfs_properties')),
        ctids=frozenset(ctids),
        binaries=dict(binaries),
    )


def load(path: str = POLICY_PATH) -> Policy:
    """Read and check the policy file. The file must belong to root and not be group or world writable."""
    try:
        info = os.stat(path)
        text = Path(path).read_text(encoding='utf-8')
    except OSError as exc:
        raise PolicyError(f'cannot read {path}: {exc.strerror}') from exc
    if info.st_uid != 0 and os.geteuid() == 0:
        raise PolicyError(f'{path} does not belong to root')
    if info.st_mode & 0o022:
        raise PolicyError(f'{path} is writable by others than its owner')
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise PolicyError(f'{path} is not valid JSON: {exc}') from exc
    return from_dict(data)
