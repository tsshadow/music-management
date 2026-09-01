#!/usr/bin/env python3
"""Restore the newest backup into a throwaway database and check what arrived.

A backup that has never been restored is not a backup, it is a file. gzip
integrity and the ``-- Dump completed`` trailer say the file is whole; only a
restore says it is a database.

What this asserts, against the row counts ``tools/db_backup.py`` recorded next to
the dump:

- every table that was dumped exists in the restored copy, and no extra ones;
- every table that had rows still has them, within a tolerance.

The tolerance is not slack, it is arithmetic. ``mariadb-dump --single-transaction``
snapshots at its start, and the counts are read after it finishes, so an
append-heavy table like ``events`` legitimately restores with slightly fewer rows
than were recorded. A missing table, an empty one, or a file truncated halfway
all fall far outside it.

The restore goes into a second database on the same server rather than a
throwaway container: the dump carries no ``CREATE DATABASE``/``USE`` (see
db_backup.py), so the target is whatever is named here, and no Docker socket has
to be handed to anything.

Usage:
    python tools/db_restore_check.py
    python tools/db_restore_check.py --keep   # leave the restored copy in place
"""

from __future__ import annotations

import argparse
import contextlib
import gzip
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from tools.db_backup import (  # noqa: E402
    BackupError,
    _credentials,
    alert,
    quote_identifier,
    read_latest,
    resolve_destination,
)

SOURCE = 'db-restore-check'

# A table may restore with up to this fraction fewer rows than recorded without
# that meaning anything, for the snapshot-ordering reason in the docstring.
ROW_TOLERANCE = 0.98
# Below this, a percentage is meaningless: a five-row table losing one row is
# worth looking at, so small tables are compared exactly.
EXACT_BELOW_ROWS = 100


class RestoreCheckError(Exception):
    """The restored copy is not what the dump claimed to hold."""


def target_database(source_database: str) -> str:
    """Never the live database, and it must be impossible to get there by typo."""
    name = os.getenv('RESTORE_CHECK_DB', f'{source_database}_restore_check')
    if name == source_database:
        raise RestoreCheckError(f'restore target {name!r} is the live database; refusing to restore over it')
    return name


def _defaults_file(creds: dict[str, str]) -> str:
    fd, path = tempfile.mkstemp(prefix='db-restore-check-', suffix='.cnf')
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as handle:
        handle.write('[client]\n')
        handle.write(f"user={creds['user']}\n")
        handle.write(f"password={creds['password']}\n")
    return path


