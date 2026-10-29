import time
from datetime import datetime

import requests
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from services.music_manager.database import get_db_connection
from services.music_manager.identity import canonical_username, same_username
from services.music_manager.rbac import is_admin_auth
from services.music_manager.routers.users import verify_api_key
from services.music_manager.scrobble_rematch import find_track, record_match

router = APIRouter(tags=['scrobble'])


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


@router.post('/event')
def handle_scrobble_event(event: ScrobbleEvent, auth: dict = Depends(verify_api_key)):
    """Record one play in `event.username`'s history.

    LMS reports every play here with the system key and names the listener. A user key
    may only report its own plays: the body's `username` used to be taken at its word,
    so any account could write listens -- and through them statistics and mixes -- into
    another account's history. Admins keep the system key's reach, as for imports.

    What is stored is the account's own spelling, never the one in the body: a user key
    stores its own `users.username`, the system key and admins the canonical spelling of
    the name they sent. LMS relayed a case-variant login ("User" for "user") verbatim,
    which split one listener's history in two for everything that groups in Python and
    for LMS itself (docs/bug-reports/074-login-case-forks-user-identity.md).
    """
    if not _may_write_history_for(auth, event.username):
        raise HTTPException(status_code=403, detail='You can only scrobble to your own history')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            username = _history_owner(cursor, auth, event.username)
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
                    username,
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
                        username,
                        event.source,
                        played_secs,
                    ),
                )
            conn.commit()
            return {'status': 'success', 'matched': row is not None}
    finally:
        conn.close()


def _process_listens_page(listens, conn, username, import_id, total_found):
    """Store one page of ListenBrainz listens; returns (processed, oldest timestamp on the page)."""
    processed = 0
    oldest_ts = None
    with conn.cursor() as cursor:
        cursor.execute('UPDATE scrobble_imports SET total_found = %s WHERE id = %s', (total_found, import_id))
        conn.commit()
        for listen in listens:
            metadata = listen.get('track_metadata', {})
            artist_name = metadata.get('artist_name')
            track_title = metadata.get('track_name')
            album_name = metadata.get('release_name')
            listened_at_ts = listen.get('listened_at')
            # A listen without a timestamp cannot page anything; comparing it raised TypeError.
            if listened_at_ts is not None and (oldest_ts is None or listened_at_ts < oldest_ts):
                oldest_ts = listened_at_ts
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
    return (processed, oldest_ts)


# ListenBrainz serves at most 100 listens per request.
LB_PAGE_SIZE = 100
# Pages one run fetches before it stops. A run that hits this ends as `truncated`, not
# `completed`, and the next import for the same account carries on where it stopped.
LB_MAX_PAGES = 100
# Statuses a run can end in that leave history below `oldest_listened_ts` unimported.
RESUMABLE_STATUSES = ('truncated', 'failed')


def _resume_point(cursor, import_id: int, username: str, lb_username: str) -> int | None:
    """The `max_ts` a new import starts from.

    When the previous import for the same account was cut off -- it hit LB_MAX_PAGES,
    or failed part way -- this run continues below the oldest listen that run reached.
    Otherwise it starts at the newest listen (None). A resumed run does not revisit
    listens made after the run it resumes; the next import after it does.
    """
    cursor.execute(
        'SELECT status, oldest_listened_ts FROM scrobble_imports'
        ' WHERE username = %s AND lb_username = %s AND id < %s ORDER BY id DESC LIMIT 1',
        (username, lb_username, import_id),
    )
    previous = cursor.fetchone()
    if previous and previous.get('status') in RESUMABLE_STATUSES and previous.get('oldest_listened_ts'):
        return int(previous['oldest_listened_ts'])
    return None


