"""Tests for tools/env_required.py and the tools and scripts that use it."""

import pathlib
import re

import pytest

from tools.env_required import MISSING_EXIT_CODE, require_env

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_returns_every_value_when_all_are_set():
    values = require_env('DB_HOST', 'DB_USER', environ={'DB_HOST': 'db.example.org', 'DB_USER': 'muma'})
    assert values == {'DB_HOST': 'db.example.org', 'DB_USER': 'muma'}


def test_exits_with_code_2_and_names_every_missing_variable(capsys):
    with pytest.raises(SystemExit) as caught:
        require_env('DB_HOST', 'DB_USER', 'DB_PASS', environ={'DB_USER': 'muma'})
    assert caught.value.code == MISSING_EXIT_CODE == 2
    error = capsys.readouterr().err
    assert 'DB_HOST' in error
    assert 'DB_PASS' in error
    assert 'DB_USER' not in error


def test_an_empty_value_counts_as_missing(capsys):
    with pytest.raises(SystemExit):
        require_env('REMOTE_HOST', environ={'REMOTE_HOST': ''})
    assert 'REMOTE_HOST' in capsys.readouterr().err


def test_reads_the_process_environment_by_default(monkeypatch):
    monkeypatch.setenv('REMOTE_HOST', 'ssh.example.org')
    assert require_env('REMOTE_HOST') == {'REMOTE_HOST': 'ssh.example.org'}


@pytest.mark.parametrize(
    'path',
    [
        'tools/check_db_structure.py',
        'tools/db_backup_json.py',
        'tools/inspect_table_content.py',
        'scripts/import_lms_users.py',
    ],
)
def test_host_comes_from_the_environment_through_the_helper(path):
    """These read text, not imports: they need pymysql or sqlalchemy, which the unit environment lacks."""
    source = (ROOT / path).read_text(encoding='utf-8')
    assert 'require_env(' in source
    assert not re.search(
        r'getenv\(\s*["\'](DB_HOST|REMOTE_HOST)["\']\s*,\s*["\'](?!localhost|db["\'])[^"\']', source
    ), f'{path} gives a host a default again'
