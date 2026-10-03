"""Tests for tools/pylint_plugins/muma_test_layout.py.

The plugin turns off three import-layout checks in test files and leaves them
on in production code. Pylint is a development tool (requirements-dev.txt), so
these tests skip where it is not installed.
"""

from pathlib import Path

import pytest

pytest.importorskip('pylint')

from pylint.lint import Run  # noqa: E402
from pylint.reporters import CollectingReporter  # noqa: E402

from tools.pylint_plugins.muma_test_layout import is_test_file  # noqa: E402

PLUGIN_DIR = Path(__file__).resolve().parent / 'pylint_plugins'

# A late import, an import inside a function and a fixture-style argument that
# shadows a module-level name: one finding per checked message.
SOURCE = '''"""Sample module."""
import os

os.environ.setdefault('X', '1')

import sys


def sample_fixture():
    """Return a value."""
    return 1


def test_sample(sample_fixture):
    """Use the fixture."""
    import json
    return json, sys, sample_fixture
'''

CHECKED = {'wrong-import-position', 'import-outside-toplevel', 'redefined-outer-name'}


@pytest.mark.parametrize(
    'path',
    [
        'services/importer/tests/test_mover.py',
        'tests/ci/helpers.py',
        'services/tagger/Song/LabelSongTest.py',
        'tools/test_db_backup.py',
        'services/conftest.py',
    ],
)
def test_is_test_file_accepts_test_modules(path):
    """Every file pytest collects, and every file under a tests/ directory, counts."""
    assert is_test_file(path)


@pytest.mark.parametrize(
    'path',
    [
        'services/importer/mover.py',
        'services/tagger/Song/TestSongBuilder.py',
        'tools/latest_report.py',
        'services/importer/tests/fixture.json',
        None,
        '',
    ],
)
def test_is_test_file_rejects_other_files(path):
    """Production modules, non-Python files and a missing path do not count."""
    assert not is_test_file(path)


def _symbols(path, monkeypatch):
    """Run pylint with the plugin on ``path`` and return the symbols it reports."""
    monkeypatch.syspath_prepend(str(PLUGIN_DIR))
    reporter = CollectingReporter()
    Run(
        [
            str(path),
            '--rcfile=/dev/null',
            '--load-plugins=muma_test_layout',
            '--disable=all',
            f'--enable={",".join(sorted(CHECKED))},muma-test-layout',
            '--score=n',
        ],
        reporter=reporter,
        exit=False,
    )
    return {message.symbol for message in reporter.messages}


def test_plugin_silences_layout_checks_in_a_test_file(tmp_path, monkeypatch):
    """A test file gets none of the three findings."""
    path = tmp_path / 'tests' / 'test_sample.py'
    path.parent.mkdir()
    path.write_text(SOURCE, encoding='utf-8')

    assert not _symbols(path, monkeypatch) & CHECKED


def test_plugin_keeps_layout_checks_in_production_code(tmp_path, monkeypatch):
    """The same source outside a test file still gets all three findings."""
    path = tmp_path / 'sample.py'
    path.write_text(SOURCE, encoding='utf-8')

    assert _symbols(path, monkeypatch) >= CHECKED