def run_listenbrainz_import(import_id: int, username: str, lb_username: str, token: str | None = None):
    """Import a ListenBrainz history page by page, newest first, into the listen tables.

    Pages with `max_ts`, which ListenBrainz treats as exclusive: the next page asks for
    listens strictly older than the oldest one seen. The old `max_ts - 1` skipped every
    listen sharing the boundary second. The oldest timestamp reached is stored on the
    import row after every page, so a run that stops early -- LB_MAX_PAGES reached
    (`truncated`) or an error (`failed`) -- is continued by the next import; before, the
    page cap silently ended at 10.000 listens and reported `completed`.
    """
    conn = get_db_connection()
    if not conn:
        print(f'Failed to connect to DB for import {import_id}')
        return
    try:
        with conn.cursor() as cursor:
            max_ts = _resume_point(cursor, import_id, username, lb_username)
            # Carried over at once, so a resumed run that dies before its first page
            # still hands the same starting point to the run after it.
            cursor.execute(
                "UPDATE scrobble_imports SET status = 'running', oldest_listened_ts = %s WHERE id = %s",
                (max_ts, import_id),
            )
            conn.commit()
        base_url = 'https://api.listenbrainz.org/1'
        headers = {}
        if token:
            headers['Authorization'] = f'Token {token}'
        processed_total = 0
        total_found = 0
        status = 'truncated'
        for page in range(LB_MAX_PAGES):
            params = {'count': LB_PAGE_SIZE}
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
                status = 'completed'
                break
            total_found += len(listens)
            processed_page, page_oldest_ts = _process_listens_page(listens, conn, username, import_id, total_found)
            processed_total += processed_page
            if page_oldest_ts is None or (max_ts is not None and page_oldest_ts >= max_ts):
                # Nothing to page on: asking again would return this same page forever.
                print('ListenBrainz returned a page without usable timestamps; stopping.')
                status = 'completed'
                break
            max_ts = page_oldest_ts
            with conn.cursor() as cursor:
                cursor.execute('UPDATE scrobble_imports SET oldest_listened_ts = %s WHERE id = %s', (max_ts, import_id))
                conn.commit()
            time.sleep(1)
            if len(listens) < LB_PAGE_SIZE:
                status = 'completed'
                break
        with conn.cursor() as cursor:
            cursor.execute(
                'UPDATE scrobble_imports SET status = %s, processed = %s, finished_at = CURRENT_TIMESTAMP'
                ' WHERE id = %s',
                (status, processed_total, import_id),
            )
            conn.commit()
            print(f'Import {import_id} {status}. Processed {processed_total} listens.')
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
def get_latest_imports(auth: dict = Depends(verify_api_key)):
    """The ten newest ListenBrainz imports: every account's for an admin, the caller's own otherwise.

    A row carries the account, its ListenBrainz name and the import's error text, so a plain
    account sees only the imports into its own history (issue #38). "Its own" by the account's
    stored spelling, which is what `_history_owner` writes the row under; the column's
    case-insensitive collation also matches an older row written in another case.
    """
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            if is_admin_auth(auth):
                cursor.execute('SELECT * FROM scrobble_imports ORDER BY started_at DESC LIMIT 10')
            else:
                username = ((auth or {}).get('user') or {}).get('username')
                if not username:
                    return []
                cursor.execute(
                    'SELECT * FROM scrobble_imports WHERE username = %s ORDER BY started_at DESC LIMIT 10',
                    (username,),
                )
            return cursor.fetchall()
    finally:
        conn.close()


def _may_write_history_for(auth: dict, username: str) -> bool:
    """An account may write (scrobble, import) into its own history; the system key and admins into anyone's.

    "Its own" whatever case the name is sent in: account names are case-insensitive
    (services/music_manager/identity.py).
    """
    if is_admin_auth(auth):
        return True
    user = (auth or {}).get('user') or {}
    return (auth or {}).get('type') == 'user' and same_username(user.get('username'), username)


def _history_owner(cursor, auth: dict, username: str) -> str:
    """The spelling a listen written for `username` is stored under.

    A user key writes only its own history (`_may_write_history_for`), so its own
    `users.username` is the answer without asking the database. The system key and
    admins name someone; that name is resolved to the account's own spelling.
    """
    user = (auth or {}).get('user') or {}
    if (auth or {}).get('type') == 'user' and same_username(user.get('username'), username):
        return user['username']
    return canonical_username(cursor, username) or username


@router.post('/import/listenbrainz')
def trigger_lb_import(req: ImportRequest, background_tasks: BackgroundTasks, auth: dict = Depends(verify_api_key)):
    """Start a ListenBrainz import into `req.username`'s history.

    Only for the caller's own account, unless the caller is an admin or the system key:
    the listens land in that user's history and feed their statistics and mixes.
    """
    if not _may_write_history_for(auth, req.username):
        raise HTTPException(status_code=403, detail='You can only import into your own history')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            # Stored under the account's own spelling, like a scrobble; the ListenBrainz name
            # defaults to the name as sent, since that one belongs to ListenBrainz, not to us.
            owner = _history_owner(cursor, auth, req.username)
            cursor.execute(
                '\n                INSERT INTO scrobble_imports (username, lb_username, status)\n                VALUES (%s, %s, %s)\n            ',
                (owner, req.lb_username or req.username, 'pending'),
            )
            import_id = cursor.lastrowid
            conn.commit()
            background_tasks.add_task(
                run_listenbrainz_import, import_id, owner, req.lb_username or req.username, req.token
            )
            return {'status': 'ok', 'import_id': import_id, 'lb_username': req.lb_username or req.username}
    finally:
        conn.close()
