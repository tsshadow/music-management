"""Edit pages for one artist, one label or one genre.

The distinction this router exists to hold up: **curation** decides whether a genre
exists at all (that is `/api/rules/genres` in management.py, and the Genre Curation
tab), while **editing** changes what else is true about something already accepted.
A rejected genre therefore has no hierarchy to edit — it is not part of the library —
and `PUT /genres/{name}/parents` says so with a 403 rather than quietly storing a rule
that will never fire.

Everything here is keyed by name rather than id. That is not a compromise: the rule
tables themselves are keyed by name (`rules_artist_genres.artist_name`,
`rules_subgenre_hierarchy.subgenre`), the artist id in the web player's URL comes from
LMS and has nothing to do with `library_artists.id`, and `name` is UNIQUE on both
`library_artists` and `library_labels`.
"""
import logging
import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from services.music_manager import curation_rules as rules
from services.music_manager.database import get_db_connection
from services.music_manager.rbac import require_permission
from services.music_manager.routers.jobs import job_manager
from services.music_manager.routers.tagger import tagger_manager

router = APIRouter(tags=['curation'])
logger = logging.getLogger('music-manager.curation')

READ = Depends(require_permission('music.read'))
WRITE = Depends(require_permission('rules.manage'))

#: Ceiling on how many files one "apply now" may retag. A rule on a prolific artist
#: can match thousands; the job would hold the tagger lock for hours and there is no
#: way to watch it fail halfway. Past this the page says to run a full tagger pass.
MAX_RETAG_FILES = 2000


class MbidRequest(BaseModel):
    mbid: str | None = None


class ExternalIdRequest(BaseModel):
    source: str
    external_id: str
    external_url: str | None = None
    verified: bool = True


class AliasRequest(BaseModel):
    alias: str


class GenreRuleRequest(BaseModel):
    genre_id: int


class ParentLabelRequest(BaseModel):
    parent_label_id: int | None = None


class CatidRequest(BaseModel):
    catid: str


class ParentGenresRequest(BaseModel):
    parents: list[str] = []


class RetagRequest(BaseModel):
    scope: Literal['artist', 'label']
    name: str


def _connect():
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='No database connection')
    return conn


# Delete-then-insert rather than ON DUPLICATE KEY UPDATE, because the two tables do
# not agree on what is unique. `artist_external_ids` is UNIQUE (artist_id, source,
# external_id) in production but PRIMARY KEY (artist_id, source) when built from
# db_init, so an upsert keyed on the pair would update in one table shape and add a
# second row in the other -- and the page would then show the same source twice.
#
# Written out per table rather than as one helper taking a table name. The names
# would be literals either way, but a function that interpolates an identifier into
# SQL is the shape that turns into an injection the first time someone passes it a
# variable, and semgrep is right to refuse it.

def _store_artist_external_id(cursor, artist_id: int, source: str, external_id: str,
                              external_url, verified: bool) -> None:
    """Replace the external id an artist carries for one source."""
    cursor.execute('DELETE FROM artist_external_ids WHERE artist_id = %s AND source = %s',
                   (artist_id, source))
    cursor.execute('''
        INSERT INTO artist_external_ids (artist_id, source, external_id, external_url, verified)
        VALUES (%s, %s, %s, %s, %s)
    ''', (artist_id, source, external_id, external_url, 1 if verified else 0))


def _store_label_external_id(cursor, label_id: int, source: str, external_id: str,
                             external_url, verified: bool) -> None:
    """Replace the external id a label carries for one source."""
    cursor.execute('DELETE FROM label_external_ids WHERE label_id = %s AND source = %s',
                   (label_id, source))
    cursor.execute('''
        INSERT INTO label_external_ids (label_id, source, external_id, external_url, verified)
        VALUES (%s, %s, %s, %s, %s)
    ''', (label_id, source, external_id, external_url, 1 if verified else 0))


# --------------------------------------------------------------------------- artists

