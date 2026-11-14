"""MuMa Wrapped: `/api/wrapped`, the year-in-review page (docs/designs/wrapped-page/).

Two tabs: `/user` is the reader's own listening, `/library` the whole server's, in the server
zone (`wrapped_server_tz`) so every reader sees the same figures. A tab is computed on its first
request and stored (`wrapped/snapshots.py`); a computation that takes longer than 20 seconds
answers 503 with Retry-After and still stores its result for the next request.

A user key is pinned to its own account, as on /api/listening: naming another account is 403.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import UTC, date, datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response

from services.common.config_store import ConfigStore
from services.music_manager.database import get_db_connection
from services.music_manager.identity import same_username
from services.music_manager.rbac import require_permission
from services.music_manager.routers.users import verify_api_key
from services.music_manager.wrapped import snapshots
from services.music_manager.wrapped.payload import LIBRARY, USER
from services.music_manager.wrapped.periods import Period, PeriodError, parse_key, parse_period, parse_zone

router = APIRouter(tags=['wrapped'])
logger = logging.getLogger('music-manager.wrapped')

#: How long a request waits for a computation before it answers 503.
COMPUTE_BUDGET_SECS = 20.0
RETRY_AFTER_SECS = 20
CACHE_CONTROL = 'private, max-age=300'
DEFAULT_SERVER_TZ = 'Europe/Amsterdam'

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix='wrapped')


def server_zone_name() -> str:
    """The Library tab's zone from the configuration, or Europe/Amsterdam when it is not a zone."""
    name = ConfigStore().get('wrapped_server_tz') or DEFAULT_SERVER_TZ
    try:
        parse_zone(name)
    except PeriodError:
        logger.warning('wrapped_server_tz %r is not a time zone; using %s', name, DEFAULT_SERVER_TZ)
        return DEFAULT_SERVER_TZ
    return name


def _connect():
    return get_db_connection()


def _bad_request(error: PeriodError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))


def _period(year: int | None, date_from: date | None, date_to: date | None) -> Period:
    try:
        return parse_period(year, date_from, date_to)
    except PeriodError as error:
        raise _bad_request(error) from None


def _reader(auth: dict, username: str | None) -> str:
    """The account a User tab is about: a user key reads its own, the system key whom it names."""
    if auth.get('type') == 'system':
        if not username:
            raise HTTPException(status_code=400, detail="The system key must name a 'username'")
        return username
    own = (auth.get('user') or {}).get('username')
    if username and not same_username(username, own):
        raise HTTPException(status_code=403, detail="Not allowed to read another user's Wrapped")
    if not own:
        raise HTTPException(status_code=403, detail='No account behind this key')
    return own


def _compute(kind: str, username: str | None, period: Period, zone_name: str) -> dict:
    zone = parse_zone(zone_name)
    future = _executor.submit(snapshots.get_or_compute, _connect, kind, username, period, zone)
    try:
        return future.result(timeout=COMPUTE_BUDGET_SECS)
    except FutureTimeout:
        raise HTTPException(
            status_code=503,
            detail='Wrapped is still being computed; try again shortly',
            headers={'Retry-After': str(RETRY_AFTER_SECS)},
        ) from None


PERIODS_SQL = """
    SELECT y, SUM(n) AS listens, SUM(own) AS own_listens FROM (
        SELECT YEAR(listened_at) AS y, COUNT(*) AS n, SUM(username = %s) AS own
        FROM scrobble_listens GROUP BY y
        UNION ALL
        SELECT YEAR(listened_at) AS y, COUNT(*) AS n, SUM(username = %s) AS own
        FROM scrobble_unmatched_listens GROUP BY y
    ) years
    WHERE y IS NOT NULL
    GROUP BY y
    ORDER BY y DESC
"""


@router.get('/periods')
def periods(response: Response, tz: str = Query('UTC'), auth: dict = Depends(verify_api_key)):
    """The years with any listen on the server, newest first, with the reader's own count.

    Years are UTC calendar years here: a listen in the first hours of 1 January local time may
    count for the year before, which only matters for a year with almost no listens.
    """
    try:
        zone = parse_zone(tz)
    except PeriodError as error:
        raise _bad_request(error) from None
    own = (auth.get('user') or {}).get('username') or ''
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute(PERIODS_SQL, (own, own))
            rows = cursor.fetchall() or []
    finally:
        conn.close()
    response.headers['Cache-Control'] = CACHE_CONTROL
    return {
        'years': [
            {'year': int(r['y']), 'listens': int(r['listens'] or 0), 'own_listens': int(r['own_listens'] or 0)}
            for r in rows
        ],
        'server_tz': server_zone_name(),
        'today': datetime.now(UTC).astimezone(zone).date().isoformat(),
    }


@router.get('/user')
def user_tab(
    response: Response,
    year: int | None = Query(None),
    date_from: date | None = Query(None, alias='from'),
    date_to: date | None = Query(None, alias='to'),
    tz: str = Query('UTC'),
    username: str | None = Query(None),
    auth: dict = Depends(verify_api_key),
):
    """The reader's own Wrapped for a year or a range, in the reader's zone (decision 8)."""
    period = _period(year, date_from, date_to)
    try:
        parse_zone(tz)
    except PeriodError as error:
        raise _bad_request(error) from None
    reader = _reader(auth, username)
    payload = _compute(USER, reader, period, tz)
    response.headers['Cache-Control'] = CACHE_CONTROL
    return payload


@router.get('/library')
def library_tab(
    response: Response,
    year: int | None = Query(None),
    date_from: date | None = Query(None, alias='from'),
    date_to: date | None = Query(None, alias='to'),
    _auth: dict = Depends(verify_api_key),
):
    """The whole server's Wrapped: every account, the collection and the system, in the server zone."""
    period = _period(year, date_from, date_to)
    payload = _compute(LIBRARY, None, period, server_zone_name())
    response.headers['Cache-Control'] = CACHE_CONTROL
    return payload


def _recompute(keys: list[tuple]) -> None:
    for kind, username, period_key, tz in keys:
        try:
            snapshots.get_or_compute(_connect, kind, username or None, parse_key(period_key), parse_zone(tz))
        except Exception:
            logger.exception('Recomputing Wrapped %s %s for %s failed', kind, period_key, username or 'the library')


@router.post('/refresh', status_code=202)
def refresh(
    body: dict = Body(...),
    _auth: dict = Depends(require_permission('wrapped.refresh')),
):
    """Drop the stored tabs of a period and compute them again in the background.

    Body: `scope` ('user' or 'library'), `year` or `from` and `to`, and for the User tab an
    optional `username` (all accounts without it).
    """
    kind = body.get('scope')
    if kind not in (USER, LIBRARY):
        raise HTTPException(status_code=400, detail="'scope' is 'user' or 'library'")
    try:
        period = parse_period(
            int(body['year']) if body.get('year') is not None else None,
            date.fromisoformat(body['from']) if body.get('from') else None,
            date.fromisoformat(body['to']) if body.get('to') else None,
        )
    except (PeriodError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            keys = snapshots.drop(cursor, kind, period, body.get('username') if kind == USER else None)
        conn.commit()
    finally:
        conn.close()
    if kind == LIBRARY and not keys:
        keys = [(LIBRARY, '', period.key, server_zone_name())]
    threading.Thread(target=_recompute, args=(keys,), name='wrapped-refresh', daemon=True).start()
    return {'queued': len(keys)}
