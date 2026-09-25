import gzip
import io
import json
import os
import stat
import subprocess
import sys
import time
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from tools import db_backup


def write_dump(path: Path, body: bytes = b'CREATE TABLE t (id INT);\n', trailer: bool = True) -> Path:
    """A gzip file that looks enough like a dump to exercise verify().

    The padding is random rather than repeated text on purpose: the size floor
    applies to the *compressed* file, and a megabyte of '-- filler' compresses to
    about two kilobytes, which would trip the floor instead of the check the test
    is aiming at.
    """
    content = body + os.urandom(db_backup.MIN_SIZE_BYTES + 1024)
    if trailer:
        content += b'\n-- Dump completed on 2026-08-31 20:00:00\n'
    with gzip.open(path, 'wb') as handle:
        handle.write(content)
    return path


class ResolveDestinationTest(unittest.TestCase):
    def test_accepts_a_writable_directory_outside_the_datadir(self):
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'backups'
            dest.mkdir()
            data = Path(tmp) / 'data'
            (data / 'mariadb').mkdir(parents=True)
            self.assertEqual(db_backup.resolve_destination(str(dest), str(data)), dest.resolve())

    def test_rejects_a_destination_inside_the_datadir(self):
        with TemporaryDirectory() as tmp:
            data = Path(tmp) / 'data'
            dest = data / 'mariadb' / 'backups'
            dest.mkdir(parents=True)
            with self.assertRaises(db_backup.BackupError) as caught:
                db_backup.resolve_destination(str(dest), str(data))
            self.assertIn('inside the MariaDB data directory', str(caught.exception))

    def test_rejects_the_datadir_reached_through_a_symlink(self):
        """A symlink is the obvious way to defeat a string comparison."""
        with TemporaryDirectory() as tmp:
            data = Path(tmp) / 'data'
            real = data / 'mariadb' / 'backups'
            real.mkdir(parents=True)
            link = Path(tmp) / 'looks-elsewhere'
            link.symlink_to(real)
            with self.assertRaises(db_backup.BackupError):
                db_backup.resolve_destination(str(link), str(data))

    def test_rejects_a_missing_destination(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(db_backup.BackupError):
                db_backup.resolve_destination(str(Path(tmp) / 'nope'), None)

    def test_rejects_an_empty_setting(self):
        with self.assertRaises(db_backup.BackupError):
            db_backup.resolve_destination('', None)


class VerifyTest(unittest.TestCase):
    def test_rejects_an_empty_dump(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'empty.sql.gz'
            path.write_bytes(b'')
            with self.assertRaises(db_backup.BackupError) as caught:
                db_backup.verify(path)
            self.assertIn('below the', str(caught.exception))

    def test_rejects_a_dump_without_the_trailer(self):
        with TemporaryDirectory() as tmp:
            path = write_dump(Path(tmp) / 'cut.sql.gz', trailer=False)
            with self.assertRaises(db_backup.BackupError) as caught:
                db_backup.verify(path)
            self.assertIn('truncated', str(caught.exception))

    def test_rejects_a_file_that_is_not_gzip(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'plain.sql.gz'
            path.write_bytes(b'x' * (db_backup.MIN_SIZE_BYTES + 1))
            with self.assertRaises(db_backup.BackupError) as caught:
                db_backup.verify(path)
            self.assertIn('does not decompress', str(caught.exception))

    def test_accepts_a_complete_dump(self):
        with TemporaryDirectory() as tmp:
            path = write_dump(Path(tmp) / 'good.sql.gz')
            db_backup.verify(path)


class DumpTest(unittest.TestCase):
    """The credentials file must never outlive the call, however it ends."""

    def _run_dump(self, returncode: int):
        seen = {}

        class FakeProcess:
            def __init__(self, *args, **kwargs):
                seen['command'] = args[0]
                self.stdout = MagicMock()
                self.stdout.read1.side_effect = [b'data', b'']
                self.returncode = returncode

            def communicate(self):
                return b'', b'ERROR 1045: Access denied\n'

        with TemporaryDirectory() as tmp:
            target = Path(tmp) / 'out.sql.gz'
            original_mkstemp = db_backup.tempfile.mkstemp

            def spy_mkstemp(*args, **kwargs):
                fd, path = original_mkstemp(*args, **kwargs)
                seen['defaults'] = path
                return fd, path

            with (
                patch.object(db_backup.tempfile, 'mkstemp', spy_mkstemp),
                patch.object(db_backup.subprocess, 'Popen', FakeProcess),
            ):
                creds = {'host': 'db', 'port': '3306', 'user': 'u', 'password': 'p', 'database': 'music-management'}
                seen['mode_during'] = None

                real_open = db_backup.gzip.open

                def capture_mode(*args, **kwargs):
                    seen['mode_during'] = stat.S_IMODE(os.stat(seen['defaults']).st_mode)
                    return real_open(*args, **kwargs)

                with patch.object(db_backup.gzip, 'open', capture_mode):
                    if returncode == 0:
                        db_backup.dump(target, creds)
                    else:
                        with self.assertRaises(db_backup.BackupError) as caught:
                            db_backup.dump(target, creds)
                        seen['error'] = str(caught.exception)
        return seen

    def test_credentials_file_is_private_and_removed_on_success(self):
        seen = self._run_dump(returncode=0)
        self.assertEqual(seen['mode_during'], 0o600)
        self.assertFalse(os.path.exists(seen['defaults']))

    def test_credentials_file_is_removed_when_the_dump_fails(self):
        seen = self._run_dump(returncode=2)
        self.assertFalse(os.path.exists(seen['defaults']))
        self.assertIn('Access denied', seen['error'])

    def test_password_never_reaches_the_command_line(self):
        seen = self._run_dump(returncode=0)
        self.assertNotIn('p', [arg for arg in seen['command'] if arg == 'p'])
        self.assertFalse([arg for arg in seen['command'] if '--password' in arg])


class PruneTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dest = Path(self.tmp.name)
        self.now = datetime(2026, 8, 31, 3, 0, tzinfo=UTC)

    def _touch(self, name: str) -> Path:
        path = self.dest / name
        path.write_bytes(b'x')
        return path

    def test_removes_dailies_past_the_window_and_keeps_the_rest(self):
        old = self._touch('muma_db_20260801_030000.sql.gz')
        fresh = self._touch('muma_db_20260830_030000.sql.gz')
        removed = db_backup.prune(self.dest, 14, self.now)
        self.assertEqual(removed, [old])
        self.assertTrue(fresh.exists())

    def test_monthlies_survive_the_daily_window(self):
        monthly = self._touch('muma_db_monthly_202608.sql.gz')
        db_backup.prune(self.dest, 14, self.now)
        self.assertTrue(monthly.exists())

    def test_monthlies_expire_after_six_months(self):
        stale = self._touch('muma_db_monthly_202501.sql.gz')
        recent = self._touch('muma_db_monthly_202607.sql.gz')
        removed = db_backup.prune(self.dest, 14, self.now)
        self.assertEqual(removed, [stale])
        self.assertTrue(recent.exists())

    def test_leaves_files_this_job_did_not_write(self):
        """The destination may be a shared mount holding other people's data."""
        others = [
            self._touch('muma_backup_20260101_000000.sql.gz'),
            self._touch('holiday-photos.sql.gz'),
            self._touch('latest.json'),
        ]
        db_backup.prune(self.dest, 14, self.now)
        for path in others:
            self.assertTrue(path.exists(), f'{path.name} should have been left alone')

    def test_ignores_a_name_that_does_not_carry_a_timestamp(self):
        odd = self._touch('muma_db_notadate.sql.gz')
        db_backup.prune(self.dest, 14, self.now)
        self.assertTrue(odd.exists())

    def test_the_newest_daily_survives_however_old_it_is(self):
        """Pruning runs before the dump now; after two weeks of failures it is the only backup."""
        older = self._touch('muma_db_20260701_030000.sql.gz')
        newest = self._touch('muma_db_20260702_030000.sql.gz')
        removed = db_backup.prune(self.dest, 14, self.now)
        self.assertEqual(removed, [older])
        self.assertTrue(newest.exists())

    def test_what_a_killed_run_left_half_written_is_removed(self):
        partials = [
            self._touch('muma_db_20260830_030000.sql.gz.partial'),
            self._touch('muma_db_monthly_202608.sql.gz.partial'),
        ]
        others = self._touch('someone-elses.sql.gz.partial')
        db_backup.prune(self.dest, 14, self.now)
        for path in partials:
            self.assertFalse(path.exists(), f'{path.name} should have been removed')
        self.assertTrue(others.exists())


class PromoteMonthlyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.backup = write_dump(Path(self.tmp.name) / 'muma_db_20260901_030000.sql.gz')

    def test_promotes_on_the_first(self):
        target = db_backup.promote_monthly(self.backup, datetime(2026, 9, 1, tzinfo=UTC))
        self.assertIsNotNone(target)
        self.assertEqual(target.name, 'muma_db_monthly_202609.sql.gz')
        self.assertEqual(target.read_bytes(), self.backup.read_bytes())

    def test_the_copy_is_streamed_not_read_into_memory(self):
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('read the whole dump into memory')):
            target = db_backup.promote_monthly(self.backup, datetime(2026, 9, 1, tzinfo=UTC))
        self.assertTrue(target.exists())

    def test_a_copy_that_does_not_verify_leaves_no_monthly_behind(self):
        real_copy = db_backup.shutil.copyfileobj

        def truncating_copy(source, destination, length=0):
            real_copy(source, destination, length)
            destination.truncate(1024)

        with patch.object(db_backup.shutil, 'copyfileobj', truncating_copy):
            with self.assertRaises(db_backup.BackupError):
                db_backup.promote_monthly(self.backup, datetime(2026, 9, 1, tzinfo=UTC))
        self.assertEqual(sorted(p.name for p in Path(self.tmp.name).iterdir()), [self.backup.name])

    def test_a_disk_that_fills_during_the_copy_leaves_no_monthly_behind(self):
        with patch.object(db_backup.shutil, 'copyfileobj', side_effect=OSError(28, 'No space left on device')):
            with self.assertRaises(OSError):
                db_backup.promote_monthly(self.backup, datetime(2026, 9, 1, tzinfo=UTC))
        self.assertEqual(sorted(p.name for p in Path(self.tmp.name).iterdir()), [self.backup.name])

    def test_leaves_the_daily_in_place_so_the_series_stays_contiguous(self):
        db_backup.promote_monthly(self.backup, datetime(2026, 9, 1, tzinfo=UTC))
        self.assertTrue(self.backup.exists())

    def test_does_nothing_on_any_other_day(self):
        self.assertIsNone(db_backup.promote_monthly(self.backup, datetime(2026, 9, 2, tzinfo=UTC)))


class StalenessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dest = Path(self.tmp.name)

    def _latest(self, finished: datetime):
        (self.dest / db_backup.LATEST_NAME).write_text(
            json.dumps(
                {
                    'file': 'muma_db_20260831_030000.sql.gz',
                    'finished_at': finished.isoformat(),
                }
            )
        )

    def test_silent_when_the_backup_is_recent(self):
        now = datetime(2026, 8, 31, 12, tzinfo=UTC)
        self._latest(now - timedelta(hours=5))
        self.assertIsNone(db_backup.check_stale(self.dest, 36, now))

    def test_reports_when_the_backup_is_too_old(self):
        now = datetime(2026, 8, 31, 12, tzinfo=UTC)
        self._latest(now - timedelta(hours=40))
        reason = db_backup.check_stale(self.dest, 36, now)
        self.assertIn('40.0 hours ago', reason)

    def test_a_destination_that_never_produced_a_backup_is_an_error(self):
        with self.assertRaises(db_backup.BackupError) as caught:
            db_backup.check_stale(self.dest, 36, datetime.now(UTC))
        self.assertIn('no backup has ever completed', str(caught.exception))


class AlertingTest(unittest.TestCase):
    def test_failure_pushes_synchronously_and_records_the_event(self):
        sink = MagicMock()
        with patch.object(db_backup, 'NtfySink', return_value=sink), patch.object(db_backup, 'event_service') as events:
            db_backup.alert('title', 'message')
        sink.handle.assert_called_once()
        pushed = sink.handle.call_args[0][0]
        self.assertEqual(pushed.level, 'ERROR')
        self.assertEqual(pushed.source, db_backup.SOURCE)
        events.emit.assert_called_once()

    def test_a_broken_push_does_not_stop_the_event_from_being_recorded(self):
        """The two paths fail independently on purpose."""
        sink = MagicMock()
        sink.handle.side_effect = RuntimeError('ntfy unreachable')
        with patch.object(db_backup, 'NtfySink', return_value=sink), patch.object(db_backup, 'event_service') as events:
            db_backup.alert('title', 'message')
        events.emit.assert_called_once()

    def test_main_alerts_when_the_run_raises(self):
        with (
            patch.object(db_backup, 'run_backup', side_effect=db_backup.BackupError('disk gone')),
            patch.object(db_backup, 'alert') as alert,
        ):
            self.assertEqual(db_backup.main([]), 1)
        alert.assert_called_once()
        self.assertIn('disk gone', alert.call_args[0][1])

    def test_main_exits_3_on_a_stalled_dump_so_the_deploy_does_not_retry_it(self):
        with (
            patch.object(db_backup, 'run_backup', side_effect=db_backup.DumpStalled('no output for 300s')),
            patch.object(db_backup, 'alert') as alert,
        ):
            self.assertEqual(db_backup.main([]), db_backup.EXIT_STALLED)
        self.assertEqual(alert.call_args[0][0], 'Database backup stalled')

    def test_main_stays_quiet_on_success(self):
        with patch.object(db_backup, 'run_backup', return_value=0), patch.object(db_backup, 'alert') as alert:
            self.assertEqual(db_backup.main([]), 0)
        alert.assert_not_called()


class RunBackupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dest = Path(self.tmp.name)
        env = {
            'BACKUP_PATH': str(self.dest),
            'DB_DB': 'music-management',
            'DB_USER': 'u',
            'DB_PASS': 'p',
            'DB_HOST': 'db',
        }
        patcher = patch.dict(os.environ, env, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_failed_dump_leaves_no_file_behind(self):
        """A partial file is a trap for whoever restores under pressure."""

        def fake_dump(target, _creds):
            target.write_bytes(b'half a dump')
            raise db_backup.BackupError('connection lost')

        with patch.object(db_backup, 'dump', fake_dump):
            with self.assertRaises(db_backup.BackupError):
                db_backup.run_backup()
        self.assertEqual(list(self.dest.glob('*.sql.gz')), [])

    def test_a_disk_that_fills_mid_dump_leaves_no_file_behind(self):
        """ENOSPC is an OSError, not a BackupError, and used to leave the half-written dump in place.

        On a full disk that partial file is what keeps the disk full: every later run
        failed the same way, and nothing ever got the space back.
        """

        def disk_full(target, _creds):
            target.write_bytes(b'x' * 4096)
            raise OSError(28, 'No space left on device')

        with patch.object(db_backup, 'dump', disk_full):
            with self.assertRaises(OSError):
                db_backup.run_backup()
        self.assertEqual(sorted(p.name for p in self.dest.iterdir()), [])

    def test_old_backups_are_pruned_before_the_dump_so_a_full_disk_recovers(self):
        write_dump(self.dest / 'muma_db_20200101_030000.sql.gz')
        write_dump(self.dest / 'muma_db_20200102_030000.sql.gz')
        seen = {}

        def dump(target, _creds):
            seen['present'] = sorted(p.name for p in self.dest.iterdir())
            write_dump(target)

        with (
            patch.object(db_backup, 'dump', dump),
            patch.object(db_backup, 'row_counts', return_value={}),
        ):
            db_backup.run_backup()
        self.assertEqual(seen['present'], ['muma_db_20200102_030000.sql.gz'])

    def test_a_dump_is_written_under_a_temporary_name_until_it_verifies(self):
        seen = {}

        def dump(target, _creds):
            seen['name'] = target.name
            write_dump(target)

        with (
            patch.object(db_backup, 'dump', dump),
            patch.object(db_backup, 'row_counts', return_value={}),
        ):
            db_backup.run_backup()
        self.assertTrue(seen['name'].endswith(db_backup.SUFFIX + db_backup.PARTIAL_SUFFIX))
        names = sorted(p.name for p in self.dest.iterdir())
        self.assertEqual(names, [db_backup.LATEST_NAME, seen['name'][: -len(db_backup.PARTIAL_SUFFIX)]])

    def test_a_dump_that_cannot_fit_is_not_started(self):
        last = write_dump(self.dest / f'muma_db_{datetime.now(UTC) - timedelta(days=1):%Y%m%d_%H%M%S}.sql.gz')
        dump = MagicMock()
        full = MagicMock(free=last.stat().st_size // 2)
        with patch.object(db_backup, 'dump', dump), patch.object(db_backup.shutil, 'disk_usage', return_value=full):
            with self.assertRaises(db_backup.BackupError) as caught:
                db_backup.run_backup()
        dump.assert_not_called()
        self.assertIn('bytes free', str(caught.exception))
        self.assertEqual([p.name for p in self.dest.iterdir()], [last.name])

    def test_a_dump_that_fails_verification_is_removed(self):
        with patch.object(db_backup, 'dump', lambda target, _c: target.write_bytes(b'tiny')):
            with self.assertRaises(db_backup.BackupError):
                db_backup.run_backup()
        self.assertEqual(list(self.dest.glob('*.sql.gz')), [])

    def test_a_successful_run_records_what_it_can_be_checked_against(self):
        counts = {'library_tracks': 332856, 'events': 13290365}
        with (
            patch.object(db_backup, 'dump', lambda target, _c: write_dump(target)),
            patch.object(db_backup, 'row_counts', return_value=counts),
        ):
            self.assertEqual(db_backup.run_backup(), 0)
        latest = json.loads((self.dest / db_backup.LATEST_NAME).read_text())
        self.assertEqual(latest['row_counts'], counts)
        self.assertEqual(latest['tables'], 2)
        self.assertTrue(latest['file'].startswith(db_backup.DAILY_PREFIX))
        self.assertGreater(latest['bytes'], 0)

    def test_a_labelled_run_names_the_file_and_leaves_the_nightly_record_alone(self):
        """scripts/deploy.sh takes BACKUP_LABEL=pre-deploy dumps; they must not
        pose as the nightly backup that /health/backup and the restore check read."""
        with (
            patch.dict(os.environ, {'BACKUP_LABEL': 'pre-deploy'}),
            patch.object(db_backup, 'dump', lambda target, _c: write_dump(target)),
            patch.object(db_backup, 'row_counts') as counts,
        ):
            self.assertEqual(db_backup.run_backup(), 0)
        files = list(self.dest.glob('*.sql.gz'))
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].name.startswith('muma_db_pre-deploy_'))
        self.assertFalse((self.dest / db_backup.LATEST_NAME).exists())
        counts.assert_not_called()

    def test_a_labelled_dump_that_fails_verification_is_removed(self):
        with (
            patch.dict(os.environ, {'BACKUP_LABEL': 'pre-deploy'}),
            patch.object(db_backup, 'dump', lambda target, _c: target.write_bytes(b'tiny')),
        ):
            with self.assertRaises(db_backup.BackupError):
                db_backup.run_backup()
        self.assertEqual(list(self.dest.glob('*.sql.gz')), [])

    def test_labelled_dumps_keep_their_own_rotation(self):
        for stamp in ['20260901_010000', '20260902_010000', '20260903_010000', '20260904_010000']:
            (self.dest / f'muma_db_pre-deploy_{stamp}.sql.gz').write_bytes(b'x')
        nightly = self.dest / 'muma_db_20260801_031200.sql.gz'
        nightly.write_bytes(b'x')
        other_label = self.dest / 'muma_db_manual_20260801_031200.sql.gz'
        other_label.write_bytes(b'x')
        removed = db_backup.prune_labelled(self.dest, 'pre-deploy', keep=3)
        self.assertEqual([p.name for p in removed], ['muma_db_pre-deploy_20260901_010000.sql.gz'])
        self.assertTrue(nightly.exists())
        self.assertTrue(other_label.exists())

    def test_the_nightly_prune_never_touches_a_labelled_dump(self):
        labelled = self.dest / 'muma_db_pre-deploy_20200101_000000.sql.gz'
        labelled.write_bytes(b'x')
        db_backup.prune(self.dest, 14, datetime(2026, 9, 1, tzinfo=UTC))
        self.assertTrue(labelled.exists())

    def test_a_labelled_run_leaves_the_nightly_rotation_unpruned(self):
        """A deploy-time dump is not the nightly job: it must not delete nightlies."""
        old = write_dump(self.dest / 'muma_db_20200101_030000.sql.gz')
        newest = write_dump(self.dest / 'muma_db_20200102_030000.sql.gz')
        with (
            patch.dict(os.environ, {'BACKUP_LABEL': 'pre-deploy'}),
            patch.object(db_backup, 'dump', lambda target, _c: write_dump(target)),
        ):
            self.assertEqual(db_backup.run_backup(), 0)
        self.assertTrue(old.exists())
        self.assertTrue(newest.exists())

    def test_a_labelled_dump_that_cannot_fit_is_not_started(self):
        last = write_dump(self.dest / f'muma_db_{datetime.now(UTC) - timedelta(days=1):%Y%m%d_%H%M%S}.sql.gz')
        dump = MagicMock()
        full = MagicMock(free=last.stat().st_size // 2)
        with (
            patch.dict(os.environ, {'BACKUP_LABEL': 'pre-deploy'}),
            patch.object(db_backup, 'dump', dump),
            patch.object(db_backup.shutil, 'disk_usage', return_value=full),
        ):
            with self.assertRaises(db_backup.BackupError):
                db_backup.run_backup()
        dump.assert_not_called()

    def test_the_free_space_yardstick_is_the_newest_nightly_not_a_labelled_dump(self):
        """A labelled name sorts after every stamp, so picking by name alone would measure it."""
        nightly = write_dump(self.dest / 'muma_db_20260901_030000.sql.gz')
        (self.dest / 'muma_db_pre-deploy_20200101_000000.sql.gz').write_bytes(b'x')
        tight = MagicMock(free=nightly.stat().st_size)
        with patch.object(db_backup.shutil, 'disk_usage', return_value=tight):
            with self.assertRaises(db_backup.BackupError):
                db_backup.ensure_free_space(self.dest, datetime(2026, 9, 2, tzinfo=UTC))

    def test_an_unusable_label_is_refused(self):
        for label in ['monthly', '../etc', 'Pre Deploy', 'x' * 40]:
            with patch.dict(os.environ, {'BACKUP_LABEL': label}):
                with self.assertRaises(db_backup.BackupError):
                    db_backup.backup_label()


class WriteLatestTest(unittest.TestCase):
    """latest.json is read by /health/backup and --check-stale; it must never be half a file."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dest = Path(self.tmp.name)
        self.backup = write_dump(self.dest / 'muma_db_20260831_030000.sql.gz')
        self.now = datetime(2026, 8, 31, 3, 5, tzinfo=UTC)

    def test_it_is_replaced_in_one_step_and_leaves_no_temporary_file(self):
        with patch.object(db_backup.os, 'replace', wraps=os.replace) as replace:
            target = db_backup.write_latest(self.dest, self.backup, self.now, self.now, {'t': 1})
        replace.assert_called_once()
        self.assertEqual(replace.call_args.args[1], target)
        self.assertEqual(json.loads(target.read_text())['row_counts'], {'t': 1})
        self.assertEqual(sorted(p.name for p in self.dest.iterdir()), [db_backup.LATEST_NAME, self.backup.name])

    def test_a_failed_write_keeps_the_previous_file_intact(self):
        db_backup.write_latest(self.dest, self.backup, self.now, self.now, {'t': 1})
        with patch.object(Path, 'write_text', side_effect=OSError(28, 'No space left on device')):
            with self.assertRaises(OSError):
                db_backup.write_latest(self.dest, self.backup, self.now, self.now, {'t': 2})
        latest = json.loads((self.dest / db_backup.LATEST_NAME).read_text())
        self.assertEqual(latest['row_counts'], {'t': 1})
        self.assertEqual(sorted(p.name for p in self.dest.iterdir()), [db_backup.LATEST_NAME, self.backup.name])


if __name__ == '__main__':
    unittest.main()


class QuoteIdentifierTest(unittest.TestCase):
    """A table name cannot be bound, so its shape is checked before it is used."""

    def test_accepts_the_names_this_schema_actually_has(self):
        for name in ('library_tracks', 'events', 'downloads_soundcloud_archive'):
            self.assertEqual(db_backup.quote_identifier(name), f'`{name}`')

    def test_refuses_anything_that_is_not_just_a_name(self):
        for name in ('tracks`; DROP TABLE users; --', 'a b', 'tracks)', ''):
            with self.assertRaises(db_backup.BackupError):
                db_backup.quote_identifier(name)


class ReadOnlyDestinationTest(unittest.TestCase):
    """The restore check reads a directory it must not be able to write.

    Both requirements are real and they collide: the backup job must refuse a
    destination it cannot write, and the restore check mounts that same
    directory read-only so it cannot damage its own source. The flag is where
    they are reconciled -- this is the bug that made the first restore check
    fail with "backup destination /backups is not writable".
    """

    def _read_only_dir(self, tmp: str) -> Path:
        dest = Path(tmp) / 'ro'
        dest.mkdir(mode=0o500)
        # Restored inside the test, not via addCleanup: the TemporaryDirectory
        # is already gone by the time cleanups run.
        return dest

    def test_a_read_only_destination_is_rejected_for_the_backup_job(self):
        with TemporaryDirectory() as tmp:
            dest = self._read_only_dir(tmp)
            try:
                with self.assertRaises(db_backup.BackupError) as caught:
                    db_backup.resolve_destination(str(dest), None)
                self.assertIn('not writable', str(caught.exception))
            finally:
                dest.chmod(0o700)

    def test_a_read_only_destination_is_accepted_when_only_reading(self):
        with TemporaryDirectory() as tmp:
            dest = self._read_only_dir(tmp)
            try:
                self.assertEqual(db_backup.resolve_destination(str(dest), None, require_writable=False), dest.resolve())
            finally:
                dest.chmod(0o700)


class StallWatchdogTest(unittest.TestCase):
    """Bug report 068: a dump queued behind a metadata lock must fail, not hang the job."""

    def _spawn(self, script: str) -> subprocess.Popen:
        process = subprocess.Popen([sys.executable, '-c', script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(process.communicate)
        return process

    def test_a_silent_dump_is_stopped_and_named(self):
        process = self._spawn(
            'import sys, time\n'
            'sys.stdout.write("-- Dumping data for table `tagger_processed_files`\\n")\n'
            'sys.stdout.flush()\n'
            'time.sleep(60)\n'
        )
        started = time.monotonic()
        with self.assertRaises(db_backup.DumpStalled) as caught:
            db_backup._copy_with_watchdog(process, io.BytesIO(), stall_limit=1)
        self.assertLess(time.monotonic() - started, 30)
        self.assertIn('no output for 1s', str(caught.exception))
        self.assertIn('tagger_processed_files', str(caught.exception))
        self.assertIsNotNone(process.wait(timeout=10), 'the stalled dump must have been killed')

    def test_a_slow_but_moving_dump_is_left_alone(self):
        process = self._spawn(
            'import sys, time\nfor _ in range(6):\n    sys.stdout.write("x"); sys.stdout.flush(); time.sleep(0.4)\n'
        )
        out = io.BytesIO()
        db_backup._copy_with_watchdog(process, out, stall_limit=1)
        self.assertEqual(out.getvalue(), b'xxxxxx')

    def test_the_limit_comes_from_the_environment(self):
        with patch.dict(os.environ, {'BACKUP_STALL_SECONDS': '42'}):
            self.assertEqual(db_backup.stall_seconds(), 42)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('BACKUP_STALL_SECONDS', None)
            self.assertEqual(db_backup.stall_seconds(), db_backup.DEFAULT_STALL_SECONDS)
