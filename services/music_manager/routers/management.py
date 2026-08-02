import os
from typing import Any

import markdown
from fastapi import APIRouter, BackgroundTasks, Body, Depends, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import docker
from services.common.Helpers.GenreRulesHelper import BLACK, VALID_STATES, WHITE
from services.common.Helpers.ProcessedFilesHelper import ProcessedFilesHelper
from services.common.version_helper import get_changelog, get_release_notes, get_version
from services.music_manager.database import get_db_connection

router = APIRouter(tags=['management'])

class ArtistGenreRule(BaseModel):
    artist_name: str
    genre_id: int

class GenreDecisionRequest(BaseModel):
    """A curation decision, optionally rewriting the genre to one or more others.

    `canonical_id` is the single-target form kept for existing callers;
    `canonical_ids` is the general one, needed for contractions like 'Upterror'
    becoming 'Uptempo Hardcore' plus 'Terror'. Whichever is given ends up in
    `rules_genre_expansions`.
    """
    state: str
    canonical_id: int | None = None
    canonical_ids: list[int] | None = None

    def targets(self) -> list[int]:
        """The rewrite targets, de-duplicated, order preserved."""
        raw = self.canonical_ids if self.canonical_ids is not None else ([self.canonical_id] if self.canonical_id is not None else [])
        return list(dict.fromkeys(target for target in raw if target is not None))

class LabelGenreRule(BaseModel):
    label_name: str
    genre_id: int
API_KEY = os.getenv('API_KEY') or os.getenv('MUMA_API_KEY') or '00000000-0000-4000-8000-000000000000'

