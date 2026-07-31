"""Storage for the downloader timing settings.

The settings live in the database rather than in ``ConfigStore``, because the
manager and the workers mount different host directories for ``/app/data`` and so
do not share ``config.json``. The database is the one thing they do share.

Only the knobs that differ from their default are stored.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

from services.downloader.timing import (
    DownloaderTiming,
    load_timing,
    sanitize_settings,
    validate_settings,
)


def rows_to_settings(rows: Iterable[Tuple[str, Any]]) -> Dict[str, Any]:
    """Turn ``(setting_key, value)`` rows into a mapping."""
    return dict(rows)


class InMemorySettingsStore:
    """Keeps the settings in a dict. Used by tests."""

    def __init__(self) -> None:
        self._rows: Dict[str, Dict[str, Any]] = {}

    def load(self, source: str) -> Dict[str, Any]:
        return dict(self._rows.get(source, {}))

    def save(self, source: str, values: Mapping[str, Any]) -> None:
        self._rows.setdefault(source, {}).update(values)


class DatabaseSettingsStore:
    """Persists the settings in ``downloads_settings``."""

    def _connect(self):
        from services.common.Helpers.DatabaseConnector import DatabaseConnector
        from services.downloader.db_schema import ensure_once
        connection = DatabaseConnector().connect()
        ensure_once(connection)
        return connection

    def load(self, source: str) -> Dict[str, Any]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    'SELECT setting_key, value FROM downloads_settings WHERE source = %s',
                    (source,))
                return rows_to_settings(cursor.fetchall())
        finally:
            connection.close()

    def save(self, source: str, values: Mapping[str, Any]) -> None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                for key, value in values.items():
                    cursor.execute(
                        'INSERT INTO downloads_settings (source, setting_key, value) '
                        'VALUES (%s, %s, %s) '
                        'ON DUPLICATE KEY UPDATE value = %s',
                        (source, key, str(value), str(value)))
            connection.commit()
        finally:
            connection.close()


_default_store: Optional[DatabaseSettingsStore] = None


def _store_or_default(store):
    global _default_store
    if store is not None:
        return store
    if _default_store is None:
        _default_store = DatabaseSettingsStore()
    return _default_store


def load_settings(source: str, store=None) -> Dict[str, int]:
    """Return the stored overrides for ``source``, or nothing if they cannot be read."""
    try:
        raw = _store_or_default(store).load(source)
    except Exception as exc:
        logging.warning('Could not read timing settings for %s; using defaults: %s', source, exc)
        return {}
    return sanitize_settings(source, raw)


def load_timing_for(source: str, multiplier: int=1, store=None) -> DownloaderTiming:
    """The effective timing of ``source``, with the stored overrides applied."""
    return load_timing(source, overrides=load_settings(source, store=store), multiplier=multiplier)


def save_settings(source: str, updates: Mapping[str, Any], store=None) -> Dict[str, int]:
    """Validate and store ``updates``. Raises ``ValueError`` on an invalid value."""
    validated = validate_settings(source, updates)
    if validated:
        _store_or_default(store).save(source, validated)
    return validated