def _run_sql(defaults_path: str, creds: dict[str, str], sql: str, database: str | None = None) -> str:
    command = [
        'mariadb',
        f'--defaults-extra-file={defaults_path}',
        '--host',
        creds['host'],
        '--port',
        creds['port'],
        '-N',
        '-B',
    ]
    if database:
        command.append(database)
    result = subprocess.run(command, input=sql.encode('utf-8'), capture_output=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.decode('utf-8', 'replace').strip().splitlines()
        raise RestoreCheckError(f'mariadb exited {result.returncode}: {detail[-1] if detail else "no output"}')
    return result.stdout.decode('utf-8', 'replace')


def restore(defaults_path: str, creds: dict[str, str], dump_path: Path, database: str) -> None:
    """Stream the dump into the target, checking the producer's return code.

    Same shape as the dump side: decompressing in this process leaves one exit
    status to inspect instead of a pipeline whose front half can fail silently.
    """
    command = [
        'mariadb',
        f'--defaults-extra-file={defaults_path}',
        '--host',
        creds['host'],
        '--port',
        creds['port'],
        database,
    ]
    with gzip.open(dump_path, 'rb') as handle:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        assert process.stdin is not None
        try:
            for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                process.stdin.write(chunk)
        finally:
            process.stdin.close()
        _, stderr = process.communicate()
    if process.returncode != 0:
        detail = stderr.decode('utf-8', 'replace').strip().splitlines()
        raise RestoreCheckError(
            f'restoring {dump_path.name} failed with exit {process.returncode}: {detail[-1] if detail else "no output"}'
        )


def restored_counts(defaults_path: str, creds: dict[str, str], database: str) -> dict[str, int]:
    listing = _run_sql(
        defaults_path,
        creds,
        'SELECT table_name FROM information_schema.tables '
        f"WHERE table_schema = '{database}' AND table_type = 'BASE TABLE' "
        'ORDER BY table_name;',
    )
    tables = [line.strip() for line in listing.splitlines() if line.strip()]
    if not tables:
        return {}
    union = ' UNION ALL '.join(f"SELECT '{table}', COUNT(*) FROM {quote_identifier(table)}" for table in tables)
    output = _run_sql(defaults_path, creds, f'{union};', database=database)
    counts: dict[str, int] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        name, _, value = line.partition('\t')
        counts[name.strip()] = int(value.strip())
    return counts


def compare(recorded: dict[str, int], restored: dict[str, int]) -> list[str]:
    """Every way the restored copy can fail to match, as readable lines."""
    problems: list[str] = []
    missing = sorted(set(recorded) - set(restored))
    extra = sorted(set(restored) - set(recorded))
    if missing:
        problems.append(f'tables missing after restore: {", ".join(missing)}')
    if extra:
        problems.append(f'tables present that were not dumped: {", ".join(extra)}')
    for table in sorted(set(recorded) & set(restored)):
        want, got = recorded[table], restored[table]
        if want == 0:
            continue
        floor = want if want < EXACT_BELOW_ROWS else int(want * ROW_TOLERANCE)
        if got < floor:
            problems.append(f'{table}: {got} rows restored, {want} recorded (floor {floor})')
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--destination', help='override BACKUP_PATH')
    parser.add_argument('--keep', action='store_true', help='leave the restored database in place for inspection')
    args = parser.parse_args(argv)

    defaults_path = None
    database = None
    creds = _credentials()
    try:
        destination = resolve_destination(args.destination or os.getenv('BACKUP_PATH', ''), os.getenv('DATA_PATH'))
        latest = read_latest(destination)
        dump_path = destination / latest['file']
        if not dump_path.exists():
            raise RestoreCheckError(f'{latest["file"]} is named in latest.json but is not on disk')
        recorded = {name: int(count) for name, count in latest['row_counts'].items()}
        if not recorded:
            raise RestoreCheckError('latest.json records no row counts to check against')

        database = target_database(creds['database'])
        defaults_path = _defaults_file(creds)

        started = datetime.now(UTC)
        _run_sql(defaults_path, creds, f'DROP DATABASE IF EXISTS `{database}`;')
        _run_sql(
            defaults_path, creds, f'CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;'
        )
        restore(defaults_path, creds, dump_path, database)
        restored = restored_counts(defaults_path, creds, database)
        elapsed = (datetime.now(UTC) - started).total_seconds()

        problems = compare(recorded, restored)
        if problems:
            message = f'{dump_path.name} restored, but it does not match what was recorded:\n' + '\n'.join(
                f'- {line}' for line in problems
            )
            alert('Database restore check failed', message)
            print(message, file=sys.stderr)
            return 1

        total = sum(restored.values())
        print(f'restore check ok: {dump_path.name} -> {database}, {len(restored)} tables, {total} rows, {elapsed:.0f}s')
        return 0
    except (RestoreCheckError, BackupError) as exc:
        alert('Database restore check failed', str(exc))
        print(f'db_restore_check: {exc}', file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - the check must alert on anything
        alert('Database restore check failed', f'{type(exc).__name__}: {exc}')
        print(f'db_restore_check: unexpected {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1
    finally:
        # The copy is ~7 GB. Leaving it behind twice fills the disk that the
        # database itself is on, which would turn a check into an outage.
        if database and defaults_path and not args.keep:
            try:
                _run_sql(defaults_path, creds, f'DROP DATABASE IF EXISTS `{database}`;')
            except Exception as exc:  # pragma: no cover - defensive
                print(f'db_restore_check: dropping {database} failed: {exc}', file=sys.stderr)
        if defaults_path:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(defaults_path)


if __name__ == '__main__':
    raise SystemExit(main())
