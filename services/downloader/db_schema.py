"""Table definitions shared by the downloaders and the music-manager API.

The worker containers and the manager both touch these tables, and either one can
be the first to start, so both call ``ensure_downloader_tables`` before use.
"""
from __future__ import annotations

import logging
import threading

_CREATE_SETTINGS = """
    CREATE TABLE IF NOT EXISTS downloads_settings (
        source      VARCHAR(32)  NOT NULL,
        setting_key VARCHAR(64)  NOT NULL,
        value       VARCHAR(255) NOT NULL,
        updated_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (source, setting_key)
    )
"""

_CREATE_RATE_STATE = """
    CREATE TABLE IF NOT EXISTS downloads_rate_state (
        source          VARCHAR(32) NOT NULL PRIMARY KEY,
        multiplier      INT         NOT NULL DEFAULT 1,
        consecutive_403 INT         NOT NULL DEFAULT 0,
        consecutive_429 INT         NOT NULL DEFAULT 0,
        clean_runs      INT         NOT NULL DEFAULT 0,
        last_403_at     DATETIME    NULL,
        last_429_at     DATETIME    NULL,
        cooldown_until  DATETIME    NULL,
        updated_at      TIMESTAMP   DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    )
"""

_CREATE_ACCOUNT_CHECKS = """
    CREATE TABLE IF NOT EXISTS downloads_account_checks (
        source             VARCHAR(32)  NOT NULL,
        account            VARCHAR(255) NOT NULL,
        last_checked_at    DATETIME     NOT NULL,
        last_upload_at     DATETIME     NULL,
        last_seen_track_id VARCHAR(64)  NULL,
        PRIMARY KEY (source, account)
    )
"""

# Installs that predate the tier ladder already have the table without these two,
# and CREATE TABLE IF NOT EXISTS leaves such a table alone.
_ALTER_ACCOUNT_CHECKS = (
    'ALTER TABLE downloads_account_checks '
    'ADD COLUMN IF NOT EXISTS last_upload_at DATETIME NULL',
    'ALTER TABLE downloads_account_checks '
    'ADD COLUMN IF NOT EXISTS last_seen_track_id VARCHAR(64) NULL',
)

_CREATE_UNAVAILABLE = """
    CREATE TABLE IF NOT EXISTS downloads_soundcloud_unavailable (
        account    VARCHAR(255) NOT NULL,
        track_id   VARCHAR(255) NOT NULL,
        reason     VARCHAR(64)  NOT NULL,
        first_seen DATETIME     NOT NULL,
        last_seen  DATETIME     NOT NULL,
        PRIMARY KEY (account, track_id)
    )
"""

_STATEMENTS = (_CREATE_SETTINGS, _CREATE_RATE_STATE, _CREATE_ACCOUNT_CHECKS, _CREATE_UNAVAILABLE)

_lock = threading.Lock()
_created = False


def ensure_downloader_tables(cursor) -> None:
    """Create the downloader tables if they do not exist yet, and widen the old ones."""
    for statement in _STATEMENTS:
        cursor.execute(statement)
    for statement in _ALTER_ACCOUNT_CHECKS:
        cursor.execute(statement)


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
