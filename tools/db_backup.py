#!/usr/bin/env python3
"""Daily database backup: dump, verify, prune, and alert when it did not work.

Implements docs/superpowers/specs/2026-08-02-daily-db-backups-design.md. Three
things deviate from that document, each for a reason recorded here:

- **The alert is pushed synchronously.** The design assumed
  ``NotificationService`` still read ``notify_url`` itself. It does not: the push
  moved to ``NtfySink``, which is only wired up by ``setup_logging()``, and
  ``EventService.emit`` hands the event to a *daemon* thread with no flush. A
  one-shot CLI that emits and exits can therefore die before its own alarm
  leaves the process -- for a job whose entire purpose is to complain when it
  fails, that is the wrong failure mode. ``NtfySink.handle`` is synchronous and
  needs no database, so the push goes through it directly and the event row is
  written best-effort alongside.

- **Row counts are recorded next to the dump.** The design's ``latest.json``
  holds a timestamp and a byte count, which proves a file arrived, not that it
  contains a database. ``tools/db_restore_check.py`` compares a restored copy
  against these counts, which is what turns "the file exists" into "the file
  restores".

- **It dumps one database, without ``--databases``.** The dump therefore carries
  no ``CREATE DATABASE``/``USE``, so restoring it somewhere else is a matter of
  naming the target -- which is what makes both ``scripts/restore_db.sh`` and
  the restore check safe. ``apk-hoster`` lives on the same server and is *not*
  covered here; it belongs to another stack and holds two tables.

Usage:
    python tools/db_backup.py                 # take a backup
    python tools/db_backup.py --check-stale   # alert if the newest is too old
    python tools/db_backup.py --check-destination  # validate config, dump nothing
"""
from __future__ import annotations

import argparse
import contextlib
import gzip
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from services.common.Helpers.EventService import Event, event_service  # noqa: E402
from services.common.Helpers.ntfy_sink import NtfySink  # noqa: E402

SOURCE = 'db-backup'

# Deliberately not `muma_*`: tools/backup_db.sh writes muma_backup_*.sql.gz into
# the same directory, and a prune glob that matched those would delete another
# tool's output. Everything this job removes, it also wrote.
DAILY_PREFIX = 'muma_db_'
MONTHLY_PREFIX = 'muma_db_monthly_'
SUFFIX = '.sql.gz'
LATEST_NAME = 'latest.json'

# A dump of this database is ~780 MB compressed. The floor only has to be above
# "MariaDB printed an error and quit", which is a few hundred bytes.
MIN_SIZE_BYTES = 1024 * 1024
DUMP_TRAILER = '-- Dump completed'
MONTHLY_RETENTION_MONTHS = 6
DEFAULT_RETENTION_DAYS = 14
DEFAULT_STALE_AFTER_HOURS = 36


class BackupError(Exception):
    """Anything that means the backup did not happen."""


def alert(title: str, message: str) -> None:
    """Push first, record second.

    The push is what wakes someone up and it needs no database. The event row is
    nice to have and needs the very thing that may be broken, so it goes last and
    its failure is not allowed to swallow the push.
    """
    event = Event(level='ERROR', title=title, message=message, source=SOURCE, push=True)
    try:
        NtfySink().handle(event)
    except Exception as exc:  # pragma: no cover - defensive
        print(f'db_backup: pushing the alert failed: {exc}', file=sys.stderr)
    try:
        event_service.emit(level='ERROR', title=title, message=message,
                           source=SOURCE, push=True)
    except Exception as exc:  # pragma: no cover - defensive
        print(f'db_backup: recording the alert failed: {exc}', file=sys.stderr)


