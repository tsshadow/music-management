"""Tests for the nightly music mirror job that runs on the mirror NAS.

Nothing here runs rsync or zfs: a fake shell answers every command, keyed on what it is.
"""

import json
import random
import subprocess
import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools import music_mirror as mm

NOW = datetime(2026, 11, 13, 1, 30, tzinfo=UTC)


def item(flags, name, size=1000):
    """One ``%i|%l|%n`` line."""
    return f'{flags}|{size}|{name}'


def done(stdout='', code=0, stderr=''):
    return subprocess.CompletedProcess([], code, stdout, stderr)


class FakeShell(mm.Shell):
    """Answers rsync and zfs calls from canned outputs and records every argument list."""

    def __init__(self, library, changed=(), copy_code=0, sample_differs=(), snapshots=(), monthly=()):  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self.library = list(library)
        self.changed = set(changed)
        self.copy_code = copy_code
        self.sample_differs = set(sample_differs)
        self.snapshots = list(snapshots)
        self.monthly = list(monthly)
        self.calls = []

    def run(self, argv, timeout=None):  # pylint: disable=too-many-return-statements
        argv = list(argv)
        self.calls.append(argv)
        if argv[0].endswith('zfs'):
            return self._zfs(argv)
        if '--list-only' in argv:
            return done('drwxr-xr-x 4,096 2026/11/12 10:00:00 Labels\ndrwxr-xr-x 4,096 2026/11/12 10:00:00 Sets\n')
        if '--files-from' in ' '.join(argv):
            listed = (
                Path(next(a for a in argv if a.startswith('--files-from=')).split('=', 1)[1])
                .read_text(encoding="utf-8")
                .split()
            )
            return done('\n'.join(item('>f..c......', n) for n in listed if n in self.sample_differs))
        if argv[-1].endswith(mm.STATUS_NAME):
            return done()
        if '--delete' in argv and '--dry-run' in argv:
            return done('\n'.join(self.monthly))
        if '--delete' in argv:
            return done('\n'.join(item('*deleting  ', n, 0) for n in self.monthly))
        if '--dry-run' in argv:
            lines = [item('>f+++++++++' if n in self.changed else '.f         ', n) for n in self.library]
            return done('\n'.join([item('cd+++++++++', 'Labels/', 0), *lines]))
        return done('\n'.join(item('>f+++++++++', n) for n in self.library if n in self.changed), self.copy_code)

    def _zfs(self, argv):
        if argv[1] == 'list' and '-t' in argv:
            return done(''.join(f'tank/mirror@{s}\n' for s in self.snapshots))
        if argv[1] == 'list':
            return done('600\t400\n')
        if argv[1] == 'snapshot':
            self.snapshots.append(argv[2].split('@', 1)[1])
            return done()
        if argv[1] == 'destroy':
            self.snapshots.remove(argv[2].split('@', 1)[1])
            return done()
        return done(code=1)


class JobTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        (root / 'mirror').mkdir()
        self.cfg = mm.Config(
            source='muma-mirror@library.example.com',
            read_key='/opt/muma-mirror/keys/read',
            status_key='/opt/muma-mirror/keys/status',
            dest=root / 'mirror',
            dataset='tank/mirror',
            state_dir=root / 'state',
            expected_dirs=('Labels', 'Sets'),
            sample_size=10,
        )
        mount = patch.object(mm.os.path, 'ismount', return_value=True)
        mount.start()
        self.addCleanup(mount.stop)
        self.notify = patch.object(mm, 'notify').start()
        self.addCleanup(patch.stopall)

    def status(self):
        return json.loads((self.cfg.state_dir / mm.STATUS_NAME).read_text(encoding="utf-8"))

    def library(self, count=100):
        return [f'Labels/L/{i:03}.flac' for i in range(count)]