def verify_api_key(x_api_key: str | None=Header(None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail='Missing API Key')
    if API_KEY and x_api_key == API_KEY:
        return {'type': 'system'}
    from services.music_manager.routers.users import verify_token
    try:
        res = verify_token(x_api_key)
        if res.get('status') == 'ok':
            return res
    except Exception:
        pass
    raise HTTPException(status_code=401, detail='Invalid API key')

def init_db(_cursor):
    pass

@router.get('/rules')
def get_genre_rules(_auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT id, name, corrected_genre FROM rules_genres ORDER BY name')
            genres = cursor.fetchall()
            cursor.execute("SHOW TABLES LIKE 'rules_ignored_genres'")
            ignored = []
            if cursor.fetchone():
                cursor.execute('SELECT name FROM rules_ignored_genres ORDER BY name')
                ignored = [{'name': r['name']} for r in cursor.fetchall()]
            return {'genres': genres, 'ignored_genres': ignored}
    finally:
        conn.close()

@router.get('/artists')
def search_artists(q: str='', _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT id, name FROM library_artists WHERE name LIKE %s LIMIT 50', (f'%{q}%',))
            return cursor.fetchall()
    finally:
        conn.close()

@router.get('/labels')
def search_labels(q: str='', _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT id, name FROM library_labels WHERE name LIKE %s LIMIT 50', (f'%{q}%',))
            return cursor.fetchall()
    finally:
        conn.close()

@router.get('/config')
def get_config(_auth: dict=Depends(verify_api_key)):
    version = '1.3.0'
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'VERSION'), encoding='utf-8') as f:
            version = f.read().strip()
    except Exception:
        pass
    return {'DB_HOST': os.getenv('DB_HOST'), 'DB_NAME': os.getenv('DB_DB'), 'VERSION': version, 'PHPMYADMIN_URL': os.getenv('PHPMYADMIN_URL', 'http://muma.example.com:8002')}

@router.get('/about', response_class=HTMLResponse)
def get_about(_auth: dict=Depends(verify_api_key)):
    readme_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'README.md')
    content = '# Music Manager\nDocumentation not found.'
    if os.path.exists(readme_path):
        with open(readme_path, encoding='utf-8') as f:
            content = f.read()
    html = markdown.markdown(content, extensions=['fenced_code', 'tables'])
    return html

@router.get('/stats')
def get_stats_proxy(_auth: dict=Depends(verify_api_key)):
    from services.music_manager.routers.stats import get_stats
    return get_stats(_auth)

@router.get('/system/containers')
def get_containers(_auth: dict=Depends(verify_api_key)):
    try:
        client = docker.from_env()
        containers = []
        for container in client.containers.list(all=True):
            if any(name in container.name for name in ['muma', 'music-management', 'music-manager', 'db', 'lms']):
                containers.append({'id': container.short_id, 'name': container.name, 'status': container.status, 'image': container.image.tags[0] if container.image.tags else 'unknown'})
        return sorted(containers, key=lambda x: x['name'])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.get('/system/logs/{name}')
def get_logs(name: str, tail: int=200, _auth: dict=Depends(verify_api_key)):
    try:
        client = docker.from_env()
        container = client.containers.get(name)
        logs = container.logs(tail=tail).decode('utf-8')
        return {'logs': logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.get('/system/activity')
def get_activity(limit: int=20, _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('\n                SELECT t.title, a.name as artist, CAST(t.created_at AS CHAR) as timestamp\n                FROM library_tracks t\n                JOIN library_artists a ON t.primary_artist_id = a.id\n                ORDER BY t.created_at DESC\n                LIMIT %s\n            ', (limit,))
            recent_added = cursor.fetchall()
            cursor.execute('\n                SELECT t.title, a.name as artist, CAST(ml.updated_at AS CHAR) as timestamp\n                FROM library_track_ml_labels ml\n                JOIN library_tracks t ON ml.track_id = t.track_uid\n                LEFT JOIN library_artists a ON t.primary_artist_id = a.id\n                WHERE ml.ml_genre IS NOT NULL\n                ORDER BY ml.updated_at DESC\n                LIMIT %s\n            ', (limit,))
            recent_tagged = cursor.fetchall()
            return {'recent_added': recent_added, 'recent_tagged': recent_tagged}
    finally:
        conn.close()

@router.get('/notes')
def get_notes(_auth: dict=Depends(verify_api_key)):
    return {'release_notes': get_release_notes(), 'changelog': get_changelog()}

@router.get('/all-notes')
def get_all_notes(_auth: dict=Depends(verify_api_key)):
    return {'release_notes': get_release_notes(), 'changelog': get_changelog()}

@router.get('/versions')
def get_versions(_auth: dict=Depends(verify_api_key)):
    version = get_version()
    return {'music-manager': version, 'muma-tagger': version, 'muma-scanner': version, 'muma-downloader': version, 'muma-importer': version, 'ultrasonic': 'unknown'}

@router.get('/soundcloud')
def get_soundcloud_accounts(_auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT name, soundcloud_id FROM downloads_soundcloud_accounts')
            return cursor.fetchall()
    finally:
        conn.close()

@router.post('/soundcloud')
def add_soundcloud_account(req: dict[str, Any]=Body(...), _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('\n                INSERT INTO downloads_soundcloud_accounts (name, soundcloud_id)\n                VALUES (%s, %s)\n                ON DUPLICATE KEY UPDATE soundcloud_id = VALUES(soundcloud_id)\n            ', (req.get('name'), req.get('soundcloud_id')))
            conn.commit()
            return {'status': 'ok', 'message': 'SoundCloud account toegevoegd'}
    finally:
        conn.close()

@router.delete('/soundcloud/{name}')
def delete_soundcloud_account(name: str, _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM downloads_soundcloud_accounts WHERE name = %s', (name,))
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()

@router.get('/youtube')
def get_youtube_accounts(_auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT name, channel_id FROM downloads_youtube_accounts')
            return cursor.fetchall()
    finally:
        conn.close()

@router.post('/youtube')
def add_youtube_account(req: dict[str, Any]=Body(...), _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("\n                INSERT INTO downloads_youtube_accounts (name, download_type)\n                VALUES (%s, 'audio')\n                ON DUPLICATE KEY UPDATE name = name\n            ", (req.get('name'),))
            conn.commit()
            return {'status': 'ok', 'message': 'YouTube account toegevoegd'}
    finally:
        conn.close()

@router.delete('/youtube/{name}')
def delete_youtube_account(name: str, _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM downloads_youtube_accounts WHERE name = %s', (name,))
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()

@router.get('/rules/genres')
def get_genre_curation_queue(state: str | None=None, limit: int=200, _auth: dict=Depends(verify_api_key)):
    """Genres by curation state, most frequently seen first.

    Called without a state this returns the whole table; `state=unknown` is the
    curation queue, ordered so the genres that touch most tracks come first.
    """
    if state is not None and state not in VALID_STATES:
        raise HTTPException(status_code=400, detail=f"Invalid state, expected one of {', '.join(VALID_STATES)}")
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            query = "\n                SELECT g.id, g.name, g.state, g.occurrences,\n                       CAST(g.detected_at AS CHAR) AS detected_at,\n                       CAST(g.decided_at AS CHAR) AS decided_at, g.decided_by\n                FROM rules_genres g\n            "
            params: list = []
            if state:
                query += ' WHERE g.state = %s'
                params.append(state)
            query += ' ORDER BY g.occurrences DESC, g.name LIMIT %s'
            params.append(limit)
            cursor.execute(query, params)
            rows = cursor.fetchall()
            # Targets come from a second query rather than a join: a genre can now
            # expand into several, so joining would multiply the rows the page shows.
            ids = [row['id'] for row in rows]
            if ids:
                placeholders = ', '.join(['%s'] * len(ids))
                cursor.execute(f'\n                    SELECT e.genre_id, t.id AS target_id, t.name AS target_name\n                    FROM rules_genre_expansions e\n                    JOIN rules_genres t ON t.id = e.target_id\n                    WHERE e.genre_id IN ({placeholders})\n                    ORDER BY e.genre_id, e.position, t.name\n                ', ids)
                targets: dict = {}
                for target in cursor.fetchall():
                    targets.setdefault(target['genre_id'], []).append({'id': target['target_id'], 'name': target['target_name']})
                for row in rows:
                    row['canonical_targets'] = targets.get(row['id'], [])
            return rows
    finally:
        conn.close()

@router.post('/rules/genres/{genre_id}/decide')
def decide_genre(genre_id: int, decision: GenreDecisionRequest, auth: dict=Depends(verify_api_key)):
    """Move a genre to white or black, optionally rewriting it to other genres.

    A decision made here is recorded as `decided_by`, so the tagger never
    overwrites it later. More than one target is allowed, which is how a
    contraction is expressed: 'Upterror' becomes 'Uptempo Hardcore' + 'Terror'.
    """
    if decision.state not in (WHITE, BLACK):
        raise HTTPException(status_code=400, detail=f'Invalid state, expected {WHITE} or {BLACK}')
    targets = decision.targets()
    if genre_id in targets:
        raise HTTPException(status_code=400, detail='A genre cannot be its own correction')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT id FROM rules_genres WHERE id = %s', (genre_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail='Unknown genre')
            for target in targets:
                cursor.execute('SELECT id FROM rules_genres WHERE id = %s', (target,))
                if not cursor.fetchone():
                    raise HTTPException(status_code=400, detail='Unknown correction target')
            decided_by = (auth.get('user') or {}).get('username') if isinstance(auth.get('user'), dict) else auth.get('type', 'human')
            cursor.execute('\n                UPDATE rules_genres\n                SET state = %s, canonical_id = %s, decided_at = NOW(), decided_by = %s\n                WHERE id = %s\n            ', (decision.state, targets[0] if targets else None, decided_by or 'human', genre_id))
            # Replace rather than merge: the request carries the whole target list,
            # so clearing a correction is just an empty one.
            cursor.execute('DELETE FROM rules_genre_expansions WHERE genre_id = %s', (genre_id,))
            for position, target in enumerate(targets):
                cursor.execute('INSERT INTO rules_genre_expansions (genre_id, target_id, position) VALUES (%s, %s, %s)', (genre_id, target, position))
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()

@router.get('/rules/artist-genres')
def get_artist_genre_rules(_auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('\n                SELECT r.id, r.artist_name, g.name as genre_name, r.genre_id\n                FROM rules_artist_genres r\n                JOIN rules_genres g ON r.genre_id = g.id\n                ORDER BY r.artist_name\n            ')
            return cursor.fetchall()
    finally:
        conn.close()

@router.post('/rules/artist-genres')
def add_artist_genre_rule(rule: ArtistGenreRule, _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('\n                INSERT INTO rules_artist_genres (artist_name, genre_id)\n                VALUES (%s, %s)\n                ON DUPLICATE KEY UPDATE genre_id = VALUES(genre_id)\n            ', (rule.artist_name, rule.genre_id))
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()

@router.delete('/rules/artist-genres/{rule_id}')
def delete_artist_genre_rule(rule_id: int, _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM rules_artist_genres WHERE id = %s', (rule_id,))
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()

@router.get('/rules/label-genres')
def get_label_genre_rules(_auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('\n                SELECT r.id, r.label_name, g.name as genre_name, r.genre_id\n                FROM rules_label_genres r\n                JOIN rules_genres g ON r.genre_id = g.id\n                ORDER BY r.label_name\n            ')
            return cursor.fetchall()
    finally:
        conn.close()

@router.post('/rules/label-genres')
def add_label_genre_rule(rule: LabelGenreRule, _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('\n                INSERT INTO rules_label_genres (label_name, genre_id)\n                VALUES (%s, %s)\n                ON DUPLICATE KEY UPDATE genre_id = VALUES(genre_id)\n            ', (rule.label_name, rule.genre_id))
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()

@router.delete('/rules/label-genres/{rule_id}')
def delete_label_genre_rule(rule_id: int, _auth: dict=Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM rules_label_genres WHERE id = %s', (rule_id,))
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()

@router.get('/scrobble/import/latest')
def get_latest_scrobble_imports_proxy(_auth: dict=Depends(verify_api_key)):
    from services.music_manager.routers.scrobbler import get_latest_imports
    return get_latest_imports()

@router.post('/scrobble/import/listenbrainz')
def trigger_lb_import_proxy(background_tasks: BackgroundTasks, req: dict[str, Any]=Body(...), _auth: dict=Depends(verify_api_key)):
    from services.music_manager.routers.scrobbler import ImportRequest, trigger_lb_import
    return trigger_lb_import(ImportRequest(**req), background_tasks)

@router.post('/tagger/rescan')
def trigger_tagger_rescan(_auth: dict=Depends(verify_api_key)):
    helper = ProcessedFilesHelper()
    helper.mark_for_rescan()
    return {'status': 'ok', 'message': 'All files marked for rescan'}

@router.post('/tagger/rescan/file')
def trigger_file_rescan(filepath: str=Body(..., embed=True), _auth: dict=Depends(verify_api_key)):
    helper = ProcessedFilesHelper()
    helper.mark_for_rescan(filepath)
    return {'status': 'ok', 'message': f"File '{filepath}' marked for rescan"}