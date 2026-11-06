"""Festival lineups: who played, as the text files the browse pages read.

A lineup is `<root>/festival-lineups/<Festival>/<year>/<stage>.txt`, one artist per
line, and every directory on that path is itself a lineup holding the union of
everything below it (see docs/festival-lineups.md). `scripts/import_festival_lineup.py`
writes one from the shell; this is the same thing from the Management page, with the same
guard: the page says which lines the library can match *before* anything is written,
because `getSpotifyTracks` compares the whole display name and a spelling the library
stores differently matches nothing at all.

Paths are user input and the root is on the music share, so every path goes through
`_resolve`, which refuses anything that leaves the lineup directory.
"""

import logging
import os
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.common.Helpers.FestivalLineupBuilder import (
    lineup_filename,
    match_lineup,
    parse_lineup,
    render_lineup,
)
from services.music_manager.database import get_db_connection
from services.music_manager.library_paths import MUMA_MUSIC_ROOT
from services.music_manager.rbac import require_permission

router = APIRouter(tags=['lineups'])
logger = logging.getLogger('music-manager.lineups')

READ = Depends(require_permission('music.read'))
WRITE = Depends(require_permission('rules.manage'))

#: Where LMS reads lineups from, seen from this container's mount of the same share.
LINEUP_DIR = os.getenv('MUMA_LINEUP_DIR') or f'{MUMA_MUSIC_ROOT}/metadata/festival-lineups'

#: The field the lineup filter compares against, read straight from LMS when its database
#: is mounted (`MUMA_SERVER_DB_PATH`, the same knob users.py uses). Without it the page
#: matches against muma's own artist names, which is a close but not identical list.
KNOWN_ARTISTS_LMS = 'SELECT DISTINCT artist_display_name FROM track WHERE artist_display_name IS NOT NULL'


class LineupRequest(BaseModel):
    festival: str
    year: int | None = None
    stage: str | None = None
    text: str


class MatchRequest(BaseModel):
    text: str


def _root() -> Path:
    return Path(LINEUP_DIR)


def _resolve(relative: str) -> Path:
    """The file for a lineup id, or a 400 when the id tries to leave the directory."""
    root = _root().resolve()
    candidate = (root / f'{relative}.txt').resolve()
    if root != candidate and root not in candidate.parents:
        raise HTTPException(status_code=400, detail='Not a lineup path')
    return candidate


def list_lineup_ids(root: Path) -> list[str]:
    """Every lineup file under `root`, as the id the browse pages use (path minus `.txt`)."""
    if not root.is_dir():
        return []
    ids = []
    for path in sorted(root.rglob('*.txt')):
        ids.append(path.relative_to(root).as_posix()[: -len('.txt')])
    return ids


def known_artists() -> list[str]:
    """Display names the lineup filter can match, from LMS when reachable, else from muma."""
    lms_db = os.getenv('MUMA_SERVER_DB_PATH') or os.getenv('LMS_DB_PATH')
    if lms_db and os.path.exists(lms_db):
        try:
            connection = sqlite3.connect(f'file:{lms_db}?mode=ro', uri=True)
            try:
                return [row[0] for row in connection.execute(KNOWN_ARTISTS_LMS)]
            finally:
                connection.close()
        except sqlite3.Error as e:
            logger.warning('Could not read LMS display names, falling back to library_artists: %s', e)
    conn = get_db_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT name FROM library_artists')
            return [row['name'] for row in cursor.fetchall()]
    finally:
        conn.close()


@router.get('')
def list_lineups(_auth: dict = READ):
    """Every lineup file, with how many names it holds."""
    root = _root()
    lineups = []
    for lineup_id in list_lineup_ids(root):
        path = root / f'{lineup_id}.txt'
        try:
            count = len(parse_lineup(path.read_text(encoding='utf-8')))
        except OSError:
            count = 0
        parts = lineup_id.split('/')
        lineups.append(
            {
                'id': lineup_id,
                'festival': parts[0],
                'year': parts[1] if len(parts) > 1 else None,
                'stage': parts[2] if len(parts) > 2 else None,
                'artists': count,
            }
        )
    return {'root': str(root), 'lineups': lineups}


@router.get('/{lineup_id:path}')
def read_lineup(lineup_id: str, _auth: dict = READ):
    """One lineup's names, with what the library can match of them."""
    path = _resolve(lineup_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail='No such lineup')
    names = parse_lineup(path.read_text(encoding='utf-8'))
    return {'id': lineup_id, 'names': names, 'match': match_lineup(names, known_artists())}


@router.post('/match')
def match(request: MatchRequest, _auth: dict = READ):
    """What a pasted bill would match, before anything is written."""
    names = parse_lineup(request.text)
    return {'names': names, 'match': match_lineup(names, known_artists())}


@router.put('')
def write_lineup(request: LineupRequest, _auth: dict = WRITE):
    """Write (or overwrite) one lineup file from a pasted bill.

    The names are written in the library's own spelling where they match, so the file
    reads the same as the browse page; unmatched names are written as typed and
    reported, so the caller can see what will not filter.
    """
    festival = request.festival.strip()
    if not festival:
        raise HTTPException(status_code=400, detail='A lineup needs a festival')
    try:
        relative = lineup_filename(festival, request.year, (request.stage or '').strip() or None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    path = _resolve(relative[: -len('.txt')])
    names = parse_lineup(request.text)
    if not names:
        raise HTTPException(status_code=400, detail='No artist names in the text')
    result = match_lineup(names, known_artists())
    # Matched names in the library's spelling, the rest as typed, source order kept.
    matched_lower = {name.lower(): name for name in result['matched']}
    written = [matched_lower.get(name.lower(), name) for name in names]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_lineup(written), encoding='utf-8')
    except OSError as e:
        raise HTTPException(status_code=500, detail=f'Could not write the lineup: {e}') from e
    return {'status': 'ok', 'id': relative[: -len('.txt')], 'names': written, 'match': result}


@router.delete('/{lineup_id:path}')
def delete_lineup(lineup_id: str, _auth: dict = WRITE):
    path = _resolve(lineup_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail='No such lineup')
    path.unlink()
    # Empty edition and festival directories would otherwise linger as lineups of nothing.
    parent = path.parent
    root = _root().resolve()
    while parent != root and parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent
    return {'status': 'ok'}