@router.get('/artists/{name}')
def get_artist(name: str, _auth: dict = READ):
    """Everything the artist edit page shows, in one call.

    A name the library has never seen is not an error: `rules_artist_genres` is free
    text, so a rule may legitimately be written before the first matching file arrives.
    The page gets a row of nulls and says so.
    """
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            artist = rules.find_artist(cursor, name)
            artist_id = artist['id'] if artist else None
            external_ids: list = []
            aliases: list = []
            if artist_id:
                cursor.execute('''
                    SELECT source, external_id, external_url, verified
                    FROM artist_external_ids WHERE artist_id = %s ORDER BY source
                ''', (artist_id,))
                external_ids = list(cursor.fetchall())
                cursor.execute('SELECT alias FROM library_artist_aliases WHERE artist_id = %s ORDER BY alias',
                               (artist_id,))
                aliases = [row['alias'] for row in cursor.fetchall()]
            return {
                'name': artist['name'] if artist else name,
                'artist_id': artist_id,
                'mbid': artist.get('mbid') if artist else None,
                'sort_name': artist.get('sort_name') if artist else None,
                'in_library': artist is not None,
                'external_ids': external_ids,
                'aliases': aliases,
                'genre_rules': rules.artist_genre_rules(cursor, name),
                'track_count': rules.artist_track_count(cursor, name),
            }
    finally:
        conn.close()


def _require_artist(cursor, name: str) -> dict:
    artist = rules.find_artist(cursor, name)
    if not artist:
        raise HTTPException(status_code=404, detail='Unknown artist')
    return artist


@router.put('/artists/{name}/mbid')
def set_artist_mbid(name: str, request: MbidRequest, _auth: dict = WRITE):
    """Store an MBID on the artist, and mirror it into artist_external_ids.

    An MBID can live in two places, and two places can disagree. Writing both here
    means the pair is only ever set together.
    """
    mbid = rules.parse_mbid(request.mbid)
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            artist = _require_artist(cursor, name)
            cursor.execute('UPDATE library_artists SET mbid = %s WHERE id = %s', (mbid, artist['id']))
            if mbid:
                _store_artist_external_id(cursor, artist['id'], rules.MUSICBRAINZ, mbid,
                                          f'https://musicbrainz.org/artist/{mbid}', True)
            else:
                cursor.execute('DELETE FROM artist_external_ids WHERE artist_id = %s AND source = %s',
                               (artist['id'], rules.MUSICBRAINZ))
            conn.commit()
            return {'status': 'ok', 'mbid': mbid}
    finally:
        conn.close()


@router.put('/artists/{name}/external-ids')
def set_artist_external_id(name: str, request: ExternalIdRequest, _auth: dict = WRITE):
    source = request.source.strip().lower()
    external_id = request.external_id.strip()
    if not source or not external_id:
        raise HTTPException(status_code=400, detail='Both source and external_id are required')
    if source == rules.MUSICBRAINZ:
        rules.parse_mbid(external_id)
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            artist = _require_artist(cursor, name)
            _store_artist_external_id(cursor, artist['id'], source, external_id,
                                      request.external_url, request.verified)
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()


@router.delete('/artists/{name}/external-ids/{source}')
def delete_artist_external_id(name: str, source: str, _auth: dict = WRITE):
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            artist = _require_artist(cursor, name)
            cursor.execute('DELETE FROM artist_external_ids WHERE artist_id = %s AND source = %s',
                           (artist['id'], source.strip().lower()))
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()


@router.post('/artists/{name}/aliases')
def add_artist_alias(name: str, request: AliasRequest, _auth: dict = WRITE):
    alias = request.alias.strip()
    if not alias:
        raise HTTPException(status_code=400, detail='An alias cannot be empty')
    if alias.lower() == name.strip().lower():
        raise HTTPException(status_code=400, detail='An artist is not an alias of itself')
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            artist = _require_artist(cursor, name)
            cursor.execute('''
                INSERT INTO library_artist_aliases (artist_id, alias) VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE alias = VALUES(alias)
            ''', (artist['id'], alias))
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()


@router.delete('/artists/{name}/aliases/{alias}')
def delete_artist_alias(name: str, alias: str, _auth: dict = WRITE):
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            artist = _require_artist(cursor, name)
            cursor.execute('DELETE FROM library_artist_aliases WHERE artist_id = %s AND alias = %s',
                           (artist['id'], alias))
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()


