"""The mock_base stubs stay inside the test modules that ask for them (bug report 085).

services/tests/mock_base.py used to replace mutagen, pymysql, yt_dlp, config_store,
Cache and more in sys.modules for the whole session. Now a module opts in with
``pytestmark = pytest.mark.mock_base(...)`` and services/tests/mock_base_plugin.py
installs the stubs only while that module is imported and while its tests run. These
tests fail the moment a stub is visible to the rest of the session again.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from services.tests import mock_base, mock_base_plugin

ROOT = Path(__file__).resolve().parents[2]

# Two test modules that between them ask for mutagen, yt_dlp, pymysql, dbutils, markdown,
# config_store, DatabaseConnector and Cache. Collecting them is what used to leave those
# stubs behind for every later test.
STUBBED_MODULES = (
    'services/downloader/soundcloud/tests/test_basic_run.py',
    'services/music_manager/tests/test_curation_router.py',
)


def test_no_stub_in_sys_modules_after_collection(request):
    """After collection, and while an unmarked test runs, sys.modules holds no stub."""
    assert request.config.stash.get(mock_base_plugin.LEAKS_AFTER_COLLECTION, []) == []
    assert mock_base_plugin.leaked_stubs() == []
    for stub_names in mock_base.STUB_MODULE_NAMES.values():
        for name in stub_names:
            assert not mock_base.is_stub(sys.modules.get(name)), name


def test_collecting_a_stubbed_module_leaks_nothing():
    """Collect a stubbed module next to the check above, in a fresh interpreter.

    On its own the check proves nothing when no stubbed module was collected before it,
    so this runs it after collecting two that ask for eight of the stubs.
    """
    for module in STUBBED_MODULES:
        assert mock_base_plugin.declared_stubs(ROOT / module), f'{module} declares no stubs any more'
    result = subprocess.run(
        [
            sys.executable,
            '-m',
            'pytest',
            '-q',
            '-p',
            'no:cacheprovider',
            '--no-cov',
            '-k',
            'test_no_stub_in_sys_modules_after_collection',
            *STUBBED_MODULES,
            'tests/ci/test_mock_base_isolation.py',
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]
    assert '1 passed' in result.stdout


def test_a_world_is_restored_and_lifted_out_again():
    """Entering a world installs its stubs; leaving it puts the session's modules back."""
    manager = mock_base_plugin.WorldManager()
    before = sys.modules.get('pymysql')
    try:
        manager.switch({'pymysql', 'DatabaseConnector'})
        stub = sys.modules['pymysql']
        assert mock_base.is_stub(stub)
        # A project module imported under the stub binds to it ...
        from services.common.Helpers import DatabaseConnector  # pylint: disable=import-outside-toplevel

        assert DatabaseConnector.DatabaseConnector is mock_base.MockDatabaseConnector
        manager.switch(())
        # ... and neither it nor the stub is visible afterwards.
        assert sys.modules.get('pymysql') is before
        assert not mock_base.is_stub(sys.modules.get('services.common.Helpers.DatabaseConnector'))
        assert mock_base_plugin.leaked_stubs() == []
        # Coming back finds the same world, stub objects and all.
        manager.switch({'pymysql', 'DatabaseConnector'})
        assert sys.modules['pymysql'] is stub
    finally:
        manager.switch(())
    assert mock_base_plugin.leaked_stubs() == []


def test_marker_is_read_from_source(tmp_path):
    """Only a module-level pytestmark with literal names declares stubs."""
    declared = tmp_path / 'test_declared.py'
    declared.write_text(
        textwrap.dedent(
            """
            import pytest
            pytestmark = [pytest.mark.slow, pytest.mark.mock_base('mutagen', 'Cache')]
            """
        )
    )
    plain = tmp_path / 'test_plain.py'
    plain.write_text('import pytest\n\n@pytest.mark.mock_base("mutagen")\ndef test_x():\n    pass\n')
    unknown = tmp_path / 'test_unknown.py'
    unknown.write_text('import pytest\npytestmark = pytest.mark.mock_base("nope")\n')

    assert mock_base_plugin.declared_stubs(declared) == {'mutagen', 'Cache'}
    assert mock_base_plugin.declared_stubs(plain) == frozenset()
    with pytest.raises(pytest.UsageError):
        mock_base_plugin.declared_stubs(unknown)


def test_a_marker_on_a_test_function_is_rejected(tmp_path):
    """A function-level marker could not take effect (the module is already imported): fail loudly."""
    (tmp_path / 'test_misplaced.py').write_text(
        'import pytest\n\n\n@pytest.mark.mock_base("mutagen")\ndef test_x():\n    pass\n'
    )
    result = subprocess.run(
        [
            sys.executable,
            '-m',
            'pytest',
            '-q',
            '-p',
            'no:cacheprovider',
            '-p',
            'services.tests.mock_base_plugin',
            '--rootdir',
            str(tmp_path),
            '-c',
            '/dev/null',
            str(tmp_path / 'test_misplaced.py'),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode != 0
    assert 'module-level' in result.stdout + result.stderr
