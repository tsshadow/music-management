import logging
from fastapi import APIRouter, HTTPException, Depends
from services.music_manager.database import get_db_connection
from services.music_manager.routers.management import verify_api_key

router = APIRouter(tags=['radio'])
logger = logging.getLogger('music-manager.radio')


def init_db(cursor):
    cursor.execute(
        'CREATE TABLE IF NOT EXISTS radio_channels ('
        ' id INT AUTO_INCREMENT PRIMARY KEY,'
        ' slug VARCHAR(64) NOT NULL UNIQUE,'
        ' name VARCHAR(128) NOT NULL,'
        ' genre VARCHAR(128) NULL,'
        ' enabled TINYINT(1) NOT NULL DEFAULT 1,'
        ' created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
        ')'
    )
    cursor.execute(
        'CREATE TABLE IF NOT EXISTS radio_timeline ('
        ' id BIGINT AUTO_INCREMENT PRIMARY KEY,'
        ' channel_id INT NOT NULL,'
        ' track_id VARCHAR(64) NOT NULL,'
        ' title VARCHAR(512) NULL,'
        ' artist VARCHAR(512) NULL,'
        ' album VARCHAR(512) NULL,'
        ' cover_art VARCHAR(64) NULL,'
        ' duration_ms INT NOT NULL,'
        ' started_at DOUBLE NOT NULL,'
        ' ends_at DOUBLE NOT NULL,'
        ' INDEX idx_channel_started (channel_id, started_at),'
        ' INDEX idx_channel_ends (channel_id, ends_at)'
        ')'
    )
    # The single beta channel: genre NULL means "draw from the whole library".
    cursor.execute(
        "INSERT IGNORE INTO radio_channels (slug, name, genre) VALUES ('main', 'Radio', NULL)"
    )


@router.get('/channels')
def list_channels(_auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database unavailable')
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT slug, name, genre FROM radio_channels WHERE enabled = 1 ORDER BY id'
            )
            return {'channels': cursor.fetchall()}
    finally:
        conn.close()
