#!/usr/bin/env python3
"""Nightly mirror of the music library to the mirror NAS.

Runs on the mirror NAS, from a root-owned copy in ``/opt/muma-mirror/bin/``, started by cron.
It pulls the library from the library NAS with rsync over SSH and **never deletes on the
mirror**: a file that is gone from the library stays on the mirror at its old path. After a
good run it takes a ZFS snapshot, so an overwritten file stays readable in the snapshot before.

Standard library only: the NAS has Python but not this repository.

Design and the decisions behind it: docs/designs/music-mirror/technical.md.
Operating manual: scripts/music-mirror/README.md.

Usage:
    music_mirror.py                       # the nightly run
    music_mirror.py --initial             # the first full copy: no change limits
    music_mirror.py --allow-large-change  # one run past the changed-files limit, after a mass retag
    music_mirror.py --prune               # snapshot, then remove what is only on the mirror
    music_mirror.py --env /path/to/env    # another config file (default /opt/muma-mirror/env)

Exit codes: 0 ok, 1 failed, 2 refused, 3 another run holds the lock, 4 configuration error.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import gzip
import json
import os
import random
import subprocess
import sys
import tempfile
import urllib.request
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_ENV = '/opt/muma-mirror/env'
STATUS_NAME = 'latest.json'
SNAPSHOT_PREFIX = 'mirror-'
STAMP_FORMAT = '%Y%m%dT%H%M%SZ'
MANIFESTS_KEPT = 30
KEEP_DAILY, KEEP_WEEKLY, KEEP_MONTHLY = 14, 8, 12
MIN_FILES_RATIO = 0.9

EXIT_OK, EXIT_FAILED, EXIT_REFUSED, EXIT_LOCKED, EXIT_CONFIG = 0, 1, 2, 3, 4

# rsync exit codes: 0 ok, 24 "some files vanished before they could be transferred" -- an import
# moved a folder during the run, which the next run picks up. Anything else is a failure.
RSYNC_OK_CODES = frozenset({0, 24})

# Content, symbolic links, times and hard links. No owner, group, mode or ACL: the library's POSIX
# ACLs would make the mirror as hard to read as the library was. --inplace writes only the changed
# blocks, so ZFS keeps only those in the snapshot of the night before. No --delete, ever: see
# copy_argv() and the test that pins it.
BASE_FLAGS = ('-rltH', '--inplace', '--partial')
# One line per item: flags|size|name. Given -ii, rsync also lists the unchanged files, which
# makes the dry run the manifest as well.
OUT_FORMAT = '--out-format=%i|%l|%n'


class ConfigError(RuntimeError):
    """The env file is missing a value or has a bad one."""


class RunRefused(RuntimeError):
    """A guard stopped the run before anything was copied."""


class RunFailed(RuntimeError):
    """Something broke; the mirror may hold a half-finished run, the snapshots do not."""


@dataclass(frozen=True)
class Config:
    """The job's settings, from ``/opt/muma-mirror/env``."""

    source: str
    read_key: str
    status_key: str
    dest: Path
    dataset: str
    state_dir: Path
    expected_dirs: tuple[str, ...] = ()
    max_changed_percent: float = 5.0
    max_changed_gb: float = 200.0
    pool_warn_percent: int = 80
    sample_size: int = 200
    full_checksum_monthly: bool = True
    ntfy_url: str = ''
    ntfy_topic: str = ''
    ntfy_token: str = ''
    rsync: str = '/usr/bin/rsync'
    ssh: str = '/usr/bin/ssh'
    zfs: str = '/usr/sbin/zfs'


