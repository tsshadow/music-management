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
        last_deep_sweep_at DATETIME     NULL,
        PRIMARY KEY (source, account)
    )
"""

# Installs that predate the tier ladder and the deep sweep already have the table
# without these three, and CREATE TABLE IF NOT EXISTS leaves such a table alone.
_ALTER_ACCOUNT_CHECKS = (
    'ALTER TABLE downloads_account_checks ADD COLUMN IF NOT EXISTS last_upload_at DATETIME NULL',
    'ALTER TABLE downloads_account_checks ADD COLUMN IF NOT EXISTS last_seen_track_id VARCHAR(64) NULL',
    'ALTER TABLE downloads_account_checks ADD COLUMN IF NOT EXISTS last_deep_sweep_at DATETIME NULL',
)

_CREATE_UNAVAILABLE = """
    CREATE TABLE IF NOT EXISTS downloads_soundcloud_unavailable (
        source           VARCHAR(32)  NOT NULL DEFAULT 'soundcloud',
        account          VARCHAR(255) NOT NULL,
        track_id         VARCHAR(255) NOT NULL,
        reason           VARCHAR(64)  NOT NULL,
        first_seen       DATETIME     NOT NULL,
        last_seen        DATETIME     NOT NULL,
        duration_seconds INT          NULL,
        attempts         INT          NOT NULL DEFAULT 0,
        PRIMARY KEY (account, track_id)
    )
"""

# The table now serves both downloaders and records duration verdicts as well as
# 403s, so installs that predate that are missing three columns. The primary key
# deliberately stays (account, track_id): dropping and recreating a key is not an
# idempotent statement, and ensure_downloader_tables runs on every start. Two
# sources sharing a row would need the same account name and the same track id
# across platforms whose ids do not share a format, and every query filters on
# source regardless.
_ALTER_UNAVAILABLE = (
    "ALTER TABLE downloads_soundcloud_unavailable "
    "ADD COLUMN IF NOT EXISTS source VARCHAR(32) NOT NULL DEFAULT 'soundcloud'",
    'ALTER TABLE downloads_soundcloud_unavailable ADD COLUMN IF NOT EXISTS duration_seconds INT NULL',
    'ALTER TABLE downloads_soundcloud_unavailable ADD COLUMN IF NOT EXISTS attempts INT NOT NULL DEFAULT 0',
)

_STATEMENTS = (_CREATE_SETTINGS, _CREATE_RATE_STATE, _CREATE_ACCOUNT_CHECKS, _CREATE_UNAVAILABLE)

_lock = threading.Lock()
_created = False


def ensure_downloader_tables(cursor) -> None:
    """Create the downloader tables if they do not exist yet, and widen the old ones."""
    for statement in _STATEMENTS:
        cursor.execute(statement)
    for statement in _ALTER_ACCOUNT_CHECKS + _ALTER_UNAVAILABLE:
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