class ArgvTest(JobTestCase):
    def test_the_nightly_copy_never_deletes(self):
        for dry in (True, False):
            argv = mm.copy_argv(self.cfg, dry_run=dry)
            self.assertFalse(any(a.startswith('--del') for a in argv), argv)
            self.assertIn('--inplace', argv)
        self.assertFalse(any(a.startswith('--del') for a in mm.sample_argv(self.cfg, Path('/x'))))

    def test_the_monthly_delete_is_always_a_dry_run(self):
        for checksum in (True, False):
            argv = mm.monthly_argv(self.cfg, checksum=checksum)
            self.assertIn('--delete', argv)
            self.assertIn('--dry-run', argv)

    def test_only_prune_deletes(self):
        self.assertIn('--delete', mm.prune_argv(self.cfg))
        self.assertNotIn('--dry-run', mm.prune_argv(self.cfg))

    def test_no_owner_or_mode_is_copied(self):
        argv = mm.copy_argv(self.cfg, dry_run=False)
        self.assertNotIn('-a', argv)
        self.assertFalse(any(a in ('-p', '-o', '-g', '-A', '--perms') for a in argv))

    def test_each_key_goes_to_its_own_command(self):
        self.assertIn('/opt/muma-mirror/keys/read', ' '.join(mm.copy_argv(self.cfg, dry_run=False)))
        status = ' '.join(mm.status_push_argv(self.cfg, Path('/s/latest.json')))
        self.assertIn('/opt/muma-mirror/keys/status', status)
        self.assertNotIn('keys/read', status)


class RunTest(JobTestCase):
    def test_a_good_run_snapshots_and_writes_the_status(self):
        files = self.library()
        shell = FakeShell(files, changed=files[:3])
        self.assertEqual(mm.run(self.cfg, shell, now=NOW), mm.EXIT_OK)
        status = self.status()
        self.assertEqual(status['result'], 'ok')
        self.assertEqual((status['files_total'], status['files_transferred']), (100, 3))
        self.assertEqual(status['bytes_transferred'], 3000)
        self.assertTrue(status['snapshot'].startswith('mirror-'))
        self.assertEqual(status['sample'], {'checked': 10, 'differing': []})
        self.assertEqual(status['last_ok_files_total'], 100)
        self.assertEqual(shell.snapshots, [status['snapshot']])
        self.assertTrue(any(c[-1].endswith(mm.STATUS_NAME) for c in shell.calls), 'status not pushed')
        self.assertEqual(len(list((self.cfg.state_dir / 'manifests').glob('*.txt.gz'))), 1)
        self.notify.assert_not_called()

    def test_the_status_is_written_through_a_partial_file(self):
        mm.run(self.cfg, FakeShell(self.library()), now=NOW)
        self.assertFalse((self.cfg.state_dir / 'latest.json.partial').exists())

    def test_vanished_files_count_as_ok(self):
        shell = FakeShell(self.library(), copy_code=24)
        with patch.object(shell, 'run', wraps=shell.run):
            self.assertEqual(mm.run(self.cfg, shell, now=NOW), mm.EXIT_OK)
        self.assertEqual(self.status()['rsync_exit'], 24)

    def test_an_rsync_error_fails_without_a_snapshot_and_pushes(self):
        shell = FakeShell(self.library(), copy_code=12)
        self.assertEqual(mm.run(self.cfg, shell, now=NOW), mm.EXIT_FAILED)
        self.assertEqual(self.status()['result'], 'failed')
        self.assertIn('rsync exit 12', self.status()['reason'])
        self.assertEqual(shell.snapshots, [])
        self.notify.assert_called_once()

    def test_an_unmounted_mirror_fails_before_rsync(self):
        shell = FakeShell(self.library())
        with patch.object(mm.os.path, 'ismount', return_value=False):
            self.assertEqual(mm.run(self.cfg, shell, now=NOW), mm.EXIT_FAILED)
        self.assertFalse(any('rsync' in c[0] and '--dry-run' in c for c in shell.calls))

    def test_a_missing_top_folder_is_refused(self):
        shell = FakeShell(self.library())
        cfg = mm.Config(**{**self.cfg.__dict__, 'expected_dirs': ('Labels', 'Youtube')})
        self.assertEqual(mm.run(cfg, shell, now=NOW), mm.EXIT_REFUSED)
        self.assertIn('Youtube', self.status()['reason'])

    def test_a_shrunk_library_is_refused(self):
        mm.run(self.cfg, FakeShell(self.library(100)), now=NOW)
        shell = FakeShell(self.library(80))
        self.assertEqual(mm.run(self.cfg, shell, now=NOW), mm.EXIT_REFUSED)
        self.assertEqual(self.status()['result'], 'refused')
        self.assertEqual(self.status()['last_ok_files_total'], 100)
        self.assertFalse(
            any(
                '--dry-run' not in c
                and 'rsync' in c[0]
                and '--list-only' not in c
                and not c[-1].endswith(mm.STATUS_NAME)
                for c in shell.calls
            )
        )

    def test_too_many_changes_are_refused_unless_allowed(self):
        files = self.library()
        self.assertEqual(mm.run(self.cfg, FakeShell(files, changed=files[:6]), now=NOW), mm.EXIT_REFUSED)
        self.assertIn('--allow-large-change', self.status()['reason'])
        self.assertEqual(
            mm.run(self.cfg, FakeShell(files, changed=files[:6]), allow_large_change=True, now=NOW), mm.EXIT_OK
        )

    def test_initial_skips_every_limit_and_the_monthly_pass(self):
        files = self.library()
        shell = FakeShell(files, changed=files)
        self.assertEqual(mm.run(self.cfg, shell, initial=True, now=NOW), mm.EXIT_OK)
        self.assertFalse(any('--delete' in c for c in shell.calls))

    def test_a_differing_sample_is_reported(self):
        files = self.library(10)
        mm.run(self.cfg, FakeShell(files, sample_differs=files[:1]), now=NOW)
        self.assertEqual(self.status()['sample']['differing'], [files[0]])

    def test_the_first_run_of_a_month_counts_orphans(self):
        orphan = self.cfg.dest / 'Labels/Gone/x.flac'
        orphan.parent.mkdir(parents=True)
        orphan.write_bytes(b'12345')
        shell = FakeShell(self.library(), monthly=[item('*deleting  ', 'Labels/Gone/x.flac', 0)])
        mm.run(self.cfg, shell, now=NOW)
        self.assertEqual(self.status()['orphans']['files'], 1)
        self.assertEqual(self.status()['orphans']['bytes'], 5)
        self.assertEqual(self.status()['full_checksum']['differing_count'], 0)
        calls = len(shell.calls)
        mm.run(self.cfg, shell, now=NOW)
        self.assertFalse(any('--delete' in c for c in shell.calls[calls:]), 'monthly pass ran twice in a month')
        self.assertEqual(self.status()['orphans']['files'], 1)