def parse_env_file(text: str) -> dict[str, str]:
    """``KEY=VALUE`` lines, read without a shell; comments and blank lines skipped."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
            value = value[1:-1]
        values[key.strip()] = value
    return values


def load_config(values: dict[str, str]) -> Config:
    """Build the config and name every missing required key at once."""
    required = (
        'MIRROR_SOURCE',
        'MIRROR_READ_KEY',
        'MIRROR_STATUS_KEY',
        'MIRROR_DEST',
        'MIRROR_DATASET',
        'MIRROR_STATE_DIR',
    )
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise ConfigError(f'missing in the env file: {", ".join(missing)}')
    try:
        cfg = Config(
            source=values['MIRROR_SOURCE'],
            read_key=values['MIRROR_READ_KEY'],
            status_key=values['MIRROR_STATUS_KEY'],
            dest=Path(values['MIRROR_DEST']),
            dataset=values['MIRROR_DATASET'],
            state_dir=Path(values['MIRROR_STATE_DIR']),
            expected_dirs=tuple(d.strip() for d in values.get('MIRROR_EXPECTED_DIRS', '').split(',') if d.strip()),
            max_changed_percent=float(values.get('MIRROR_MAX_CHANGED_PERCENT', '5')),
            max_changed_gb=float(values.get('MIRROR_MAX_CHANGED_GB', '200')),
            pool_warn_percent=int(values.get('MIRROR_POOL_WARN_PERCENT', '80')),
            sample_size=int(values.get('MIRROR_SAMPLE_SIZE', '200')),
            full_checksum_monthly=values.get('MIRROR_FULL_CHECKSUM_MONTHLY', '1') != '0',
            ntfy_url=values.get('MIRROR_NTFY_URL', '').rstrip('/'),
            ntfy_topic=values.get('MIRROR_NTFY_TOPIC', ''),
            ntfy_token=values.get('MIRROR_NTFY_TOKEN', ''),
            rsync=values.get('MIRROR_RSYNC', '/usr/bin/rsync'),
            ssh=values.get('MIRROR_SSH', '/usr/bin/ssh'),
            zfs=values.get('MIRROR_ZFS', '/usr/sbin/zfs'),
        )
    except ValueError as exc:
        raise ConfigError(f'a number in the env file does not parse: {exc}') from exc
    if cfg.ntfy_url and not cfg.ntfy_url.startswith(('https://', 'http://')):
        raise ConfigError('MIRROR_NTFY_URL must start with https:// or http://')
    return cfg


# --- rsync argument lists ----------------------------------------------------------------------


def _ssh(cfg: Config, key: str) -> str:
    """The ``-e`` value: batch mode, one key, a pinned host key."""
    return f'{cfg.ssh} -i {key} -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes'


def _source(cfg: Config) -> str:
    """The library as rsync sees it. ``rrsync -ro`` on the library NAS roots ``./`` at the library."""
    return f'{cfg.source}:./'


def copy_argv(cfg: Config, *, dry_run: bool) -> list[str]:
    """The nightly copy (``dry_run=False``) or its dry run, which also lists the unchanged files."""
    argv = [cfg.rsync, *BASE_FLAGS, OUT_FORMAT, '-e', _ssh(cfg, cfg.read_key)]
    argv += ['--dry-run', '-ii'] if dry_run else ['-i']
    return [*argv, _source(cfg), f'{cfg.dest}/']


def sample_argv(cfg: Config, files_from: Path) -> list[str]:
    """Compare the listed files by checksum; every ``>f`` line in the output differs."""
    return [
        cfg.rsync,
        *BASE_FLAGS,
        '--checksum',
        '--dry-run',
        '-i',
        OUT_FORMAT,
        f'--files-from={files_from}',
        '-e',
        _ssh(cfg, cfg.read_key),
        _source(cfg),
        f'{cfg.dest}/',
    ]


def monthly_argv(cfg: Config, *, checksum: bool) -> list[str]:
    """The monthly pass: what a delete *would* remove, and with ``checksum`` what differs.

    ``--delete`` here is always paired with ``--dry-run``: this lists, it removes nothing.
    """
    argv = [cfg.rsync, *BASE_FLAGS, '--dry-run', '--delete', '-i', OUT_FORMAT]
    if checksum:
        argv.append('--checksum')
    return [*argv, '-e', _ssh(cfg, cfg.read_key), _source(cfg), f'{cfg.dest}/']


def prune_argv(cfg: Config) -> list[str]:
    """The one argument list that deletes on the mirror. Only ``prune()`` uses it, after a snapshot."""
    return [
        cfg.rsync,
        *BASE_FLAGS,
        '--delete',
        '-i',
        OUT_FORMAT,
        '-e',
        _ssh(cfg, cfg.read_key),
        _source(cfg),
        f'{cfg.dest}/',
    ]


def status_push_argv(cfg: Config, local: Path) -> list[str]:
    """Copy ``latest.json`` into the status directory (``rrsync -wo`` on the library NAS)."""
    return [cfg.rsync, '-t', '-e', _ssh(cfg, cfg.status_key), str(local), f'{cfg.source}:./{STATUS_NAME}']


# --- reading rsync output ----------------------------------------------------------------------


@dataclass
class Listing:
    """What one rsync pass reported, per file."""

    files: list[str] = field(default_factory=list)
    changed: list[tuple[str, int]] = field(default_factory=list)
    deleting: list[str] = field(default_factory=list)


def parse_items(lines: Iterable[str]) -> Listing:
    """Read ``%i|%l|%n`` lines. Directories and links count for nothing; files are listed."""
    listing = Listing()
    for line in lines:
        flags, sep, rest = line.partition('|')
        if not sep:
            continue
        size_text, _, name = rest.partition('|')
        flags = flags.strip()
        if flags.startswith('*deleting'):
            listing.deleting.append(name.rstrip('/'))
            continue
        if len(flags) < 2 or flags[1] != 'f':
            continue
        listing.files.append(name)
        if flags[0] in '<>':
            try:
                size = int(size_text.replace(',', ''))
            except ValueError:
                size = 0
            listing.changed.append((name, size))
    return listing


def count_vanished(stderr: str) -> int:
    """How many "file has vanished" lines rsync printed."""
    return sum(1 for line in stderr.splitlines() if 'file has vanished' in line)


# --- guards ------------------------------------------------------------------------------------


def check_change(  # pylint: disable=too-many-arguments
    files_total: int,
    changed: Sequence[tuple[str, int]],
    previous_total: int | None,
    cfg: Config,
    *,
    initial: bool,
    allow_large_change: bool,
) -> None:
    """Raise ``RunRefused`` when the library shrank or too much of it would change."""
    if initial:
        return
    if previous_total and files_total < previous_total * MIN_FILES_RATIO:
        raise RunRefused(
            f'the library lists {files_total} files, fewer than 90% of the {previous_total} of the last good run'
        )
    if allow_large_change:
        return
    changed_bytes = sum(size for _, size in changed)
    percent = 100.0 * len(changed) / files_total if files_total else 0.0
    if percent > cfg.max_changed_percent or changed_bytes > cfg.max_changed_gb * 1e9:
        raise RunRefused(
            f'{len(changed)} files ({percent:.1f}%, {changed_bytes / 1e9:.1f} GB) would change; '
            f'the limit is {cfg.max_changed_percent}% or {cfg.max_changed_gb} GB. '
            'Check the library, then run once with --allow-large-change.'
        )


# --- snapshots ---------------------------------------------------------------------------------


def snapshot_name(now: datetime) -> str:
    """``mirror-20261113T011244Z``."""
    return SNAPSHOT_PREFIX + now.strftime(STAMP_FORMAT)


def parse_snapshot_time(name: str) -> datetime | None:
    """The time in a ``mirror-<stamp>`` name, or None for any other name."""
    if not name.startswith(SNAPSHOT_PREFIX):
        return None
    try:
        return datetime.strptime(name[len(SNAPSHOT_PREFIX) :], STAMP_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None


def snapshots_to_remove(names: Iterable[str]) -> list[str]:
    """Pick the ``mirror-*`` snapshots outside 14 daily, 8 weekly and 12 monthly.

    The newest snapshot of each of the last N periods that have one is kept, per kind, like
    ``restic forget --keep-daily``. The newest snapshot is always kept. A name without the
    prefix is never returned.
    """
    dated = sorted(((t, n) for n in names if (t := parse_snapshot_time(n)) is not None), reverse=True)
    if not dated:
        return []
    keep = {dated[0][1]}
    buckets = (
        (KEEP_DAILY, lambda t: t.date()),
        (KEEP_WEEKLY, lambda t: t.isocalendar()[:2]),
        (KEEP_MONTHLY, lambda t: (t.year, t.month)),
    )
    for limit, period in buckets:
        seen: set[Any] = set()
        for when, name in dated:
            key = period(when)
            if key in seen:
                continue
            if len(seen) >= limit:
                break
            seen.add(key)
            keep.add(name)
    return [name for _, name in dated if name not in keep]


# --- the run -----------------------------------------------------------------------------------


@dataclass
class Shell:
    """Runs a command; replaced by a fake in the tests."""

    def run(self, argv: Sequence[str], timeout: float | None = None) -> subprocess.CompletedProcess[str]:
        """Run without a shell and capture both streams as text."""
        return subprocess.run(list(argv), capture_output=True, text=True, timeout=timeout, check=False)


def _log(message: str) -> None:
    print(f'{datetime.now(UTC).isoformat(timespec="seconds")} music_mirror: {message}', flush=True)


def read_state(cfg: Config) -> dict[str, Any]:
    """The local copy of the last status, or an empty dict."""
    try:
        data = json.loads((cfg.state_dir / STATUS_NAME).read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_status(cfg: Config, payload: dict[str, Any], shell: Shell) -> None:
    """Write ``latest.json`` locally through a partial name and a rename, then push it."""
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    final = cfg.state_dir / STATUS_NAME
    partial = cfg.state_dir / (STATUS_NAME + '.partial')
    partial.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    os.replace(partial, final)
    result = shell.run(status_push_argv(cfg, final), timeout=120)
    if result.returncode != 0:
        _log(f'pushing the status failed (exit {result.returncode}): {result.stderr.strip()[:300]}')


def notify(cfg: Config, title: str, message: str) -> None:
    """Push a failure to the alerts topic at once, so the phone hears it at night."""
    if not (cfg.ntfy_url and cfg.ntfy_topic):
        return
    request = urllib.request.Request(  # noqa: S310 - the URL comes from the root-owned env file
        f'{cfg.ntfy_url}/{cfg.ntfy_topic}',
        data=message.encode('utf-8'),
        headers={'Title': title, 'Priority': 'high', 'Tags': 'warning,floppy_disk'},
        method='POST',
    )
    if cfg.ntfy_token:
        request.add_header('Authorization', f'Bearer {cfg.ntfy_token}')
    try:
        with urllib.request.urlopen(request, timeout=15):  # noqa: S310
            pass
    except OSError as exc:
        _log(f'the ntfy push failed: {exc}')


def pool_used_percent(cfg: Config, shell: Shell) -> int | None:
    """Used space of the mirror dataset as a percentage of used plus available."""
    result = shell.run([cfg.zfs, 'list', '-H', '-p', '-o', 'used,avail', cfg.dataset], timeout=60)
    if result.returncode != 0:
        return None
    try:
        used, avail = (int(v) for v in result.stdout.split()[:2])
    except ValueError:
        return None
    return round(100 * used / (used + avail)) if used + avail else None


def list_snapshots(cfg: Config, shell: Shell) -> list[str]:
    """The short names of the dataset's own snapshots."""
    result = shell.run([cfg.zfs, 'list', '-H', '-t', 'snapshot', '-d', '1', '-o', 'name', cfg.dataset], timeout=120)
    if result.returncode != 0:
        raise RunFailed(f'zfs list of the snapshots failed: {result.stderr.strip()[:300]}')
    prefix = cfg.dataset + '@'
    return [line[len(prefix) :] for line in result.stdout.splitlines() if line.startswith(prefix)]


