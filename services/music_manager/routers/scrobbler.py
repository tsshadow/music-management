import time
from datetime import datetime

import requests
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel

from services.music_manager.api_key import is_system_api_key
from services.music_manager.database import get_db_connection
from services.music_manager.scrobble_rematch import find_track, record_match

router = APIRouter(tags=['scrobble'])


def verify_api_key(x_api_key: str | None = Header(None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail='Missing API Key')
    if is_system_api_key(x_api_key):
        return {'type': 'system'}
    from services.music_manager.routers.users import verify_token

    try:
        res = verify_token(x_api_key)
        if res.get('status') == 'ok':
            return res
    except Exception:
        pass
    raise HTTPException(status_code=401, detail='Invalid API key')


class ScrobbleEvent(BaseModel):
    """One play reported by a client.

    `source` says where the play happened -- `frontend`, `mobile`, `auto`, `lms-web`,
    `listenbrainz` -- rather than which server relayed it. `played_secs` is how long the track was
    actually played; both are optional, so a client that has not been updated still scrobbles.
    """

    artist_name: str
    track_title: str
    album_name: str | None = None
    mbid_track: str | None = None
    mbid_artist: str | None = None
    listened_at: int | None = None
    username: str
    source: str = 'manual'
    played_secs: int | None = None


def init_db(cursor):
    """Create the scrobble tables, and bring an older copy of them up to date.

    `listened_at` carries an explicit DEFAULT on purpose. Without one, a server running with
    `explicit_defaults_for_timestamp=OFF` (every MariaDB before 10.10) gives the first TIMESTAMP
    column of a table `ON UPDATE CURRENT_TIMESTAMP` as well, and then every UPDATE of a row --
    a rematch miss, a played_secs top-up, an account merge -- silently moves the listen to now.
    See docs/bug-reports/039-listened-at-rewritten-on-every-rematch.md.
    """
    cursor.execute(
        '\n        CREATE TABLE IF NOT EXISTS scrobble_listens (\n            id INT AUTO_INCREMENT PRIMARY KEY,\n            track_id INT,\n            listened_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,\n            username VARCHAR(255) NOT NULL,\n            source VARCHAR(50),\n            mbid_track VARCHAR(36),\n            match_method ENUM(\'exact\', \'normalized\', \'base_title\', \'fuzzy\') NOT NULL DEFAULT \'exact\',\n            match_score TINYINT UNSIGNED NULL,\n            played_secs INT UNSIGNED NULL,\n            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n            UNIQUE KEY (username, listened_at, track_id),\n            INDEX idx_listens_track_user (track_id, username)\n        )\n    '
    )
    cursor.execute(
        '\n        CREATE TABLE IF NOT EXISTS scrobble_unmatched_listens (\n            id INT AUTO_INCREMENT PRIMARY KEY,\n            artist_name VARCHAR(512),\n            track_title VARCHAR(512),\n            album_name VARCHAR(512),\n            mbid_track VARCHAR(36),\n            mbid_artist VARCHAR(36),\n            listened_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,\n            username VARCHAR(255) NOT NULL,\n            source VARCHAR(50),\n            data JSON,\n            attempts INT NOT NULL DEFAULT 0,\n            last_attempt_at TIMESTAMP NULL,\n            played_secs INT UNSIGNED NULL,\n            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n            UNIQUE KEY (username, listened_at, artist_name, track_title)\n        )\n    '
    )
    cursor.execute(
        '\n        CREATE TABLE IF NOT EXISTS scrobble_imports (\n            id INT AUTO_INCREMENT PRIMARY KEY,\n            username VARCHAR(255) NOT NULL,\n            lb_username VARCHAR(255) NOT NULL,\n            status VARCHAR(50) NOT NULL,\n            total_found INT DEFAULT 0,\n            processed INT DEFAULT 0,\n            last_error TEXT,\n            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n            finished_at TIMESTAMP NULL\n        )\n    '
    )
    # played_secs on installations that predate it. The CREATE TABLE statements above only run for
    # a database that has neither table, so an existing stack would never see the column otherwise.
    # Mirrors migrate_v12_listen_played_secs.sql, which is what production runs.
    # Written out per table rather than looped over an f-string: a table name cannot be a bound
    # parameter, and a formatted statement here is indistinguishable from an injectable one to
    # anything reading the code, semgrep included.
    cursor.execute("SHOW COLUMNS FROM scrobble_listens LIKE 'played_secs'")
    if not cursor.fetchone():
        cursor.execute('ALTER TABLE scrobble_listens ADD COLUMN played_secs INT UNSIGNED NULL')
    cursor.execute("SHOW COLUMNS FROM scrobble_unmatched_listens LIKE 'played_secs'")
    if not cursor.fetchone():
        cursor.execute('ALTER TABLE scrobble_unmatched_listens ADD COLUMN played_secs INT UNSIGNED NULL')

    # The unique keys above lead on `username`, which answers "my listens between
    # two dates" and nothing else. /api/listening also asks for everybody's, where
    # there is no username to seek on. Mirrors migrate_v20_listening_indexes.sql,
    # which is what production runs.
    cursor.execute('ALTER TABLE scrobble_listens ADD INDEX IF NOT EXISTS idx_listens_listened_at (listened_at)')
    cursor.execute(
        'ALTER TABLE scrobble_unmatched_listens ADD INDEX IF NOT EXISTS idx_unmatched_listened_at (listened_at)'
    )
    # Every per-track question -- a play count, a track's history, the rematch
    # moving a listen onto a track -- seeks on track_id, which no key led with.
    # Mirrors migrate_v34_primary_artist_and_listen_track_indexes.sql.
    cursor.execute('ALTER TABLE scrobble_listens ADD INDEX IF NOT EXISTS idx_listens_track_user (track_id, username)')
    # An existing table keeps whatever its CREATE gave it, ON UPDATE included; this
    # removes it. Mirrors migrate_v33_listened_at_no_on_update.sql.
    # Written out per table for the same reason as the played_secs ALTERs above.
    if _listened_at_rewrites_itself(cursor, 'scrobble_listens'):
        cursor.execute('ALTER TABLE scrobble_listens MODIFY listened_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP')
    if _listened_at_rewrites_itself(cursor, 'scrobble_unmatched_listens'):
        cursor.execute(
            'ALTER TABLE scrobble_unmatched_listens MODIFY listened_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP'
        )


def _listened_at_rewrites_itself(cursor, table: str) -> bool:
    """Whether `table.listened_at` carries ON UPDATE CURRENT_TIMESTAMP.

    Asked first rather than running the MODIFY unconditionally: the long UNIQUE key on
    scrobble_unmatched_listens is a hash key, which rules out an in-place ALTER, so every
    unconditional MODIFY would copy the whole table on each start.
    """
    cursor.execute(
        'SELECT COUNT(*) AS n FROM information_schema.columns '
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = 'listened_at' "
        "AND LOWER(extra) LIKE '%%on update%%'",
        (table,),
    )
    row = cursor.fetchone()
    return bool(row and row['n'])


@router.post('/event')
def handle_scrobble_event(event: ScrobbleEvent, _auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            found = find_track(cursor, event.artist_name, event.track_title)
            row = {'id': found[0]} if found else None
            listened_at = datetime.fromtimestamp(event.listened_at) if event.listened_at else datetime.now()
            # A zero or negative playing time says the client had nothing to report, which is not
            # the same claim as "played for no time at all" -- store the absence, not a number.
            played_secs = event.played_secs if event.played_secs and event.played_secs > 0 else None
            if found:
                track_id, tier, score = found
                record_match(
                    cursor,
                    track_id,
                    listened_at,
                    event.username,
                    event.source,
                    tier,
                    score,
                    event.mbid_track,
                    played_secs,
                )
            else:
                cursor.execute(
                    '\n                    INSERT INTO scrobble_unmatched_listens (artist_name, track_title, album_name, mbid_track, mbid_artist, listened_at, username, source, played_secs)\n                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)\n                    ON DUPLICATE KEY UPDATE artist_name = VALUES(artist_name), played_secs = COALESCE(VALUES(played_secs), played_secs)\n                ',
                    (
                        event.artist_name,
                        event.track_title,
                        event.album_name,
                        event.mbid_track,
                        event.mbid_artist,
                        listened_at,
                        event.username,
                        event.source,
                        played_secs,
                    ),
                )
            conn.commit()
            return {'status': 'success', 'matched': row is not None}
    finally:
        conn.close()


def _process_listens_page(listens, conn, username, import_id, total_found):
    processed = 0
    max_ts = None
    with conn.cursor() as cursor:
        cursor.execute('UPDATE scrobble_imports SET total_found = %s WHERE id = %s', (total_found, import_id))
        conn.commit()
        for listen in listens:
            metadata = listen.get('track_metadata', {})
            artist_name = metadata.get('artist_name')
            track_title = metadata.get('track_name')
            album_name = metadata.get('release_name')
            listened_at_ts = listen.get('listened_at')
            if max_ts is None or listened_at_ts < max_ts:
                max_ts = listened_at_ts
            if not artist_name or not track_title or (not listened_at_ts):
                continue
            listened_at = datetime.fromtimestamp(listened_at_ts)
            found = find_track(cursor, artist_name, track_title)
            row = {'id': found[0]} if found else None
            if row:
                track_id = row['id']
                track_id, tier, score = found
                record_match(cursor, track_id, listened_at, username, 'listenbrainz', tier, score)
            else:
                cursor.execute(
                    '\n                    INSERT INTO scrobble_unmatched_listens (artist_name, track_title, album_name, listened_at, username, source)\n                    VALUES (%s, %s, %s, %s, %s, %s)\n                    ON DUPLICATE KEY UPDATE artist_name = artist_name\n                ',
                    (artist_name, track_title, album_name, listened_at, username, 'listenbrainz'),
                )
            processed += 1
            if processed % 10 == 0:
                cursor.execute('UPDATE scrobble_imports SET processed = %s WHERE id = %s', (processed, import_id))
                conn.commit()
    return (processed, max_ts)


def run_listenbrainz_import(import_id: int, username: str, lb_username: str, token: str | None = None):
    conn = get_db_connection()
    if not conn:
        print(f'Failed to connect to DB for import {import_id}')
        return
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE scrobble_imports SET status = 'running' WHERE id = %s", (import_id,))
            conn.commit()
        base_url = 'https://api.listenbrainz.org/1'
        headers = {}
        if token:
            headers['Authorization'] = f'Token {token}'
        processed_total = 0
        total_found = 0
        max_ts = None
        pages_to_fetch = 100
        for page in range(pages_to_fetch):
            params = {'count': 100}
            if max_ts:
                params['max_ts'] = max_ts
            print(f'Fetching listens for {lb_username} from ListenBrainz (page {page + 1}, max_ts={max_ts})...')
            response = requests.get(
                f'{base_url}/user/{lb_username}/listens', params=params, headers=headers, timeout=30
            )
            response.raise_for_status()
            data = response.json()
            listens = data.get('payload', {}).get('listens', [])
            if not listens:
                print('No more listens found.')
                break
            total_found += len(listens)
            processed_page, page_max_ts = _process_listens_page(listens, conn, username, import_id, total_found)
            processed_total += processed_page
            max_ts = page_max_ts
            time.sleep(1)
            if len(listens) < 100:
                break
            max_ts = max_ts - 1
        with conn.cursor() as cursor:
            cursor.execute(
                "\n                UPDATE scrobble_imports\n                SET status = 'completed', processed = %s, finished_at = CURRENT_TIMESTAMP\n                WHERE id = %s\n            ",
                (processed_total, import_id),
            )
            conn.commit()
            print(f'Import {import_id} completed. Processed {processed_total} listens.')
    except Exception as e:
        print(f'Error during import {import_id}: {str(e)}')
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE scrobble_imports SET status = 'failed', last_error = %s WHERE id = %s", (str(e), import_id)
                )
                conn.commit()
        except Exception:
            pass
    finally:
        conn.close()


class ImportRequest(BaseModel):
    username: str
    lb_username: str | None = None
    token: str | None = None


@router.get('/import/latest')
def get_latest_imports(_auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT * FROM scrobble_imports ORDER BY started_at DESC LIMIT 10')
            return cursor.fetchall()
    finally:
        conn.close()


@router.post('/import/listenbrainz')
def trigger_lb_import(req: ImportRequest, background_tasks: BackgroundTasks, _auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                '\n                INSERT INTO scrobble_imports (username, lb_username, status)\n                VALUES (%s, %s, %s)\n            ',
                (req.username, req.lb_username or req.username, 'pending'),
            )
            import_id = cursor.lastrowid
            conn.commit()
            background_tasks.add_task(
                run_listenbrainz_import, import_id, req.username, req.lb_username or req.username, req.token
            )
            return {'status': 'ok', 'import_id': import_id, 'lb_username': req.lb_username or req.username}
    finally:
        conn.close()