def resolve_destination(destination: str, data_path: str | None) -> Path:
    """Refuse a destination that is not a usable, separate place to write.

    A backup on the database's own disk protects against nothing, and writing one
    is worse than writing none because it manufactures confidence. Both paths are
    resolved before comparing so a symlink cannot smuggle the backups back onto
    the data directory.

    This runs inside the tools container, where the host's data directory is not
    mounted, so it can only compare paths. The device comparison -- prod's actual
    failure, where /muma/backups and the datadir are different paths on one disk
    -- has to happen on the host and lives in scripts/backup/install-systemd.sh.
    """
    if not destination:
        raise BackupError('BACKUP_PATH is not set')
    dest = Path(destination).resolve()
    if not dest.is_dir():
        raise BackupError(f'backup destination {dest} does not exist or is not a directory')
    if not os.access(dest, os.W_OK):
        raise BackupError(f'backup destination {dest} is not writable')
    if data_path:
        datadir = (Path(data_path) / 'mariadb').resolve()
        if dest == datadir or datadir in dest.parents:
            raise BackupError(
                f'backup destination {dest} is inside the MariaDB data directory '
                f'{datadir}; that is not a backup')
    return dest


def _credentials() -> dict[str, str]:
    """Prefer a dedicated backup account, fall back to the application's.

    The application user has no SHOW VIEW, TRIGGER or EVENT privilege, so a dump
    with --routines --triggers --events fails against it. That failure is loud
    and the grant is in scripts/backup/README.md, which is better than quietly
    dumping less than was asked for.
    """
    host = os.getenv('DB_HOST', 'db')
    port = os.getenv('DB_PORT', '3306')
    if ':' in host:
        host, _, port = host.partition(':')
    return {
        'host': host,
        'port': port,
        'user': os.getenv('BACKUP_DB_USER') or os.getenv('DB_USER', ''),
        'password': os.getenv('BACKUP_DB_PASS') or os.getenv('DB_PASS', ''),
        'database': os.getenv('DB_DB', ''),
    }


def dump(target: Path, creds: dict[str, str]) -> None:
    """Run mariadb-dump into a gzip file, checking the thing that actually failed.

    The password goes in a --defaults-extra-file, never on the command line:
    command lines are readable through ps by every local process.

    gzip happens in this process rather than through a shell pipe, so there is
    one return code to check instead of a pipeline whose first half can fail
    while gzip cheerfully reports success. That is the exact shape that left a
    zero-byte pre_deploy_20260705_081708.sql on production.
    """
    fd, defaults_path = tempfile.mkstemp(prefix='db-backup-', suffix='.cnf')
    os.fchmod(fd, 0o600)
    try:
        with os.fdopen(fd, 'w') as handle:
            handle.write('[client]\n')
            handle.write(f"user={creds['user']}\n")
            handle.write(f"password={creds['password']}\n")
        command = [
            'mariadb-dump',
            f'--defaults-extra-file={defaults_path}',
            '--host', creds['host'],
            '--port', creds['port'],
            '--single-transaction',
            '--quick',
            '--routines',
            '--triggers',
            '--events',
            '--default-character-set=utf8mb4',
            creds['database'],
        ]
        with gzip.open(target, 'wb') as out:
            process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            assert process.stdout is not None
            for chunk in iter(lambda: process.stdout.read(1024 * 1024), b''):
                out.write(chunk)
            _, stderr = process.communicate()
        if process.returncode != 0:
            detail = stderr.decode('utf-8', 'replace').strip().splitlines()
            raise BackupError(
                f'mariadb-dump exited {process.returncode}: '
                f'{detail[-1] if detail else "no output"}')
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(defaults_path)


def verify(path: Path) -> None:
    """Three checks, because the failure already seen here is a file that exists.

    Reading the whole stream is the gzip -t equivalent; the trailer is what
    separates a complete dump from one truncated halfway.
    """
    size = path.stat().st_size
    if size < MIN_SIZE_BYTES:
        raise BackupError(f'{path.name} is {size} bytes, below the {MIN_SIZE_BYTES} floor')
    tail = b''
    try:
        with gzip.open(path, 'rb') as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                tail = chunk[-4096:]
    except (OSError, EOFError) as exc:
        raise BackupError(f'{path.name} does not decompress: {exc}') from exc
    if DUMP_TRAILER.encode() not in tail:
        raise BackupError(f'{path.name} has no {DUMP_TRAILER!r} trailer; it is truncated')


