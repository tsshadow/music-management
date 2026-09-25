"""Unit tests for tools/apply_migrations.py: the deploy's migration ledger and lock timeout (bug report 068)."""

from __future__ import annotations

import hashlib
import io
import re
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools import apply_migrations as am

ROOT = Path(__file__).resolve().parents[1]


class FakeClient:
    """Stands in for the mariadb client: records every batch and answers the helper's own queries."""

    def __init__(self, ledger: dict[str, str] | None = None, fail_on: str | None = None, stderr: str = ''):
        self.ledger = dict(ledger or {})
        self.fail_on = fail_on
        self.stderr = stderr
        self.batches: list[str] = []
        self.ledger_readable = True
        self.record_fails = False
        self.processlist_needs_process = False

    def __call__(self, sql: str) -> am.SqlResult:
        self.batches.append(sql)
        if "SELECT 'ledger'" in sql:
            if not self.ledger_readable:
                return am.SqlResult(1, '', 'ERROR 1142 (42000): CREATE command denied')
            rows = ''.join(f'ledger\t{name}\t{digest}\n' for name, digest in self.ledger.items())
            return am.SqlResult(0, f'kind\tfilename\tsha256\n{rows}', '')
        if 'information_schema.PROCESSLIST' in sql:
            if 'INNODB_TRX' in sql and self.processlist_needs_process:
                return am.SqlResult(1, '', 'ERROR 1227 (42000): Access denied; you need the PROCESS privilege')
            return am.SqlResult(
                0,
                'kind\tID\tUSER\n'
                'proc\t42\tmuma-readonly\t18000\tQuery\tSending data\t2026-09-24 21:46:01\t'
                'SELECT COUNT(*) FROM tagger_processed_files t JOIN library_media_files m\n'
                "proc\t43\troot\t5\tQuery\tStarting\t\tALTER USER x IDENTIFIED BY 'hunter2'\n",
                '',
            )
        if sql.startswith(f'INSERT INTO {am.LEDGER_TABLE}'):
            if self.record_fails:
                return am.SqlResult(1, '', 'ERROR 2013: Lost connection')
            name, digest = re.findall(r"'([^']*)'", sql)[:2]
            self.ledger[name] = digest
            return am.SqlResult(0, '', '')
        if self.fail_on and self.fail_on in sql:
            return am.SqlResult(1, '', self.stderr)
        return am.SqlResult(0, '', '')

    def migrations_run(self) -> list[str]:
        """The batches that were migrations, i.e. carried the lock prelude."""
        return [batch for batch in self.batches if batch.startswith('SET SESSION lock_wait_timeout')]


class MigrationsTestCase(unittest.TestCase):
    """Writes a handful of migrate_*.sql files into a temporary directory."""

    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        for name, body in {
            'migrate_v10_audio.sql': 'ALTER TABLE a ADD COLUMN IF NOT EXISTS x INT;\n',
            'migrate_v2.sql': 'CREATE TABLE IF NOT EXISTS b (id INT);\n',
            'migrate_v29_processed_mtime_double.sql': 'ALTER TABLE tagger_processed_files MODIFY COLUMN mtime DOUBLE;\n',
        }.items():
            (self.dir / name).write_text(body, encoding='utf-8')
        # Byte-wise name order, as main() sorts them: v10 before v2 before v29.
        self.paths = sorted(self.dir.glob('migrate_*.sql'))

    def digest(self, name: str) -> str:
        return hashlib.sha256((self.dir / name).read_bytes()).hexdigest()

    def apply(self, client: FakeClient, **kwargs) -> tuple[list[am.Migration], str]:
        out = io.StringIO()
        with redirect_stdout(out):
            applied = am.apply_all(client, self.paths, **kwargs)
        return applied, out.getvalue()


class PlanTest(MigrationsTestCase):
    def test_a_recorded_file_with_the_same_hash_is_skipped(self) -> None:
        ledger = {'migrate_v2.sql': self.digest('migrate_v2.sql')}
        reasons = {m.name: m.reason for m in am.plan(self.paths, ledger)}
        self.assertEqual(reasons['migrate_v2.sql'], 'recorded')

    def test_a_recorded_file_whose_content_changed_runs_again(self) -> None:
        reasons = {m.name: m.reason for m in am.plan(self.paths, {'migrate_v2.sql': '0' * 64})}
        self.assertEqual(reasons['migrate_v2.sql'], 'changed')

    def test_an_unrecorded_file_runs(self) -> None:
        reasons = {m.name: m.reason for m in am.plan(self.paths, {})}
        self.assertEqual(set(reasons.values()), {'new'})

    def test_no_ledger_at_all_runs_everything(self) -> None:
        self.assertTrue(all(m.runs for m in am.plan(self.paths, None)))

    def test_the_given_order_is_kept(self) -> None:
        names = [m.name for m in am.plan(self.paths, {})]
        self.assertEqual(names, ['migrate_v10_audio.sql', 'migrate_v2.sql', 'migrate_v29_processed_mtime_double.sql'])