@router.post('/artists/{name}/genres')
def add_artist_genre(name: str, request: GenreRuleRequest, _auth: dict = WRITE):
    """File every track by this artist under a genre, from the next tagger pass on.

    The reply carries how many files the rule matches so the page can offer to retag
    them, and the helper is refreshed so this process stops answering from the map it
    preloaded at startup.
    """
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            rules.require_white_genre(cursor, request.genre_id)
            rules.add_artist_genre_rule(cursor, name, request.genre_id, rules.actor_name(_auth))
            affected = rules.artist_track_count(cursor, name)
            conn.commit()
    finally:
        conn.close()
    rules.refresh(rules.ARTIST_GENRE_HELPER)
    return {'status': 'ok', 'affected_tracks': affected}


@router.delete('/artists/{name}/genres/{genre_id}')
def delete_artist_genre(name: str, genre_id: int, _auth: dict = WRITE):
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            rules.remove_artist_genre_rule(cursor, name, genre_id)
            affected = rules.artist_track_count(cursor, name)
            conn.commit()
    finally:
        conn.close()
    rules.refresh(rules.ARTIST_GENRE_HELPER)
    return {'status': 'ok', 'affected_tracks': affected}


# ---------------------------------------------------------------------------- labels

@router.get('/labels/{name}')
def get_label(name: str, _auth: dict = READ):
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            label = rules.find_label(cursor, name)
            label_id = label['id'] if label else None
            external_ids: list = []
            parent_name = None
            if label_id:
                cursor.execute('''
                    SELECT source, external_id, external_url, verified
                    FROM label_external_ids WHERE label_id = %s ORDER BY source
                ''', (label_id,))
                external_ids = list(cursor.fetchall())
                if label.get('parent_label_id'):
                    cursor.execute('SELECT name FROM library_labels WHERE id = %s', (label['parent_label_id'],))
                    parent = cursor.fetchone()
                    parent_name = parent['name'] if parent else None
            cursor.execute('SELECT catid FROM rules_catid_label WHERE label = %s ORDER BY catid', (name,))
            catids = [row['catid'] for row in cursor.fetchall()]
            return {
                'name': label['name'] if label else name,
                'label_id': label_id,
                'mbid': label.get('mbid') if label else None,
                'parent_label_id': label.get('parent_label_id') if label else None,
                'parent_label_name': parent_name,
                'in_library': label is not None,
                'external_ids': external_ids,
                'catids': catids,
                'genre_rules': rules.label_genre_rules(cursor, name),
                'track_count': rules.label_track_count(cursor, name),
            }
    finally:
        conn.close()


def _require_label(cursor, name: str) -> dict:
    label = rules.find_label(cursor, name)
    if not label:
        raise HTTPException(status_code=404, detail='Unknown label')
    return label


@router.put('/labels/{name}/mbid')
def set_label_mbid(name: str, request: MbidRequest, _auth: dict = WRITE):
    mbid = rules.parse_mbid(request.mbid)
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            label = _require_label(cursor, name)
            cursor.execute('UPDATE library_labels SET mbid = %s WHERE id = %s', (mbid, label['id']))
            if mbid:
                _store_label_external_id(cursor, label['id'], rules.MUSICBRAINZ, mbid,
                                         f'https://musicbrainz.org/label/{mbid}', True)
            else:
                cursor.execute('DELETE FROM label_external_ids WHERE label_id = %s AND source = %s',
                               (label['id'], rules.MUSICBRAINZ))
            conn.commit()
            return {'status': 'ok', 'mbid': mbid}
    finally:
        conn.close()


@router.put('/labels/{name}/parent')
def set_label_parent(name: str, request: ParentLabelRequest, _auth: dict = WRITE):
    """File this label under a parent label, or clear the relation.

    Stored and displayed; nothing reads it yet. The tagger rule that lets a sublabel
    inherit its parent's genres is deliberately later work — the model lands first so
    the relations can be entered.
    """
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            label = _require_label(cursor, name)
            parent_id = request.parent_label_id
            if parent_id is not None:
                if parent_id == label['id']:
                    raise HTTPException(status_code=400, detail='A label cannot be its own parent')
                cursor.execute('SELECT id, parent_label_id FROM library_labels WHERE id = %s', (parent_id,))
                parent = cursor.fetchone()
                if not parent:
                    raise HTTPException(status_code=400, detail='Unknown parent label')
                # One level of cycle is the one a person actually creates by hand:
                # filing A under B while B is already filed under A.
                if parent.get('parent_label_id') == label['id']:
                    raise HTTPException(status_code=400, detail='That label is already filed under this one')
            cursor.execute('UPDATE library_labels SET parent_label_id = %s WHERE id = %s', (parent_id, label['id']))
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()