IDENTIFIER = re.compile(r'^[A-Za-z0-9_$]+$')


def quote_identifier(name: str) -> str:
    """Backtick-quote a table name, having first checked it is only a name.

    A table name cannot be a bound parameter, so the counting query interpolates
    it. The value comes from information_schema for the configured database, not
    from anything a user supplies -- but "it cannot be hostile today" is not a
    property that survives refactoring, so the shape is checked rather than
    assumed.
    """
    if not IDENTIFIER.match(name):
        raise BackupError(f'refusing to build a query around table name {name!r}')
    return f'`{name}`'


def row_counts(creds: dict[str, str]) -> dict[str, int]:
    """Exact counts per table, taken right after the dump.

    information_schema.table_rows is an InnoDB estimate and can be out by
    percentages, which is useless for deciding whether a restore lost data.

    These are read after the dump's snapshot, so a restored copy can hold
    slightly *fewer* rows in an append-heavy table than what is recorded here.
    tools/db_restore_check.py allows for that; it is checking for a lost table or
    a truncated file, not for a difference of a hundred events.
    """
    from services.common.Helpers.DatabaseConnector import DatabaseConnector

    counts: dict[str, int] = {}
    with DatabaseConnector().connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            'SELECT table_name FROM information_schema.tables '
            'WHERE table_schema = %s AND table_type = %s ORDER BY table_name',
            (creds['database'], 'BASE TABLE'))
        tables = [row[0] for row in cursor.fetchall()]
        for table in tables:
            cursor.execute(f'SELECT COUNT(*) FROM {quote_identifier(table)}')  # noqa: S608
            counts[table] = int(cursor.fetchone()[0])
    return counts


def prune(destination: Path, retention_days: int, now: datetime) -> list[Path]:
    """Remove only what this job wrote, matched by its own prefix.

    The destination may be a shared mount holding other people's files, so this
    never globs the directory blindly.
    """
    removed: list[Path] = []
    daily_cutoff = now - timedelta(days=retention_days)
    monthly_cutoff = now - timedelta(days=MONTHLY_RETENTION_MONTHS * 31)
    for path in sorted(destination.iterdir()):
        if not path.is_file() or not path.name.endswith(SUFFIX):
            continue
        if path.name.startswith(MONTHLY_PREFIX):
            stamp = _parse_monthly(path.name)
            cutoff = monthly_cutoff
        elif path.name.startswith(DAILY_PREFIX):
            stamp = _parse_daily(path.name)
            cutoff = daily_cutoff
        else:
            continue
        if stamp is not None and stamp < cutoff:
            path.unlink()
            removed.append(path)
    return removed


def _parse_daily(name: str) -> datetime | None:
    stem = name[len(DAILY_PREFIX):-len(SUFFIX)]
    try:
        return datetime.strptime(stem, '%Y%m%d_%H%M%S').replace(tzinfo=UTC)
    except ValueError:
        return None


def _parse_monthly(name: str) -> datetime | None:
    stem = name[len(MONTHLY_PREFIX):-len(SUFFIX)]
    try:
        return datetime.strptime(stem, '%Y%m').replace(tzinfo=UTC)
    except ValueError:
        return None


def promote_monthly(backup: Path, now: datetime) -> Path | None:
    """On the first of the month, copy today's backup into the monthly series.

    A copy and not a rename: the daily series has to stay contiguous inside its
    own retention window.
    """
    if now.day != 1:
        return None
    target = backup.parent / f'{MONTHLY_PREFIX}{now:%Y%m}{SUFFIX}'
    if target.exists():
        return target
    target.write_bytes(backup.read_bytes())
    return target


