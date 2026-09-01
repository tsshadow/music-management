"""Regression tests for tools/*.py import paths.

These scripts run as standalone containers in production (`genre-processor` and
`muma-soundcloud-fetcher`, see docker/docker-compose.yml). They are not covered by the
regular services/ test suite, so a refactor of services/common (e.g. moving/removing
modules) can silently break them with a ModuleNotFoundError that only surfaces at
container runtime. This test just imports/exercises them to catch that early.
"""

import importlib
import pathlib


def test_soundcloud_fetcher_imports():
    """tools/soundcloud_fetcher.py must import without raising ModuleNotFoundError."""
    module = importlib.import_module('tools.soundcloud_fetcher')
    assert hasattr(module, 'get_tracks_to_process')


def test_process_genres_imports():
    """tools/process_genres.py must import without raising ModuleNotFoundError."""
    module = importlib.import_module('tools.process_genres')
    assert hasattr(module, 'process_genres')


def test_process_genres_non_dry_run_import_path_is_valid():
    """process_genres(dry_run=False) resolves `ensure_tables_exist` from its current
    location (services.common.db_init), not the old, removed services.common.api.db_init
    path. ensure_tables_exist() itself degrades gracefully without a live DB connection.
    """
    from tools.process_genres import process_genres

    result = process_genres(json_file=None, dry_run=False, interactive=False)

    assert isinstance(result, dict)


def test_db_backup_imports():
    """tools/db_backup.py runs as the db-backup container, on a timer, unattended.

    An import error there surfaces as a backup that silently never happened --
    the exact failure this job exists to make impossible.
    """
    module = importlib.import_module('tools.db_backup')
    assert hasattr(module, 'run_backup')
    assert hasattr(module, 'check_stale')


def test_db_restore_check_imports():
    """tools/db_restore_check.py runs as the db-restore-check container."""
    module = importlib.import_module('tools.db_restore_check')
    assert hasattr(module, 'compare')


def test_ad_hoc_db_tools_have_no_credentials_of_their_own():
    """Seven of these carried the production root password as a string literal.

    They also defaulted DB_HOST to the production address, so running one from a
    checkout aimed itself at production as root without being asked to. The URL
    now comes from tools/db_url.py, which reads the environment and defaults
    nothing.

    Read as text rather than imported: these scripts need sqlalchemy, which is
    not in the test environment, and the property under test is a property of
    the source.
    """
    tools_dir = pathlib.Path(__file__).parent
    for name in (
        'check_backlog',
        'check_media',
        'cleanup_db',
        'describe_tables',
        'finalize_genres',
        'integrity_check',
        'migrate_db_renames',
    ):
        source = (tools_dir / f'{name}.py').read_text(encoding='utf-8')
        assert 'mysql+mysqlconnector://' not in source, f'tools/{name}.py builds its own database URL again'
        assert '192.0.2.27' not in source, f'tools/{name}.py defaults to the production host again'
        assert 'from tools.db_url import database_url' in source, (
            f'tools/{name}.py no longer takes its URL from the shared helper'
        )


def test_database_url_refuses_to_guess():
    """A missing variable must raise, not silently pick a database."""
    import os

    from tools.db_url import database_url

    saved = {name: os.environ.pop(name, None) for name in ('DB_HOST', 'DB_USER', 'DB_PASS', 'DB_DB')}
    try:
        raised = False
        try:
            database_url()
        except SystemExit as exc:
            raised = True
            assert 'DB_HOST' in str(exc)
        assert raised, 'database_url() returned a URL with nothing configured'
    finally:
        for name, value in saved.items():
            if value is not None:
                os.environ[name] = value


def test_database_url_builds_from_the_environment():
    import os

    from tools.db_url import database_url

    env = {'DB_HOST': 'db', 'DB_USER': 'u', 'DB_PASS': 'p', 'DB_DB': 'muma', 'DB_PORT': '3307'}
    saved = {name: os.environ.get(name) for name in env}
    os.environ.update(env)
    try:
        assert database_url() == 'mysql+mysqlconnector://u:p@db:3307/muma'
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
