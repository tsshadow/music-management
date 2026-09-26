#!/usr/bin/env python3
"""Apply the repository's migrate_*.sql files the way a deploy does, with a ledger and a lock timeout.

scripts/deploy.sh calls this for step [4/6]. It used to loop over every file in bash and
pipe each one into the `mariadb` client; two things went wrong with that on 2026-09-25
(docs/bug-reports/068-deploy-hangs-on-no-op-alter-metadata-lock.md):

- **A blocked statement waited forever.** A no-op ``ALTER TABLE ... MODIFY`` queued for a
  table metadata lock behind a five-hour diagnostic ``SELECT``; the server's default
  ``lock_wait_timeout`` is a year, so the client sat there until the CI job's one-hour
  timeout killed it, and the ALTER stayed queued server-side, freezing every later write to
  the table. Every file now runs with ``lock_wait_timeout`` and
  ``innodb_lock_wait_timeout`` set for its session (120 s by default), so a blocked
  statement errors, the deploy stops before ``up`` while the old containers still serve,
  and the sessions on the server are printed so the holder is visible at once.
- **Every file ran on every deploy.** Harmless while each is re-runnable, until a no-op
  ALTER needs an exclusive lock it does not need to take. The ``schema_migrations`` table
  records each file's name and the sha256 of its content once it has applied; a file whose
  name and hash are recorded is skipped. A changed file (new hash) runs again, as does
  anything unrecorded. The ledger is an optimisation, not a correctness dependency: every
  migration stays re-runnable, and a ledger that cannot be read means "run everything".

The files run in byte-wise lexical order of their names, whatever order they were given
in: ``migrate_v10_...`` before ``migrate_v2.sql``, and ``migrate_v2.sql`` before
``migrate_v29_...``. Sorted here rather than left to bash, whose glob order follows the
runner's locale -- under en_US.UTF-8 ``migrate_v29_...`` sorts *before* ``migrate_v2.sql``,
under C after it. Byte order is also what Python's ``sorted()`` and so the integration suite
use. The version number is therefore not an order: no migration may rely on a
higher-numbered one having run first.

How SQL reaches the database is the caller's business: ``--exec`` is a shell command that
reads SQL on stdin and prints the client's batch output (tab-separated, one header line).
deploy.sh passes a function that pipes it over ssh into ``docker exec ... mariadb``; the
end-to-end stack passes a plain ``docker exec``. With ``--password-stdin`` the first line
of this program's stdin is a password, handed on as the first line of every command's
stdin -- the same protocol deploy.sh's remote command already reads -- so it never appears
on a command line. This module is standard library only: it runs on the CI runner, not in
an image.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

LEDGER_TABLE = 'schema_migrations'

# Kept identical to the entry in services/common/db_init.py and to
# migrate_v39_schema_migrations.sql (tools/test_apply_migrations.py compares them). It is
# created here as well because the first deploy after this change reads the ledger before
# the new music-manager -- and with it db_init -- has ever started.
LEDGER_DDL = """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename VARCHAR(255) NOT NULL PRIMARY KEY,
                sha256 CHAR(64) NOT NULL,
                applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """

DEFAULT_LOCK_WAIT_SECONDS = 120

# How many sessions the failure report lists, oldest first.
PROCESSLIST_LIMIT = 50
INFO_WIDTH = 100

# The report goes to a CI log. A statement that carries a credential is not printed.
_CREDENTIAL_RE = re.compile(r'identified|password', re.IGNORECASE)
_LOCK_TIMEOUT_RE = re.compile(r'ERROR 1205\b|Lock wait timeout exceeded', re.IGNORECASE)
_LINE_RE = re.compile(r'\bat line (\d+)')
_HASH_RE = re.compile(r'^[0-9a-f]{64}$')
_NAME_RE = re.compile(r'^migrate_[A-Za-z0-9_.-]+\.sql$')


@dataclass(frozen=True)
class SqlResult:
    """What one run of the SQL client returned."""

    returncode: int
    stdout: str
    stderr: str


# Runs one batch of SQL in a session of its own and returns the client's result.
SqlRunner = Callable[[str], SqlResult]


@dataclass(frozen=True)
class Migration:
    """One migrate_*.sql file and the reason it runs or is skipped."""

    path: Path
    sha256: str
    reason: str  # 'new', 'changed' or 'recorded'

    @property
    def name(self) -> str:
        """The file name, which is the ledger key."""
        return self.path.name

    @property
    def runs(self) -> bool:
        """Whether this file has to be applied."""
        return self.reason != 'recorded'


class MigrationFailed(Exception):
    """A migration exited non-zero; the message says which one and why."""


def file_sha256(path: Path) -> str:
    """The sha256 of the file's bytes, as the ledger stores it."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lock_prelude(seconds: int) -> str:
    """The session settings every migration runs under, on a single line.

    One line on purpose: the client reports errors by line, and translate_line_numbers()
    only has to subtract one.
    """
    return f'SET SESSION lock_wait_timeout = {int(seconds)}; SET SESSION innodb_lock_wait_timeout = {int(seconds)};\n'