def take_snapshot(cfg: Config, shell: Shell, now: datetime) -> str:
    """Snapshot the mirror dataset and return the snapshot's short name."""
    name = snapshot_name(now)
    result = shell.run([cfg.zfs, 'snapshot', f'{cfg.dataset}@{name}'], timeout=120)
    if result.returncode != 0:
        raise RunFailed(f'zfs snapshot failed: {result.stderr.strip()[:300]}')
    return name


def apply_retention(cfg: Config, shell: Shell) -> list[str]:
    """Destroy the snapshots that fall outside the retention; returns their names."""
    removed = []
    for name in snapshots_to_remove(list_snapshots(cfg, shell)):
        result = shell.run([cfg.zfs, 'destroy', f'{cfg.dataset}@{name}'], timeout=600)
        if result.returncode == 0:
            removed.append(name)
        else:
            _log(f'could not remove snapshot {name}: {result.stderr.strip()[:300]}')
    return removed


def save_manifest(cfg: Config, files: Sequence[str], now: datetime) -> Path:
    """Store the library's file list of this run, for a full restore without the orphans."""
    directory = cfg.state_dir / 'manifests'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'manifest-{now.strftime(STAMP_FORMAT)}.txt.gz'
    with gzip.open(path, 'wt', encoding='utf-8') as handle:
        for name in files:
            handle.write(name + '\n')
    for old in sorted(directory.glob('manifest-*.txt.gz'))[:-MANIFESTS_KEPT]:
        old.unlink()
    return path


