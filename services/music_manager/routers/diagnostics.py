
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.music_manager.database import get_db_connection
from services.music_manager.routers.users import verify_api_key

router = APIRouter(tags=['diagnostics'])


class CrashReportCreate(BaseModel):
    device_model: str
    os_version: str
    app_version_name: str
    app_version_code: int
    build_type: str
    ring_buffer_text: str
    stacktrace_text: str | None = None


def init_db(cursor):
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS crash_reports (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            device_model VARCHAR(255),
            os_version VARCHAR(50),
            app_version_name VARCHAR(50),
            app_version_code INT,
            build_type VARCHAR(20),
            stacktrace_text LONGTEXT,
            ring_buffer_text LONGTEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        )
    ''')


@router.post('/crash-reports')
def create_crash_report(report: CrashReportCreate, auth: dict = Depends(verify_api_key)):
    user_id = (auth.get('user') or {}).get('id')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                '''
                INSERT INTO crash_reports
                    (user_id, device_model, os_version, app_version_name, app_version_code,
                     build_type, stacktrace_text, ring_buffer_text)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ''',
                (
                    user_id, report.device_model, report.os_version, report.app_version_name,
                    report.app_version_code, report.build_type, report.stacktrace_text,
                    report.ring_buffer_text,
                )
            )
            conn.commit()
            return {'status': 'ok', 'id': cursor.lastrowid}
    finally:
        conn.close()