def translate_line_numbers(text: str) -> str:
    """Rewrite the client's `at line N` so N counts lines of the file, not of file plus prelude."""
    return _LINE_RE.sub(lambda match: f'at line {max(int(match.group(1)) - 1, 1)}', text)


def _rows(stdout: str, kind: str) -> list[list[str]]:
    """The data rows of a batch-mode result whose first column is the literal KIND.

    The header line carries the column *name* ("kind"), so it never matches.
    """
    rows = []
    for line in stdout.splitlines():
        fields = line.split('\t')
        if fields and fields[0] == kind:
            rows.append(fields[1:])
    return rows


def read_ledger(run: SqlRunner) -> dict[str, str] | None:
    """Filename -> sha256 of every recorded migration, or None when it cannot be read.

    Creates the table first, so the first deploy after this change finds an empty ledger
    rather than an error.
    """
    sql = f"{LEDGER_DDL.strip()};\nSELECT 'ledger' AS kind, filename, sha256 FROM {LEDGER_TABLE};\n"
    result = run(sql)
    if result.returncode != 0:
        print(f'WARNING: could not read {LEDGER_TABLE}, applying every migration: {result.stderr.strip()}')
        return None
    return {row[0]: row[1] for row in _rows(result.stdout, 'ledger') if len(row) >= 2}


def plan(paths: Sequence[Path], ledger: dict[str, str] | None) -> list[Migration]:
    """Decide, per file and in the given order, whether it runs.

    Recorded with the same hash: skipped. Recorded with another hash: runs ('changed').
    Not recorded, or no ledger at all: runs ('new').
    """
    migrations = []
    for path in paths:
        digest = file_sha256(path)
        recorded = (ledger or {}).get(path.name)
        if recorded is None:
            reason = 'new'
        elif recorded == digest:
            reason = 'recorded'
        else:
            reason = 'changed'
        migrations.append(Migration(path=path, sha256=digest, reason=reason))
    return migrations


def record_sql(migration: Migration) -> str:
    """The INSERT that records MIGRATION as applied.

    The values are interpolated, so both are checked to be exactly what they claim: a
    migrate_*.sql name and a hex digest. Neither can carry a quote.
    """
    if not _NAME_RE.match(migration.name) or not _HASH_RE.match(migration.sha256):
        raise ValueError(f'refusing to record {migration.name!r}: not a migration file name')
    return (
        f"INSERT INTO {LEDGER_TABLE} (filename, sha256, applied_at) "
        f"VALUES ('{migration.name}', '{migration.sha256}', NOW()) "
        "ON DUPLICATE KEY UPDATE sha256 = VALUES(sha256), applied_at = VALUES(applied_at);\n"
    )


def _processlist_sql(with_transactions: bool) -> str:
    """Every other session, oldest first, the statement cut to INFO_WIDTH characters.

    With WITH_TRANSACTIONS the start of each session's open InnoDB transaction is joined in:
    a session idle ("Sleep") inside a transaction still holds its metadata locks, and that
    column is what gives it away. Reading INNODB_TRX needs the PROCESS privilege.
    """
    info = f"IFNULL(LEFT(REPLACE(REPLACE(p.INFO, CHAR(10), ' '), CHAR(9), ' '), {INFO_WIDTH}), '')"
    trx = "IFNULL(t.trx_started, '')" if with_transactions else "''"
    join = ' LEFT JOIN information_schema.INNODB_TRX t ON t.trx_mysql_thread_id = p.ID' if with_transactions else ''
    return (
        f"SELECT 'proc' AS kind, p.ID, p.USER, p.TIME, p.COMMAND, IFNULL(p.STATE, ''), {trx}, {info} "
        f'FROM information_schema.PROCESSLIST p{join} '
        f'WHERE p.ID <> CONNECTION_ID() ORDER BY p.TIME DESC LIMIT {PROCESSLIST_LIMIT};\n'
    )


