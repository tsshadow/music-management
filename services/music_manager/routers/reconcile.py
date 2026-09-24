"""Admin endpoints that reconcile muma's listening history against LMS's own listen table.

Mounted under `/api/scrobble/reconcile`. The logic lives in `services.music_manager.scrobble_reconcile`;
this module only opens the connections, guards the admin role, and runs the apply in the
background the way `POST /api/scanner/relink-orphans` does. See bug report 039 and the dated
"LMS listen reconcile" section of docs/designs/ratings-scrobbling/technical.md.
"""

from __future__ import annotations

import contextlib
import logging
import threading

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from services.music_manager import scrobble_reconcile
from services.music_manager.database import get_db_connection
from services.music_manager.rbac import require_admin

router = APIRouter(tags=['scrobble-reconcile'])
logger = logging.getLogger('music-manager.scrobble-reconcile')

#: The running flag and the last apply's result, for GET /lms/status. Per process.
reconcile_state: dict = {'running': False, 'last': None, 'error': None}
_state_lock = threading.Lock()


class ReconcileRequest(BaseModel):
    """Body of POST /lms: whose listens, and which of the two repairs to write."""

    username: str | None = None
    apply_shifted: bool = False
    insert_lms_only: bool = False


def _servers():
    """Open every LMS database this process can see, read-only; 503 when there is none."""
    from services.music_manager.routers.users import lms_db_targets

    servers = scrobble_reconcile.open_servers(lms_db_targets())
    if not servers:
        raise HTTPException(status_code=503, detail='No LMS database is visible to music-manager')
    return servers


def _close(servers) -> None:
    """Close the SQLite handles `_servers()` opened."""
    for server_conn, _ in servers:
        with contextlib.suppress(Exception):
            server_conn.close()


@router.get('/lms')
def api_reconcile_dry_run(
    username: str | None = Query(None, description='Only this user; every user when omitted'),
    _auth: dict = Depends(require_admin()),
):
    """Dry run: how muma's listens compare with LMS's, per class, with a bounded sample. Writes nothing."""
    servers = _servers()
    try:
        conn = get_db_connection()
        if not conn:
            raise HTTPException(status_code=500, detail='Database connection failed')
        try:
            return scrobble_reconcile.dry_run(conn, servers, username)
        finally:
            conn.close()
    finally:
        _close(servers)


def run_reconcile_apply(request: ReconcileRequest) -> dict | None:
    """Background body of POST /lms: write the chosen repairs, record the totals as an INFO event."""
    result = None
    error = None
    servers = []
    try:
        servers = _servers()
        conn = get_db_connection()
        if not conn:
            raise RuntimeError('Database connection failed')
        try:
            result = scrobble_reconcile.apply(
                conn, servers, request.username, request.apply_shifted, request.insert_lms_only
            )
        finally:
            conn.close()
    except HTTPException as exc:
        error = str(exc.detail)
    except Exception as exc:
        logger.exception('scrobble reconcile failed')
        error = str(exc)
    finally:
        _close(servers)
        with _state_lock:
            reconcile_state['running'] = False
            reconcile_state['last'] = result
            reconcile_state['error'] = error
    if result is not None:
        _emit(result)
    return result


def _emit(result: dict) -> None:
    """Record an apply's totals in the event log."""
    written = result['written']
    try:
        from services.common.Helpers.EventService import event_service

        event_service.emit(
            level='INFO',
            title='Listens reconciled against LMS',
            message=(
                f"{written['shifted_fixed']} shifted listens restored to LMS's time, "
                f"{written['lms_only_inserted']} lost listens inserted, "
                f"{written['collisions']} skipped on a duplicate, "
                f"{written['changed_since_read']} changed while the run was reading."
            ),
            source='music-manager',
            logger=logger.name,
            context=result,
        )
    except Exception as exc:
        logger.warning('Could not record the scrobble reconcile event: %s', exc)


@router.post('/lms')
def api_reconcile_apply(
    body: ReconcileRequest,
    background_tasks: BackgroundTasks,
    _auth: dict = Depends(require_admin()),
):
    """Start an apply in the background; its outcome is on GET /lms/status and in the event log."""
    if not (body.apply_shifted or body.insert_lms_only):
        raise HTTPException(status_code=400, detail='Nothing to apply: set apply_shifted and/or insert_lms_only')
    with _state_lock:
        if reconcile_state['running']:
            raise HTTPException(status_code=409, detail='A reconcile is already running')
        reconcile_state['running'] = True
    background_tasks.add_task(run_reconcile_apply, body)
    return {'message': 'Scrobble reconcile started in background', 'last': reconcile_state['last']}


@router.get('/lms/status')
def api_reconcile_status(_auth: dict = Depends(require_admin())):
    """Whether an apply is running, and the result (or error) of the last one in this process."""
    return {
        'running': reconcile_state['running'],
        'last': reconcile_state['last'],
        'error': reconcile_state['error'],
    }
