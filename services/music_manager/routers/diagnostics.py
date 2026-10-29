import contextlib
import hashlib
import threading
from typing import Literal

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.common.config_store import ConfigStore as Settings
from services.music_manager.database import get_db_connection
from services.music_manager.routers.users import verify_api_key

router = APIRouter(tags=['diagnostics'])

_settings = Settings()

CRASH_STATUSES = ('new', 'analyzing', 'mr_open', 'done', 'failed')


class CrashReportCreate(BaseModel):
    device_model: str
    os_version: str
    app_version_name: str
    app_version_code: int
    build_type: str
    ring_buffer_text: str
    stacktrace_text: str | None = None


class CrashReportStatusUpdate(BaseModel):
    status: Literal['new', 'analyzing', 'mr_open', 'done', 'failed']


def _post_crash_hook(report_id: int) -> None:
    url = _settings.get('crash_hook_url')
    if not url:
        return
    # The hook is best-effort; the report itself is already stored.
    with contextlib.suppress(requests.RequestException):
        requests.post(url, json={'id': report_id}, timeout=5)


def _require_system(auth: dict) -> None:
    if auth.get('type') != 'system':
        raise HTTPException(status_code=403, detail='System API key required')


@router.post('/crash-reports')
def create_crash_report(report: CrashReportCreate, auth: dict = Depends(verify_api_key)):
    user_id = (auth.get('user') or {}).get('id')
    stacktrace_hash = None
    if report.stacktrace_text:
        stacktrace_hash = hashlib.sha256(report.stacktrace_text.encode('utf-8')).hexdigest()
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                '''
                INSERT INTO crash_reports
                    (user_id, device_model, os_version, app_version_name, app_version_code,
                     build_type, stacktrace_text, ring_buffer_text, stacktrace_hash)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''',
                (
                    user_id,
                    report.device_model,
                    report.os_version,
                    report.app_version_name,
                    report.app_version_code,
                    report.build_type,
                    report.stacktrace_text,
                    report.ring_buffer_text,
                    stacktrace_hash,
                ),
            )
            conn.commit()
            report_id = cursor.lastrowid
    finally:
        conn.close()
    threading.Thread(
        target=_post_crash_hook,
        args=(report_id,),
        daemon=True,
        name=f'crash-hook-{report_id}',
    ).start()
    return {'status': 'ok', 'id': report_id}


@router.get('/crash-reports/{report_id}')
def get_crash_report(report_id: int, auth: dict = Depends(verify_api_key)):
    _require_system(auth)
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT * FROM crash_reports WHERE id = %s', (report_id,))
            row = cursor.fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail='Crash report not found')
    return row


@router.patch('/crash-reports/{report_id}/status')
def update_crash_report_status(report_id: int, update: CrashReportStatusUpdate, auth: dict = Depends(verify_api_key)):
    _require_system(auth)
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                'UPDATE crash_reports SET status = %s WHERE id = %s',
                (update.status, report_id),
            )
            conn.commit()
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail='Crash report not found')
    finally:
        conn.close()
    return {'status': 'ok'}
