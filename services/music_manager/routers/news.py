"""News bulletins MuMa records for itself.

No feed publishes the NOS radio bulletin on demand, so the only way to have
"the news of this hour" available is to record it off the live stream. A tap of
an icecast MP3 stream is already a playable file — the frames are
self-contained — which is why nothing here transcodes.

Bulletins deliberately live outside the music library: ratings, genre curation,
scan statistics and scrobbles all key on that library, and a dozen news files a
day would be noise in every one of them.
"""

import logging

from fastapi import APIRouter

router = APIRouter(tags=['news'])
logger = logging.getLogger('music-manager.news')

DEFAULT_STREAM_URL = 'https://icecast.omroep.nl/radio1-bb-mp3'
DEFAULT_DURATION_SECONDS = 600
DEFAULT_LEAD_SECONDS = 5
DEFAULT_RETENTION = 12


def init_db(cursor):
    cursor.execute(
        'CREATE TABLE IF NOT EXISTS news_sources ('
        ' id INT AUTO_INCREMENT PRIMARY KEY,'
        ' slug VARCHAR(64) NOT NULL UNIQUE,'
        ' name VARCHAR(128) NOT NULL,'
        ' stream_url VARCHAR(512) NOT NULL,'
        ' minute_of_hour TINYINT NOT NULL DEFAULT 0,'
        ' duration_seconds INT NOT NULL DEFAULT 600,'
        ' lead_seconds INT NOT NULL DEFAULT 5,'
        ' retention_count INT NOT NULL DEFAULT 12,'
        ' enabled TINYINT(1) NOT NULL DEFAULT 1,'
        ' last_error VARCHAR(512) NULL,'
        ' last_success_at DOUBLE NULL,'
        ' created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
        ')'
    )
    cursor.execute(
        'CREATE TABLE IF NOT EXISTS news_bulletins ('
        ' id BIGINT AUTO_INCREMENT PRIMARY KEY,'
        ' source_id INT NOT NULL,'
        ' started_at DOUBLE NOT NULL,'
        ' duration_ms INT NOT NULL,'
        ' size_bytes BIGINT NOT NULL,'
        ' filename VARCHAR(255) NOT NULL,'
        ' created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,'
        ' INDEX idx_source_started (source_id, started_at)'
        ')'
    )
    # The one seeded source: the hourly bulletin on NPO Radio 1.
    cursor.execute(
        'INSERT IGNORE INTO news_sources'
        ' (slug, name, stream_url, minute_of_hour, duration_seconds, lead_seconds,'
        ' retention_count) VALUES (%s, %s, %s, %s, %s, %s, %s)',
        ('nos', 'NOS Nieuws (NPO Radio 1)', DEFAULT_STREAM_URL, 0,
         DEFAULT_DURATION_SECONDS, DEFAULT_LEAD_SECONDS, DEFAULT_RETENTION),
    )