class PruneTest(JobTestCase):
    def test_prune_takes_a_snapshot_before_it_deletes(self):
        shell = FakeShell(self.library(), monthly=['Labels/Gone/x.flac'])
        self.assertEqual(mm.prune(self.cfg, shell), mm.EXIT_OK)
        snapshot = next(i for i, c in enumerate(shell.calls) if c[:2] == ['/usr/sbin/zfs', 'snapshot'])
        delete = next(i for i, c in enumerate(shell.calls) if '--delete' in c)
        self.assertLess(snapshot, delete)

    def test_prune_without_a_snapshot_deletes_nothing(self):
        shell = FakeShell(self.library())
        with patch.object(mm, 'take_snapshot', side_effect=mm.RunFailed('pool full')):
            self.assertEqual(mm.prune(self.cfg, shell), mm.EXIT_REFUSED)
        self.assertFalse(any('--delete' in c for c in shell.calls))


class RetentionTest(unittest.TestCase):
    def names(self, start, days):
        base = datetime(2026, 1, 1, 1, 30, tzinfo=UTC).timestamp() + start * 86400
        return [mm.snapshot_name(datetime.fromtimestamp(base + d * 86400, UTC)) for d in range(days)]

    def test_a_year_and_a_half_of_nights_keeps_14_daily_8_weekly_12_monthly_at_most(self):
        names = self.names(0, 540)
        removed = set(mm.snapshots_to_remove(names))
        kept = [n for n in names if n not in removed]
        self.assertLessEqual(len(kept), 14 + 8 + 12)
        self.assertIn(names[-1], kept)
        self.assertEqual(kept[-14:], names[-14:])

    def test_other_snapshots_are_never_removed(self):
        names = [*self.names(0, 60), 'manual-before-upgrade', 'mirror-garbage', 'auto-2026-01-01']
        removed = mm.snapshots_to_remove(names)
        for name in ('manual-before-upgrade', 'mirror-garbage', 'auto-2026-01-01'):
            self.assertNotIn(name, removed)

    def test_the_newest_is_kept_even_alone(self):
        self.assertEqual(mm.snapshots_to_remove(self.names(0, 1)), [])
        self.assertEqual(mm.snapshots_to_remove([]), [])

    def test_retention_destroys_only_what_it_picked(self):
        shell = FakeShell([], snapshots=self.names(0, 30))
        cfg = mm.Config('s', 'r', 'w', Path('/m'), 'tank/mirror', Path('/st'))
        removed = mm.apply_retention(cfg, shell)
        self.assertEqual(len(shell.snapshots), 30 - len(removed))
        self.assertTrue(all(c[1] == 'destroy' for c in shell.calls if c[1] not in ('list',)))


