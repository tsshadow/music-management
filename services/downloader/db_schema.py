"""Table definitions shared by the downloaders and the music-manager API.

The worker containers and the manager both touch these tables, and either one can
be the first to start, so both call ``ensure_downloader_tables`` before use.
"""

from __future__ import annotations

import logging
import threading

from services.common import schema_tables

# Declared with every other table in services/common/schema_tables.py.
DOWNLOADER_TABLES = (
    'downloads_settings',
    'downloads_rate_state',
    'downloads_account_checks',
    'downloads_soundcloud_unavailable',
)

_lock = threading.Lock()
_created = False


def ensure_downloader_tables(cursor) -> None:
    """Create the downloader tables if they do not exist yet."""
    statements = dict(schema_tables.TABLES)
    for name in DOWNLOADER_TABLES:
        cursor.execute(statements[name])


def ensure_once(connection) -> None:
    """Create the tables the first time this process needs them."""
    global _created
    with _lock:
        if _created:
            return
        try:
            with connection.cursor() as cursor:
                ensure_downloader_tables(cursor)
            connection.commit()
            _created = True
        except Exception as exc:  # pragma: no cover - depends on a live database
            logging.warning('Could not ensure downloader tables exist: %s', exc)


def reset_for_tests() -> None:
    """Forget that the tables were created; used by tests only."""
    global _created
    with _lock:
        _created = False
