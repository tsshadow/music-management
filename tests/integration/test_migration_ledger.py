"""The deploy's migration ledger and lock timeout, against a real MariaDB (bug report 068).

tools/test_apply_migrations.py proves the decisions against a fake client. This proves the
two things only a server can: that the ledger round-trips through schema_migrations (a
second pass skips, a modified file runs again), and that ``lock_wait_timeout`` really turns
a statement queued behind another session's metadata lock into an error -- with the holder
in the report -- instead of the endless wait that hung the 0.73.1 deploy.

The runner here speaks pymysql rather than piping into the `mariadb` client (the tooling
container has no client). The e2e stack (scripts/lib/e2e-stack.sh) runs the same helper
through the real client, twice, the way a deploy does.
"""

from __future__ import annotations

from pathlib import Path

import pymysql
import pytest

from tests.integration.conftest import _connect, _split_statements
from tools import apply_migrations as am

pytestmark = pytest.mark.integration

PROBE = 'ledger_probe'


def _runner(sql: str) -> am.SqlResult:
    """Run SQL in a session of its own, answering the way the client's batch mode does."""
    connection = _connect()
    lines: list[str] = []
    try:
        with connection.cursor(pymysql.cursors.Cursor) as cursor:
            for statement in _split_statements(sql):
                cursor.execute(statement)
                if cursor.description:
                    lines.append('\t'.join(column[0] for column in cursor.description))
                    lines.extend('\t'.join('' if v is None else str(v) for v in row) for row in cursor.fetchall())
    except pymysql.err.MySQLError as exc:
        return am.SqlResult(1, '\n'.join(lines), f'ERROR {exc.args[0]}: {exc.args[1]}')
    finally:
        connection.close()
    return am.SqlResult(0, '\n'.join(lines) + '\n', '')


@pytest.fixture
def probe(db):
    """A scratch table for the migrations below, dropped again afterwards."""
    with db.cursor() as cursor:
        cursor.execute(f'CREATE TABLE IF NOT EXISTS {PROBE} (id INT PRIMARY KEY)')
    yield PROBE
    with db.cursor() as cursor:
        cursor.execute(f'DROP TABLE IF EXISTS {PROBE}')


def _write(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(body, encoding='utf-8')
    return path


def _ledger(db) -> dict[str, str]:
    with db.cursor() as cursor:
        cursor.execute('SELECT filename, sha256 FROM schema_migrations')
        return {row['filename']: row['sha256'] for row in cursor.fetchall()}


def test_the_second_pass_skips_through_the_ledger_and_a_modified_file_runs_again(db, probe, tmp_path, capsys):
    paths = [
        _write(tmp_path, 'migrate_v10_probe.sql', f'ALTER TABLE {probe} ADD COLUMN IF NOT EXISTS a INT;\n'),
        _write(tmp_path, 'migrate_v2_probe.sql', f'INSERT IGNORE INTO {probe} (id) VALUES (1);\n'),
    ]

    applied = am.apply_all(_runner, paths, lock_wait_seconds=5)
    assert [m.name for m in applied] == ['migrate_v10_probe.sql', 'migrate_v2_probe.sql']
    assert _ledger(db) == {p.name: am.file_sha256(p) for p in paths}

    assert am.apply_all(_runner, paths, lock_wait_seconds=5) == []
    assert '0 applied, 2 skipped' in capsys.readouterr().out

    _write(tmp_path, 'migrate_v2_probe.sql', f'INSERT IGNORE INTO {probe} (id) VALUES (1), (2);\n')
    applied = am.apply_all(_runner, paths, lock_wait_seconds=5)
    assert [(m.name, m.reason) for m in applied] == [('migrate_v2_probe.sql', 'changed')]
    assert _ledger(db)['migrate_v2_probe.sql'] == am.file_sha256(paths[1])
    with db.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(*) AS n FROM {probe}')
        assert cursor.fetchone()['n'] == 2


def test_a_migration_behind_a_metadata_lock_times_out_and_names_the_holder(db, probe, tmp_path):
    migration = _write(tmp_path, 'migrate_v29_probe.sql', f'ALTER TABLE {probe} ADD COLUMN IF NOT EXISTS held INT;\n')
    # The incident's shape: a session reading the table, its transaction still open, holds
    # a shared metadata lock the ALTER's exclusive one has to wait for.
    holder = _connect()
    holder_id = holder.thread_id()
    try:
        with holder.cursor() as cursor:
            cursor.execute('START TRANSACTION')
            cursor.execute(f'SELECT COUNT(*) FROM {probe}')
        with pytest.raises(am.MigrationFailed) as caught:
            am.apply_all(_runner, [migration], lock_wait_seconds=2)
    finally:
        holder.rollback()
        holder.close()

    message = str(caught.value)
    assert 'migrate_v29_probe.sql waited more than 2s for a lock' in message
    assert 'Sessions on the database server' in message
    assert f'\n{holder_id} ' in message, message
    assert 'migrate_v29_probe.sql' not in _ledger(db)