@router.put('/labels/{name}/external-ids')
def set_label_external_id(name: str, request: ExternalIdRequest, _auth: dict = WRITE):
    source = request.source.strip().lower()
    external_id = request.external_id.strip()
    if not source or not external_id:
        raise HTTPException(status_code=400, detail='Both source and external_id are required')
    if source == rules.MUSICBRAINZ:
        rules.parse_mbid(external_id)
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            label = _require_label(cursor, name)
            _store_label_external_id(cursor, label['id'], source, external_id,
                                     request.external_url, request.verified)
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()


@router.delete('/labels/{name}/external-ids/{source}')
def delete_label_external_id(name: str, source: str, _auth: dict = WRITE):
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            label = _require_label(cursor, name)
            cursor.execute('DELETE FROM label_external_ids WHERE label_id = %s AND source = %s',
                           (label['id'], source.strip().lower()))
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()


@router.post('/labels/{name}/catids')
def add_label_catid(name: str, request: CatidRequest, _auth: dict = WRITE):
    """Map a catalogue-number prefix onto this label.

    Upper-cased on the way in: catalogue numbers are written both ways in the wild and
    the importer matches them case-sensitively.
    """
    catid = request.catid.strip().upper()
    if not catid:
        raise HTTPException(status_code=400, detail='A catalogue prefix cannot be empty')
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            label = _require_label(cursor, name)
            cursor.execute('''
                INSERT INTO rules_catid_label (catid, label) VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE label = VALUES(label)
            ''', (catid, label['name']))
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()


@router.delete('/labels/{name}/catids/{catid}')
def delete_label_catid(name: str, catid: str, _auth: dict = WRITE):
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM rules_catid_label WHERE catid = %s AND label = %s',
                           (catid.strip().upper(), name))
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()


@router.post('/labels/{name}/genres')
def add_label_genre(name: str, request: GenreRuleRequest, _auth: dict = WRITE):
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            rules.require_white_genre(cursor, request.genre_id)
            rules.add_label_genre_rule(cursor, name, request.genre_id, rules.actor_name(_auth))
            affected = rules.label_track_count(cursor, name)
            conn.commit()
    finally:
        conn.close()
    rules.refresh(rules.LABEL_GENRE_HELPER)
    return {'status': 'ok', 'affected_tracks': affected}


@router.delete('/labels/{name}/genres/{genre_id}')
def delete_label_genre(name: str, genre_id: int, _auth: dict = WRITE):
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            rules.remove_label_genre_rule(cursor, name, genre_id)
            affected = rules.label_track_count(cursor, name)
            conn.commit()
    finally:
        conn.close()
    rules.refresh(rules.LABEL_GENRE_HELPER)
    return {'status': 'ok', 'affected_tracks': affected}


# ---------------------------------------------------------------------------- genres

@router.get('/genres/{name}')
def get_genre(name: str, _auth: dict = READ):
    """Where this genre sits in the hierarchy, and whether it may be edited at all.

    A rejected genre still reads back, carrying `editable: false`, so the page can
    explain why there is nothing to change rather than showing a bare error.
    """
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            genre = rules.find_genre_by_name(cursor, name)
            if not genre:
                raise HTTPException(status_code=404, detail='Unknown genre')
            cursor.execute(
                'SELECT genre FROM rules_subgenre_hierarchy WHERE LOWER(subgenre) = LOWER(%s) ORDER BY genre',
                (genre['name'],))
            parents = [row['genre'] for row in cursor.fetchall()]
            cursor.execute(
                'SELECT subgenre FROM rules_subgenre_hierarchy WHERE LOWER(genre) = LOWER(%s) ORDER BY subgenre',
                (genre['name'],))
            children = [row['subgenre'] for row in cursor.fetchall()]
            return {
                'name': genre['name'],
                'genre_id': genre['id'],
                'state': genre['state'],
                'editable': genre['state'] == rules.WHITE,
                'occurrences': genre.get('occurrences'),
                'parents': parents,
                'children': children,
            }
    finally:
        conn.close()


