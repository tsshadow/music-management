"""Dagelijks opruimen van de events-tabel, met een eigen venster per level.

Fouten blijven lang genoeg staan om een patroon te herkennen; INFO verdwijnt
snel, want dat is het volume.
"""
from __future__ import annotations

import sys
import time

from services.music_manager.database import get_db_connection

RETENTION_DAYS = {'INFO': 14, 'WARNING': 60, 'ERROR': 365, 'CRITICAL': 365}
BATCH_SIZE = 10000
INTERVAL_SECONDS = 86400

_DELETE = (
    'DELETE FROM events WHERE level = %s '
    'AND created_at < DATE_SUB(NOW(), INTERVAL %s DAY) LIMIT %s'
)


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


def run_events_retention() -> None:
    while True:
        try:
            conn = get_db_connection()
            if conn:
                try:
                    purge_once(conn)
                finally:
                    conn.close()
        except Exception as exc:
            print(f'events-retention: opruimen mislukt: {exc}', file=sys.stderr)
        time.sleep(INTERVAL_SECONDS)