def pick_sample(files: Sequence[str], changed: Sequence[str], size: int, rng: random.Random) -> list[str]:
    """Up to half from tonight's transfers, the rest at random from the whole library."""
    from_changed = rng.sample(list(changed), min(len(changed), size // 2))
    taken = set(from_changed)
    rest = [f for f in files if f not in taken]
    return from_changed + rng.sample(rest, min(len(rest), size - len(from_changed)))


def _rsync(shell: Shell, argv: Sequence[str], what: str) -> subprocess.CompletedProcess[str]:
    result = shell.run(argv)
    if result.returncode not in RSYNC_OK_CODES:
        raise RunFailed(f'{what}: rsync exit {result.returncode}: {result.stderr.strip()[-500:]}')
    return result


def preflight(cfg: Config, shell: Shell) -> None:
    """The mirror dataset is mounted and the library lists with every expected folder."""
    if not os.path.ismount(cfg.dest):
        raise RunFailed(f'{cfg.dest} is not a mount point; the mirror dataset is not mounted')
    result = shell.run([cfg.rsync, '--list-only', '-e', _ssh(cfg, cfg.read_key), _source(cfg)], timeout=120)
    if result.returncode != 0:
        raise RunFailed(f'the library does not list (exit {result.returncode}): {result.stderr.strip()[:300]}')
    names = {line.split(None, 4)[-1] for line in result.stdout.splitlines() if len(line.split(None, 4)) == 5}
    absent = [d for d in cfg.expected_dirs if d not in names]
    if absent:
        raise RunRefused(f'the library has no {", ".join(absent)}: the source looks wrong or unmounted')


def monthly_pass(cfg: Config, shell: Shell, now: datetime) -> tuple[dict[str, Any], dict[str, Any]]:
    """Count what is only on the mirror and, when configured, compare every file by checksum."""
    result = _rsync(shell, monthly_argv(cfg, checksum=cfg.full_checksum_monthly), 'monthly pass')
    listing = parse_items(result.stdout.splitlines())
    orphan_files, orphan_bytes = 0, 0
    for name in listing.deleting:
        path = cfg.dest / name
        if path.is_file() and not path.is_symlink():
            orphan_files += 1
            orphan_bytes += path.stat().st_size
    stamp = now.isoformat(timespec='seconds')
    orphans = {'files': orphan_files, 'bytes': orphan_bytes, 'measured_at': stamp}
    full: dict[str, Any] = {'at': None, 'differing': None, 'differing_count': None}
    if cfg.full_checksum_monthly:
        names = [name for name, _ in listing.changed]
        full = {'at': stamp, 'differing': names[:50], 'differing_count': len(names)}
    return orphans, full


def run(  # pylint: disable=too-many-locals,too-many-statements  # one run, step by step
    cfg: Config, shell: Shell, *, initial: bool = False, allow_large_change: bool = False, now: datetime | None = None
) -> int:
    """One nightly run; always writes a status, also when it fails or is refused."""
    started = now or datetime.now(UTC)
    previous = read_state(cfg)
    payload: dict[str, Any] = {
        'run_id': started.strftime(STAMP_FORMAT),
        'started_at': started.isoformat(timespec='seconds'),
        'result': 'failed',
        'reason': None,
        'rsync_exit': None,
        'snapshot': None,
        'sample': {'checked': 0, 'differing': []},
        'orphans': previous.get('orphans'),
        'full_checksum': previous.get('full_checksum'),
        'last_ok_files_total': previous.get('last_ok_files_total'),
        'last_ok_at': previous.get('last_ok_at'),
    }
    code = EXIT_FAILED
    try:
        payload['pool_used_percent'] = pool_used_percent(cfg, shell)
        preflight(cfg, shell)

        dry = _rsync(shell, copy_argv(cfg, dry_run=True), 'dry run')
        listing = parse_items(dry.stdout.splitlines())
        payload['files_total'] = len(listing.files)
        check_change(
            len(listing.files),
            listing.changed,
            previous.get('last_ok_files_total'),
            cfg,
            initial=initial,
            allow_large_change=allow_large_change,
        )

        copy = _rsync(shell, copy_argv(cfg, dry_run=False), 'copy')
        payload['rsync_exit'] = copy.returncode
        copied = parse_items(copy.stdout.splitlines()).changed
        payload['files_transferred'] = len(copied)
        payload['bytes_transferred'] = sum(size for _, size in copied)
        payload['files_vanished'] = count_vanished(copy.stderr)

        save_manifest(cfg, listing.files, started)

        sample = pick_sample(listing.files, [n for n, _ in copied], cfg.sample_size, random.Random())
        with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False, encoding='utf-8') as handle:
            handle.write('\n'.join(sample) + '\n')
            files_from = Path(handle.name)
        try:
            checked = _rsync(shell, sample_argv(cfg, files_from), 'sample check')
        finally:
            files_from.unlink(missing_ok=True)
        differing = [name for name, _ in parse_items(checked.stdout.splitlines()).changed]
        payload['sample'] = {'checked': len(sample), 'differing': differing[:50]}

        last_ok = previous.get('last_ok_at')
        # First good run of a month. Not on --initial: that run has just read every byte.
        if not initial and (not last_ok or last_ok[:7] != started.isoformat()[:7]):
            payload['orphans'], payload['full_checksum'] = monthly_pass(cfg, shell, started)

        payload['snapshot'] = take_snapshot(cfg, shell, datetime.now(UTC))
        payload['snapshots_removed'] = apply_retention(cfg, shell)
        payload['result'] = 'ok'
        payload['last_ok_files_total'] = len(listing.files)
        code = EXIT_OK
    except RunRefused as exc:
        payload.update(result='refused', reason=str(exc))
        code = EXIT_REFUSED
    except (RunFailed, OSError, subprocess.SubprocessError) as exc:
        payload.update(result='failed', reason=str(exc))
        code = EXIT_FAILED

    finished = datetime.now(UTC)
    payload['finished_at'] = finished.isoformat(timespec='seconds')
    if code == EXIT_OK:
        payload['last_ok_at'] = payload['finished_at']
    write_status(cfg, payload, shell)
    if code == EXIT_OK and payload['pool_used_percent'] and payload['pool_used_percent'] >= cfg.pool_warn_percent:
        notify(cfg, 'Music mirror pool filling up', f'the mirror pool is {payload["pool_used_percent"]}% used')
    if code != EXIT_OK:
        notify(cfg, f'Music mirror {payload["result"]}', payload['reason'] or payload['result'])
    _log(f'{payload["result"]}: {payload["reason"] or "done"}')
    return code


def prune(cfg: Config, shell: Shell) -> int:
    """Snapshot first, then delete what is only on the mirror. Refuses without the snapshot."""
    try:
        preflight(cfg, shell)
        name = take_snapshot(cfg, shell, datetime.now(UTC))
    except (RunFailed, RunRefused) as exc:
        _log(f'prune refused, no snapshot: {exc}')
        return EXIT_REFUSED
    result = shell.run(prune_argv(cfg))
    removed = len(parse_items(result.stdout.splitlines()).deleting)
    state = read_state(cfg)
    if state:
        state['last_prune'] = {
            'at': datetime.now(UTC).isoformat(timespec='seconds'),
            'removed': removed,
            'snapshot': name,
        }
        write_status(cfg, state, shell)
    _log(f'prune removed {removed} items after snapshot {name} (rsync exit {result.returncode})')
    return EXIT_OK if result.returncode in RSYNC_OK_CODES else EXIT_FAILED


@contextlib.contextmanager
def run_lock(state_dir: Path):
    """Hold ``state_dir/lock``; yields False when another run holds it."""
    state_dir.mkdir(parents=True, exist_ok=True)
    with open(state_dir / 'lock', 'w', encoding='utf-8') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the flags, load the env file, take the lock and run."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n', 1)[0])
    parser.add_argument('--env', default=DEFAULT_ENV)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--initial', action='store_true', help='first full copy: no change limits')
    mode.add_argument('--allow-large-change', action='store_true', help='one run past the changed-files limit')
    mode.add_argument('--prune', action='store_true', help='snapshot, then remove what is only on the mirror')
    args = parser.parse_args(argv)
    try:
        cfg = load_config(parse_env_file(Path(args.env).read_text(encoding='utf-8')))
    except (OSError, ConfigError) as exc:
        print(f'music_mirror: {exc}', file=sys.stderr)
        return EXIT_CONFIG
    with run_lock(cfg.state_dir) as locked:
        if not locked:
            print('music_mirror: another run holds the lock', file=sys.stderr)
            return EXIT_LOCKED
        shell = Shell()
        if args.prune:
            return prune(cfg, shell)
        return run(cfg, shell, initial=args.initial, allow_large_change=args.allow_large_change)


if __name__ == '__main__':
    sys.exit(main())