@router.put('/genres/{name}/parents')
def set_genre_parents(name: str, request: ParentGenresRequest, _auth: dict = WRITE):
    """Replace the genres this one rolls up into. 'Industrial Hardcore' -> 'Hardcore'.

    Replaces rather than merges, so clearing the hierarchy is an empty list — the same
    contract the genre decision endpoint uses for its rewrite targets.
    """
    subject_key = rules.normalize_genre(name)
    wanted: list[str] = []
    for parent in request.parents:
        key = rules.normalize_genre(parent)
        if not key:
            continue
        if key == subject_key:
            raise HTTPException(status_code=400, detail='A genre cannot be its own parent')
        if key not in [rules.normalize_genre(w) for w in wanted]:
            wanted.append(parent.strip())

    conn = _connect()
    try:
        with conn.cursor() as cursor:
            genre = rules.find_genre_by_name(cursor, name)
            if not genre:
                raise HTTPException(status_code=404, detail='Unknown genre')
            if genre['state'] != rules.WHITE:
                raise HTTPException(
                    status_code=403,
                    detail='Curation has not accepted this genre, so it has no hierarchy to edit')
            resolved = []
            for parent in wanted:
                parent_row = rules.find_genre_by_name(cursor, parent)
                if not parent_row:
                    raise HTTPException(status_code=400, detail=f"Unknown genre '{parent}'")
                if parent_row['state'] != rules.WHITE:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Genre '{parent_row['name']}' has not been accepted by curation")
                resolved.append(parent_row['name'])
            cursor.execute('DELETE FROM rules_subgenre_hierarchy WHERE LOWER(subgenre) = LOWER(%s)',
                           (genre['name'],))
            for parent_name in resolved:
                cursor.execute('INSERT INTO rules_subgenre_hierarchy (subgenre, genre) VALUES (%s, %s)',
                               (genre['name'], parent_name))
            conn.commit()
    finally:
        conn.close()
    rules.refresh(rules.SUBGENRE_HELPER)
    return {'status': 'ok', 'parents': resolved}


# ----------------------------------------------------------------------------- apply

def _run_retag(job_id: str, paths: list[str]) -> None:
    """Retag the files a rule matches, one at a time.

    Goes through `tagger_manager` rather than calling TagSingleFile directly so this
    takes the same lock a full tagging run holds: the two must not interleave over the
    same file. One unreadable file must not abandon the rest of the batch -- a single
    permission error on a CIFS share is common and is not a reason to leave the other
    hundred files on their old tags.
    """
    state = job_manager.jobs.setdefault(job_id, {})
    state.update({'status': 'running', 'progress': 0, 'total': len(paths), 'current': None, 'failed': 0})
    for index, path in enumerate(paths, start=1):
        state['current'] = path
        try:
            tagger_manager.tag_single(path)
        except Exception as e:  # pylint: disable=broad-except
            state['failed'] = state.get('failed', 0) + 1
            logger.warning('Retag of %s failed: %s', path, e)
        state['progress'] = index
    state['status'] = 'finished'
    state['current'] = None
    job_manager.results[job_id] = dict(state)
    if job_id not in job_manager.history:
        job_manager.history.appendleft(job_id)


@router.post('/retag', status_code=202)
def retag(request: RetagRequest, background: BackgroundTasks, _auth: dict = WRITE):
    """Apply the rules for one artist or label to the files they already match.

    A rule only changes a file the next time the tagger reaches it, which for a
    library this size can be a long wait. This is the shortcut, deliberately a
    separate action from saving the rule: saving is cheap and reversible, retagging
    hundreds of files is neither.
    """
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            if request.scope == 'artist':
                paths = rules.artist_track_paths(cursor, request.name, MAX_RETAG_FILES + 1)
            else:
                paths = rules.label_track_paths(cursor, request.name, MAX_RETAG_FILES + 1)
    finally:
        conn.close()

    if len(paths) > MAX_RETAG_FILES:
        raise HTTPException(
            status_code=400,
            detail=f'That matches more than {MAX_RETAG_FILES} files; start a full tagger run instead')

    job_id = f'retag-{uuid.uuid4()}'
    job_manager.jobs[job_id] = {'status': 'queued', 'progress': 0, 'total': len(paths),
                                'current': None, 'failed': 0}
    background.add_task(_run_retag, job_id, paths)
    return {'status': 'queued', 'job_id': job_id, 'files': len(paths)}