def processlist_report(run: SqlRunner) -> str:
    """The server's sessions as a small table, or why they could not be read."""
    result = run(_processlist_sql(with_transactions=True))
    if result.returncode != 0:
        result = run(_processlist_sql(with_transactions=False))
    if result.returncode != 0:
        return f'(could not read the processlist: {result.stderr.strip()})'
    header = ['Id', 'User', 'Time', 'Command', 'State', 'Trx started', 'Info']
    rows = []
    for fields in _rows(result.stdout, 'proc'):
        fields = (fields + [''] * len(header))[: len(header)]
        if _CREDENTIAL_RE.search(fields[6]):
            fields[6] = '[statement mentions a credential; not printed]'
        fields[6] = fields[6][:INFO_WIDTH]
        rows.append(fields)
    if not rows:
        return '(no other sessions)'
    widths = [max(len(header[i]), *(len(row[i]) for row in rows)) for i in range(len(header) - 1)]
    lines = []
    for row in [header, *rows]:
        cells = [row[i].ljust(widths[i]) for i in range(len(header) - 1)]
        lines.append('  '.join([*cells, row[-1]]).rstrip())
    return '\n'.join(lines)


def apply_migration(run: SqlRunner, migration: Migration, lock_wait_seconds: int) -> None:
    """Run one file under the lock timeout; raise MigrationFailed naming it on any error."""
    sql = lock_prelude(lock_wait_seconds) + migration.path.read_text(encoding='utf-8')
    result = run(sql)
    if result.stdout.strip():
        print(result.stdout.rstrip())
    if result.returncode == 0:
        return
    detail = translate_line_numbers(result.stderr.strip()) or f'client exited {result.returncode}'
    if _LOCK_TIMEOUT_RE.search(result.stderr):
        headline = (
            f'Error: {migration.name} waited more than {lock_wait_seconds}s for a lock and was aborted. '
            'Another session holds a lock on a table it touches -- usually the oldest session below '
            'that reads or writes the same table. Find it, `KILL QUERY <Id>` it (or wait for it), '
            'then retry the job; see docs/deployment.md#when-a-deploy-stops-on-a-lock-wait.'
        )
    else:
        headline = f'Error: {migration.name} failed.'
    raise MigrationFailed(
        f'{headline}\n{detail}\n'
        'Nothing after it was applied and no container was recreated; the previous release keeps serving.\n'
        f'Sessions on the database server:\n{processlist_report(run)}'
    )


def apply_all(
    run: SqlRunner, paths: Sequence[Path], lock_wait_seconds: int = DEFAULT_LOCK_WAIT_SECONDS, use_ledger: bool = True
) -> list[Migration]:
    """Apply what the ledger does not already hold, in order; return the ones that ran.

    Raises MigrationFailed on the first failure, so nothing after it runs.
    """
    ledger = read_ledger(run) if use_ledger else None
    migrations = plan(paths, ledger)
    skipped = [migration for migration in migrations if not migration.runs]
    if skipped:
        print(f'--- Skipping {len(skipped)} migration(s) recorded in {LEDGER_TABLE} with an unchanged hash ---')
    applied = []
    for migration in migrations:
        if not migration.runs:
            continue
        print(f'--- Executing database migration: {migration.name} ({migration.reason}) ---', flush=True)
        apply_migration(run, migration, lock_wait_seconds)
        applied.append(migration)
        recorded = run(record_sql(migration))
        if recorded.returncode != 0:
            # Not fatal: the file applied, and an unrecorded file only runs once more next time.
            print(f'WARNING: {migration.name} applied but could not be recorded: {recorded.stderr.strip()}')
    print(f'--- Migrations: {len(applied)} applied, {len(skipped)} skipped ---')
    return applied


def shell_runner(command: str, password: str | None) -> SqlRunner:
    """A runner that pipes each batch into `bash -c COMMAND`, password first when given."""

    def run(sql: str) -> SqlResult:
        stdin = sql if password is None else f'{password}\n{sql}'
        completed = subprocess.run(  # noqa: S603 - the command is the caller's, by design
            ['bash', '-c', command], input=stdin, capture_output=True, text=True, check=False
        )
        return SqlResult(completed.returncode, completed.stdout, completed.stderr)

    return run


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry point; see the module docstring."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('files', nargs='+', type=Path, help='migrate_*.sql files, applied in byte-wise name order')
    parser.add_argument('--exec', dest='command', required=True, help='shell command that runs SQL from stdin')
    parser.add_argument(
        '--password-stdin', action='store_true', help='first stdin line is a password, passed on to every command'
    )
    parser.add_argument('--lock-wait-timeout', type=int, default=DEFAULT_LOCK_WAIT_SECONDS, metavar='SECONDS')
    parser.add_argument('--ignore-ledger', action='store_true', help='apply every file (and still record them)')
    args = parser.parse_args(argv)

    password = sys.stdin.readline().rstrip('\n') if args.password_stdin else None
    files = sorted((path for path in args.files if path.is_file()), key=lambda path: path.name.encode())
    try:
        apply_all(
            shell_runner(args.command, password), files, args.lock_wait_timeout, use_ledger=not args.ignore_ledger
        )
    except MigrationFailed as exc:
        sys.stdout.flush()
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