class ApplyAllTest(MigrationsTestCase):
    def test_the_first_pass_runs_and_records_everything_the_second_skips_it(self) -> None:
        client = FakeClient()
        applied, _ = self.apply(client)
        self.assertEqual(len(applied), 3)
        self.assertEqual(client.ledger, {p.name: self.digest(p.name) for p in self.paths})

        again = FakeClient(ledger=client.ledger)
        applied, output = self.apply(again)
        self.assertEqual(applied, [])
        self.assertEqual(again.migrations_run(), [])
        self.assertIn('Skipping 3 migration(s)', output)
        self.assertIn('0 applied, 3 skipped', output)

    def test_a_modified_file_runs_again_and_its_new_hash_is_recorded(self) -> None:
        ledger = {p.name: self.digest(p.name) for p in self.paths}
        (self.dir / 'migrate_v2.sql').write_text('CREATE TABLE IF NOT EXISTS b (id BIGINT);\n', encoding='utf-8')
        client = FakeClient(ledger=ledger)
        applied, output = self.apply(client)
        self.assertEqual([m.name for m in applied], ['migrate_v2.sql'])
        self.assertIn('migrate_v2.sql (changed)', output)
        self.assertEqual(client.ledger['migrate_v2.sql'], self.digest('migrate_v2.sql'))

    def test_every_migration_runs_under_the_lock_timeout(self) -> None:
        client = FakeClient()
        self.apply(client, lock_wait_seconds=7)
        for batch in client.migrations_run():
            first_line = batch.splitlines()[0]
            self.assertEqual(first_line, 'SET SESSION lock_wait_timeout = 7; SET SESSION innodb_lock_wait_timeout = 7;')
        self.assertTrue(client.migrations_run()[0].endswith((self.dir / 'migrate_v10_audio.sql').read_text()))

    def test_an_unreadable_ledger_means_everything_runs(self) -> None:
        client = FakeClient(ledger={p.name: self.digest(p.name) for p in self.paths})
        client.ledger_readable = False
        applied, output = self.apply(client)
        self.assertEqual(len(applied), 3)
        self.assertIn('could not read schema_migrations', output)

    def test_ignoring_the_ledger_runs_everything(self) -> None:
        client = FakeClient(ledger={p.name: self.digest(p.name) for p in self.paths})
        applied, _ = self.apply(client, use_ledger=False)
        self.assertEqual(len(applied), 3)

    def test_a_failed_record_is_a_warning_not_a_failure(self) -> None:
        client = FakeClient()
        client.record_fails = True
        applied, output = self.apply(client)
        self.assertEqual(len(applied), 3)
        self.assertIn('applied but could not be recorded', output)


class FailureTest(MigrationsTestCase):
    LOCK_ERROR = 'ERROR 1205 (HY000) at line 2: Lock wait timeout exceeded; try restarting transaction'

    def test_a_lock_timeout_names_the_file_and_prints_the_processlist(self) -> None:
        client = FakeClient(fail_on='MODIFY COLUMN mtime', stderr=self.LOCK_ERROR)
        with self.assertRaises(am.MigrationFailed) as caught:
            self.apply(client, lock_wait_seconds=120)
        message = str(caught.exception)
        self.assertIn('migrate_v29_processed_mtime_double.sql waited more than 120s for a lock', message)
        self.assertIn('KILL QUERY', message)
        # Line 2 of prelude + file is line 1 of the file.
        self.assertIn('at line 1: Lock wait timeout exceeded', message)
        self.assertIn('Sessions on the database server', message)
        self.assertRegex(message, r'42\s+muma-readonly\s+18000\s+Query\s+Sending data\s+2026-09-24 21:46:01')
        self.assertIn('SELECT COUNT(*) FROM tagger_processed_files', message)
        self.assertNotIn('hunter2', message)
        self.assertIn('statement mentions a credential', message)
        self.assertNotIn('migrate_v29_processed_mtime_double.sql', client.ledger)

    def test_nothing_after_a_failed_file_runs(self) -> None:
        client = FakeClient(fail_on='ADD COLUMN IF NOT EXISTS x', stderr='ERROR 1064 (42000) at line 2: syntax')
        with self.assertRaises(am.MigrationFailed) as caught:
            self.apply(client)
        self.assertEqual(len(client.migrations_run()), 1)
        self.assertIn('Error: migrate_v10_audio.sql failed.', str(caught.exception))
        self.assertEqual(client.ledger, {})

    def test_without_process_privilege_the_processlist_falls_back(self) -> None:
        client = FakeClient(fail_on='MODIFY COLUMN mtime', stderr=self.LOCK_ERROR)
        client.processlist_needs_process = True
        with self.assertRaises(am.MigrationFailed) as caught:
            self.apply(client)
        self.assertIn('muma-readonly', str(caught.exception))

    def test_an_unreadable_processlist_says_why(self) -> None:
        def run(sql: str) -> am.SqlResult:
            return am.SqlResult(1, '', 'ERROR 2006: gone away')

        self.assertIn('could not read the processlist: ERROR 2006', am.processlist_report(run))

    def test_an_empty_processlist(self) -> None:
        self.assertEqual(am.processlist_report(lambda sql: am.SqlResult(0, 'kind\tID\n', '')), '(no other sessions)')


