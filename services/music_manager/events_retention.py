"""Dagelijks opruimen van de events-tabel, met een eigen venster per level.

Fouten blijven lang genoeg staan om een patroon te herkennen; INFO verdwijnt
snel, want dat is het volume.
"""

from __future__ import annotations

from services.music_manager.database import get_db_connection
from services.music_manager.rbac import purge_refresh_tokens
from services.music_manager.thread_registry import run_forever

RETENTION_DAYS = {'INFO': 14, 'WARNING': 60, 'ERROR': 365, 'CRITICAL': 365}
BATCH_SIZE = 10000
INTERVAL_SECONDS = 86400

_DELETE = 'DELETE FROM events WHERE level = %s AND created_at < DATE_SUB(NOW(), INTERVAL %s DAY) LIMIT %s'


def purge_once(conn) -> dict[str, int]:
    """Verwijder in batches, zodat een grote opruiming de tabel niet lang op slot zet."""
    removed = {}
    for level, days in RETENTION_DAYS.items():
        total = 0
        while True:
            with conn.cursor() as cursor:
                cursor.execute(_DELETE, (level, days, BATCH_SIZE))
                deleted = cursor.rowcount
            conn.commit()
            total += deleted
            if deleted < BATCH_SIZE:
                break
        removed[level] = total
    return removed


def retention_tick() -> None:
    """One purge of events and stale refresh tokens; raises on a database failure so run_forever can log it and back off."""
    conn = get_db_connection()
    if not conn:
        return
    try:
        purge_once(conn)
        # The same daily housekeeping pass caps user_refresh_tokens, which every login grows.
        purge_refresh_tokens(conn)
    finally:
        conn.close()


def run_events_retention() -> None:
    """The `events-retention` thread: purge on start, then once a day, for good."""
    run_forever('events-retention', retention_tick, INTERVAL_SECONDS)