class ParseTest(unittest.TestCase):
    def test_parse_items_reads_files_changes_and_deletions(self):
        listing = mm.parse_items(
            [
                item('>f+++++++++', 'a.flac', 1_000),
                item('.f         ', 'b.flac'),
                item('cd+++++++++', 'dir/', 0),
                item('cL+++++++++', 'link', 0),
                item('*deleting  ', 'old/', 0),
                'noise without separators',
                item('>f.st......', 'c.flac', 'n/a'),
            ]
        )
        self.assertEqual(listing.files, ['a.flac', 'b.flac', 'c.flac'])
        self.assertEqual(listing.changed, [('a.flac', 1000), ('c.flac', 0)])
        self.assertEqual(listing.deleting, ['old'])

    def test_count_vanished(self):
        stderr = 'file has vanished: "/x/a.flac"\nrsync warning: some files vanished\nfile has vanished: "/x/b"\n'
        self.assertEqual(mm.count_vanished(stderr), 2)

    def test_pick_sample_takes_half_from_the_transfers(self):
        files = [f'f{i}' for i in range(100)]
        sample = mm.pick_sample(files, files[:30], 20, random.Random(1))
        self.assertEqual(len(sample), 20)
        self.assertEqual(len(set(sample)), 20)
        self.assertGreaterEqual(sum(1 for f in sample if f in files[:30]), 10)


class ConfigTest(unittest.TestCase):
    def test_env_file_is_read_without_a_shell(self):
        values = mm.parse_env_file('# c\nMIRROR_SOURCE="a@b"\nMIRROR_DEST=$(rm -rf /)\n\nBROKEN\n')
        self.assertEqual(values, {'MIRROR_SOURCE': 'a@b', 'MIRROR_DEST': '$(rm -rf /)'})

    def test_every_missing_key_is_named(self):
        with self.assertRaises(mm.ConfigError) as caught:
            mm.load_config({'MIRROR_SOURCE': 'a@b'})
        self.assertIn('MIRROR_READ_KEY', str(caught.exception))
        self.assertIn('MIRROR_STATE_DIR', str(caught.exception))

    def test_a_bad_number_is_a_config_error(self):
        values = dict.fromkeys(
            (
                'MIRROR_SOURCE',
                'MIRROR_READ_KEY',
                'MIRROR_STATUS_KEY',
                'MIRROR_DEST',
                'MIRROR_DATASET',
                'MIRROR_STATE_DIR',
            ),
            'x',
        )
        values['MIRROR_MAX_CHANGED_GB'] = 'lots'
        with self.assertRaises(mm.ConfigError):
            mm.load_config(values)

    def test_the_ntfy_url_must_be_http(self):
        keys = ('MIRROR_SOURCE', 'MIRROR_READ_KEY', 'MIRROR_STATUS_KEY', 'MIRROR_DEST', 'MIRROR_DATASET')
        values = {**dict.fromkeys(keys, 'x'), 'MIRROR_STATE_DIR': 'x', 'MIRROR_NTFY_URL': 'file:///etc/shadow'}
        with self.assertRaises(mm.ConfigError):
            mm.load_config(values)
        values['MIRROR_NTFY_URL'] = 'https://ntfy.example.com/'
        self.assertEqual(mm.load_config(values).ntfy_url, 'https://ntfy.example.com')

    def test_main_exits_4_on_a_missing_env_file(self):
        self.assertEqual(mm.main(['--env', '/nonexistent/env']), mm.EXIT_CONFIG)

    def test_main_exits_3_when_locked(self):
        with TemporaryDirectory() as tmp:
            env = Path(tmp, 'env')
            env.write_text(
                f'MIRROR_SOURCE=a@b\nMIRROR_READ_KEY=r\nMIRROR_STATUS_KEY=s\nMIRROR_DEST={tmp}\n'
                f'MIRROR_DATASET=tank/m\nMIRROR_STATE_DIR={tmp}/state\n',
                encoding='utf-8',
            )
            with mm.run_lock(Path(tmp, 'state')) as locked:
                self.assertTrue(locked)
                self.assertEqual(mm.main(['--env', str(env)]), mm.EXIT_LOCKED)


if __name__ == '__main__':
    unittest.main()