def write_latest(destination: Path, backup: Path, started: datetime,
                 finished: datetime, counts: dict[str, int]) -> Path:
    payload = {
        'file': backup.name,
        'finished_at': finished.isoformat(),
        'bytes': backup.stat().st_size,
        'duration_seconds': round((finished - started).total_seconds(), 1),
        'database': os.getenv('DB_DB', ''),
        'tables': len(counts),
        'row_counts': counts,
    }
    target = destination / LATEST_NAME
    target.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return target


def read_latest(destination: Path) -> dict:
    target = destination / LATEST_NAME
    if not target.exists():
        raise BackupError(f'{target} does not exist; no backup has ever completed here')
    return json.loads(target.read_text())


def check_stale(destination: Path, hours: int, now: datetime) -> str | None:
    """Return a reason when the newest backup is too old, else None.

    This shares a blind spot with whatever schedules it: a timer that stops
    firing produces no failures, so it also produces no staleness alert. That is
    why music-manager exposes the same answer over /health/backup, where an
    Uptime Kuma check watching from outside the host does not depend on anything
    on it still running.
    """
    latest = read_latest(destination)
    finished = datetime.fromisoformat(latest['finished_at'])
    age_hours = (now - finished).total_seconds() / 3600
    if age_hours > hours:
        return (f'newest backup {latest["file"]} finished {age_hours:.1f} hours ago, '
                f'over the {hours} hour limit')
    return None


def run_backup(argv_destination: str | None = None) -> int:
    destination = resolve_destination(
        argv_destination or os.getenv('BACKUP_PATH', ''), os.getenv('DATA_PATH'))
    retention = int(os.getenv('BACKUP_RETENTION_DAYS', str(DEFAULT_RETENTION_DAYS)))
    creds = _credentials()
    if not creds['database']:
        raise BackupError('DB_DB is not set, so there is nothing to dump')

    started = datetime.now(UTC)
    backup = destination / f'{DAILY_PREFIX}{started:%Y%m%d_%H%M%S}{SUFFIX}'
    try:
        dump(backup, creds)
        verify(backup)
    except BackupError:
        # A partial file is a trap for whoever restores under pressure.
        backup.unlink(missing_ok=True)
        raise

    finished = datetime.now(UTC)
    counts = row_counts(creds)
    write_latest(destination, backup, started, finished, counts)
    promoted = promote_monthly(backup, finished)
    removed = prune(destination, retention, finished)

    print(f'backup: {backup} ({backup.stat().st_size} bytes, '
          f'{(finished - started).total_seconds():.0f}s, {len(counts)} tables)')
    if promoted:
        print(f'promoted to monthly: {promoted.name}')
    for path in removed:
        print(f'pruned: {path.name}')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--destination', help='override BACKUP_PATH')
    parser.add_argument('--check-destination', action='store_true',
                        help='validate the destination and exit without dumping')
    parser.add_argument('--check-stale', action='store_true',
                        help='alert when the newest backup is older than the limit')
    parser.add_argument('--stale-hours', type=int,
                        default=int(os.getenv('BACKUP_STALE_AFTER_HOURS',
                                              str(DEFAULT_STALE_AFTER_HOURS))))
    args = parser.parse_args(argv)

    try:
        if args.check_destination:
            dest = resolve_destination(
                args.destination or os.getenv('BACKUP_PATH', ''), os.getenv('DATA_PATH'))
            print(f'destination ok: {dest}')
            return 0
        if args.check_stale:
            dest = resolve_destination(
                args.destination or os.getenv('BACKUP_PATH', ''), os.getenv('DATA_PATH'))
            reason = check_stale(dest, args.stale_hours, datetime.now(UTC))
            if reason:
                alert('Database backup is stale', reason)
                print(reason, file=sys.stderr)
                return 1
            print('backup is current')
            return 0
        return run_backup(args.destination)
    except BackupError as exc:
        alert('Database backup failed', str(exc))
        print(f'db_backup: {exc}', file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - the job must alert on anything
        alert('Database backup failed', f'{type(exc).__name__}: {exc}')
        print(f'db_backup: unexpected {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
