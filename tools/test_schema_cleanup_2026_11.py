"""tools/schema_cleanup_2026_11.py: nothing changes without --apply, and --apply needs a backup.

tests/integration/test_schema_cleanup.py runs the statements against a real MariaDB.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools import schema_cleanup_2026_11 as cleanup

STATEMENTS = ['DROP TABLE `rules_genres_old`']


@pytest.fixture(name='env')
def env_fixture(monkeypatch):
    monkeypatch.setenv('DB_DB', 'music-management')
    monkeypatch.setenv('DB_USER', 'muma')
    monkeypatch.setenv('DB_PASS', 'app-secret')
    with (
        patch.object(cleanup, '_connect', return_value=MagicMock()),
        patch.object(cleanup, 'plan', return_value=STATEMENTS),
        patch.object(cleanup, 'apply') as apply,
        patch.object(cleanup, 'backup', return_value=Path('/backups/x.sql.gz')) as backup,
    ):
        yield apply, backup


def test_the_default_is_a_dry_run(env, capsys):
    apply, backup = env
    assert cleanup.main([]) == 0
    assert 'would run: DROP TABLE `rules_genres_old`' in capsys.readouterr().out
    apply.assert_not_called()
    backup.assert_not_called()


def test_apply_without_a_backup_dir_is_refused(env):
    apply, _ = env
    with pytest.raises(SystemExit):
        cleanup.main(['--apply'])
    apply.assert_not_called()


def test_apply_backs_up_first(env, tmp_path):
    apply, backup = env
    calls = []
    backup.side_effect = lambda *a: calls.append('backup') or tmp_path / 'x.sql.gz'
    apply.side_effect = lambda *a: calls.append('apply')
    assert cleanup.main(['--apply', '--backup-dir', str(tmp_path)]) == 0
    assert calls == ['backup', 'apply']


def test_a_failed_backup_changes_nothing(env, tmp_path):
    apply, backup = env
    backup.side_effect = cleanup.db_backup.BackupError('no trailer')
    with pytest.raises(cleanup.db_backup.BackupError):
        cleanup.main(['--apply', '--backup-dir', str(tmp_path)])
    apply.assert_not_called()


def test_the_cleanup_account_comes_first(monkeypatch):
    monkeypatch.setenv('DB_USER', 'muma')
    monkeypatch.setenv('DB_PASS', 'app-secret')
    monkeypatch.setenv('CLEANUP_DB_USER', 'root')
    monkeypatch.setenv('CLEANUP_DB_PASS', 'root-secret')
    creds = cleanup.credentials()
    assert (creds['user'], creds['password']) == ('root', 'root-secret')
