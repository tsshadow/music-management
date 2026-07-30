"""Regression tests for tools/*.py import paths.

These scripts run as standalone containers in production (`genre-processor` and
`muma-soundcloud-fetcher`, see docker/docker-compose.yml). They are not covered by the
regular services/ test suite, so a refactor of services/common (e.g. moving/removing
modules) can silently break them with a ModuleNotFoundError that only surfaces at
container runtime. This test just imports/exercises them to catch that early.
"""
import importlib


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
