"""Leeskant van de events-stroom: het logboek in de web-UI en de REST-sensor in
Home Assistant komen hier binnen."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from services.music_manager.database import get_db_connection
from services.music_manager.rbac import require_admin
from services.music_manager.routers.users import verify_api_key

router = APIRouter(tags=['events'])

LEVELS = ('INFO', 'WARNING', 'ERROR', 'CRITICAL')
# Four processes call setup_logging, so there are four sources. The tagger and scanner
# loops run inside music-manager; their events carry source='music-manager', so a chip for
# 'tagger' would always stay empty. 'bpm-analyzer' is its own container
# (services/music_manager/bpm/worker.py).
SOURCES = ('music-manager', 'downloader', 'importer', 'bpm-analyzer')
DEFAULT_LIMIT = 100
MAX_LIMIT = 1000

_RELATIVE = re.compile(r'^-(\d+)([mhd])$')
_UNITS = {'m': 'minutes', 'h': 'hours', 'd': 'days'}


def init_db(cursor):
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            created_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
            level VARCHAR(10) NOT NULL,
            source VARCHAR(50) NOT NULL,
            logger VARCHAR(120),
            title VARCHAR(255),
            message TEXT,
            context JSON NULL,
            KEY idx_created (created_at),
            KEY idx_level_created (level, created_at),
            KEY idx_source_created (source, created_at)
        )
    ''')


def parse_since(value: str) -> datetime:
    """Accepteert zowel '-1h' als een volledige ISO-tijdstempel."""
    match = _RELATIVE.match(value)
    if match:
        amount, unit = int(match.group(1)), match.group(2)
        return datetime.now() - timedelta(**{_UNITS[unit]: amount})
    return datetime.fromisoformat(value)


def _build_filters(level, source, since, until, q):
    clauses, params = [], []
    if level:
        clauses.append(f"level IN ({', '.join(['%s'] * len(level))})")
        params.extend(level)
    if source:
        clauses.append(f"source IN ({', '.join(['%s'] * len(source))})")
        params.extend(source)
    if since:
        clauses.append('created_at >= %s')
        params.append(since)
    if until:
        clauses.append('created_at <= %s')
        params.append(until)
    if q:
        clauses.append('(title LIKE %s OR message LIKE %s)')
        params.extend([f'%{q}%', f'%{q}%'])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    return where, params


@router.get('')
@router.get('/')
def list_events(
    level: list[str] = Query(default=[]),
    source: list[str] = Query(default=[]),
    since: str | None = None,
    until: str | None = None,
    q: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    _auth: dict = Depends(verify_api_key),
):
    unknown = [item for item in level if item not in LEVELS]
    if unknown:
        raise HTTPException(status_code=400, detail=f'unknown level(s): {unknown}')
    unknown_source = [item for item in source if item not in SOURCES]
    if unknown_source:
        raise HTTPException(status_code=400, detail=f'unknown source(s): {unknown_source}')
    try:
        since_value = parse_since(since) if since else None
        until_value = parse_since(until) if until else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f'invalid timestamp: {exc}') from exc

    limit = max(1, min(limit, MAX_LIMIT))
    offset = max(0, offset)
    where, params = _build_filters(level, source, since_value, until_value, q)
    # The level badges must show what's behind each chip, including chips that
    # are currently unchecked — so the counts query drops the level filter
    # while keeping every other filter the user applied.
    counts_where, counts_params = _build_filters([], source, since_value, until_value, q)

    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f'SELECT * FROM events {where} ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s',
                (*params, limit, offset),
            )
            events = cursor.fetchall()

            cursor.execute(f'SELECT COUNT(*) AS total FROM events {where}', tuple(params))
            total = (cursor.fetchone() or {}).get('total', 0)

            cursor.execute(
                f'SELECT level, COUNT(*) AS n FROM events {counts_where} GROUP BY level', tuple(counts_params)
            )
            counts = {row['level']: row['n'] for row in cursor.fetchall()}

        return {
            'events': events,
            'total': total,
            'counts': {name: counts.get(name, 0) for name in LEVELS},
        }
    finally:
        conn.close()


@router.delete('/{event_id}')
def delete_event(event_id: int, _auth: dict = Depends(require_admin())):
    """Remove one event. Admin only: the log is the audit trail of what went wrong."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM events WHERE id = %s', (event_id,))
        conn.commit()
        return {'status': 'ok'}
    finally:
        conn.close()


@router.delete('')
@router.delete('/')
def clear_events(_auth: dict = Depends(require_admin())):
    """Empty the event log. Admin only."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM events')
        conn.commit()
        return {'status': 'ok'}
    finally:
        conn.close()