class HelpersTest(unittest.TestCase):
    def test_line_numbers_count_the_file_not_the_prelude(self) -> None:
        self.assertEqual(am.translate_line_numbers('ERROR 1 at line 5: x'), 'ERROR 1 at line 4: x')
        self.assertEqual(am.translate_line_numbers('ERROR 1 at line 1: x'), 'ERROR 1 at line 1: x')

    def test_record_sql_refuses_anything_but_a_migration_name_and_digest(self) -> None:
        with self.assertRaises(ValueError):
            am.record_sql(am.Migration(Path("migrate_x'; DROP TABLE t; --.sql"), '0' * 64, 'new'))
        with self.assertRaises(ValueError):
            am.record_sql(am.Migration(Path('migrate_x.sql'), 'not-a-digest', 'new'))

    def test_the_ledger_ddl_matches_db_init_and_the_migration(self) -> None:
        def normalise(sql: str) -> str:
            lines = [line.split('--', 1)[0] for line in sql.splitlines()]
            return ' '.join(' '.join(lines).split()).rstrip(';').strip()

        db_init = (ROOT / 'services/common/db_init.py').read_text(encoding='utf-8')
        match = re.search(r"'schema_migrations': '(.*?)',\n", db_init)
        assert match is not None
        from_db_init = match.group(1).encode().decode('unicode_escape')
        migration = (ROOT / 'migrate_v39_schema_migrations.sql').read_text(encoding='utf-8')
        self.assertEqual(normalise(am.LEDGER_DDL), normalise(from_db_init))
        self.assertEqual(normalise(am.LEDGER_DDL), normalise(migration))


class MainTest(unittest.TestCase):
    def test_the_password_leads_every_batch_and_never_reaches_the_command(self) -> None:
        with TemporaryDirectory() as tmp:
            migration = Path(tmp) / 'migrate_v1.sql'
            migration.write_text('SELECT 1;\n', encoding='utf-8')
            log = Path(tmp) / 'batches'
            command = f'{{ cat; echo "<end>"; }} >> {log}'
            with patch('sys.stdin', io.StringIO('s3cr#t pw\n')), redirect_stdout(io.StringIO()):
                self.assertEqual(am.main(['--password-stdin', '--exec', command, str(migration)]), 0)
            batches = log.read_text(encoding='utf-8').split('<end>\n')[:-1]
            # Ledger read, the migration, its record.
            self.assertEqual(len(batches), 3)
            self.assertTrue(all(batch.startswith('s3cr#t pw\n') for batch in batches))
            self.assertIn('SELECT 1;', batches[1])

    def test_files_run_in_byte_order_whatever_order_they_are_given_in(self) -> None:
        with TemporaryDirectory() as tmp:
            names = ['migrate_v29_x.sql', 'migrate_v2.sql', 'migrate_v10_y.sql']
            for name in names:
                (Path(tmp) / name).write_text(f'SELECT "{name}";\n', encoding='utf-8')
            log = Path(tmp) / 'batches'
            with redirect_stdout(io.StringIO()):
                am.main(['--exec', f'cat >> {log}', *(str(Path(tmp) / name) for name in names)])
            ran = re.findall(r'SELECT "(migrate_[^"]+)"', log.read_text(encoding='utf-8'))
            self.assertEqual(ran, ['migrate_v10_y.sql', 'migrate_v2.sql', 'migrate_v29_x.sql'])

    def test_a_failure_exits_non_zero_with_the_report_on_stderr(self) -> None:
        with TemporaryDirectory() as tmp:
            migration = Path(tmp) / 'migrate_v1.sql'
            migration.write_text('SELECT 1;\n', encoding='utf-8')
            command = (
                'if grep -q "SELECT 1"; then echo "ERROR 1205 (HY000) at line 2: Lock wait timeout" >&2; exit 1; fi'
            )
            err = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                self.assertEqual(am.main(['--exec', command, '--lock-wait-timeout', '3', str(migration)]), 1)
            self.assertIn('migrate_v1.sql waited more than 3s for a lock', err.getvalue())


if __name__ == '__main__':
    unittest.main()
