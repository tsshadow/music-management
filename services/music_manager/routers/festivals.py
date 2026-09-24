"""Festival curation: the names, spellings and dates the tagger recognises a festival by.

`FestivalHelper` reads three tables -- `rules_festivals` (the canonical name),
`rules_festival_aliases` (the spellings that occur in the wild) and
`rules_festival_editions` (the date per year) -- and until now they were only ever
filled by hand in SQL. This is the page for them, in the shape of the other curation
pages: one festival per row with everything the tagger knows about it, and a "what
does this text resolve to" probe so a new alias can be checked against the real
matcher before it is saved rather than after the next tagger run.

Everything the tagger needs to recognise a festival is here; what a *lineup* holds
(who played) is a text file per edition, and that is `routers/lineups.py`.
"""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.common.Helpers.FestivalHelper import Festival, FestivalHelper
from services.music_manager import curation_rules
from services.music_manager.database import get_db_connection, transaction
from services.music_manager.rbac import require_permission

router = APIRouter(tags=['festivals'])
logger = logging.getLogger('music-manager.festivals')

READ = Depends(require_permission('music.read'))
WRITE = Depends(require_permission('rules.manage'))

FESTIVAL_HELPER = 'festivalHelper'


class EditionRequest(BaseModel):
    year: int
    date: str


class FestivalRequest(BaseModel):
    name: str
    active: bool = True
    aliases: list[str] = []
    editions: list[EditionRequest] = []


class ProbeRequest(BaseModel):
    text: str


def _connect():
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='No database connection')
    return conn


def _key(value: str) -> str:
    """The normalised key the tables are unique on; empty when nothing is left of the text."""
    return FestivalHelper.normalize(value).strip()


def _clean_aliases(name: str, aliases: list[str]) -> list[str]:
    """Trimmed, deduplicated on the normalised key, without the name itself.

    The helper falls back to the name when a festival has no aliases, so storing the
    name as an alias would only make it match twice.
    """
    seen = {_key(name)}
    cleaned = []
    for raw in aliases:
        alias = (raw or '').strip()
        key = _key(alias)
        if not key or key in seen:
            continue
        seen.add(key)
        cleaned.append(alias)
    return cleaned


def _clean_editions(editions: list[EditionRequest]) -> list[tuple[int, date]]:
    cleaned: dict[int, date] = {}
    for edition in editions:
        try:
            when = date.fromisoformat(edition.date)
        except (TypeError, ValueError) as e:
            raise HTTPException(status_code=400, detail=f'Edition {edition.year}: date must be YYYY-MM-DD') from e
        if not 1980 <= edition.year <= 2049:
            raise HTTPException(status_code=400, detail=f'Edition year {edition.year} is out of range')
        cleaned[edition.year] = when
    return sorted(cleaned.items())


def _load_all(cursor) -> list[dict]:
    cursor.execute('SELECT id, name, normalized_name, active FROM rules_festivals ORDER BY name')
    rows = {
        row['id']: {**row, 'active': bool(row['active']), 'aliases': [], 'editions': []} for row in cursor.fetchall()
    }
    cursor.execute('SELECT festival_id, alias FROM rules_festival_aliases ORDER BY alias')
    for alias in cursor.fetchall():
        if alias['festival_id'] in rows:
            rows[alias['festival_id']]['aliases'].append(alias['alias'])
    cursor.execute('SELECT festival_id, year, CAST(date AS CHAR) AS date FROM rules_festival_editions ORDER BY year')
    for edition in cursor.fetchall():
        if edition['festival_id'] in rows:
            rows[edition['festival_id']]['editions'].append({'year': edition['year'], 'date': edition['date']})
    return list(rows.values())


def _write_children(cursor, festival_id: int, aliases: list[str], editions: list[tuple[int, date]]) -> None:
    """Replace rather than merge: the request carries the whole list, so clearing one is an empty one."""
    cursor.execute('DELETE FROM rules_festival_aliases WHERE festival_id = %s', (festival_id,))
    for alias in aliases:
        cursor.execute(
            'INSERT INTO rules_festival_aliases (festival_id, alias, normalized_alias) VALUES (%s, %s, %s)',
            (festival_id, alias, _key(alias)),
        )
    cursor.execute('DELETE FROM rules_festival_editions WHERE festival_id = %s', (festival_id,))
    for year, when in editions:
        cursor.execute(
            'INSERT INTO rules_festival_editions (festival_id, year, date) VALUES (%s, %s, %s)',
            (festival_id, year, when.isoformat()),
        )


@router.get('')
def list_festivals(_auth: dict = READ):
    """Every festival with its aliases and editions, inactive ones included."""
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            return _load_all(cursor)
    finally:
        conn.close()


@router.post('', status_code=201)
def create_festival(request: FestivalRequest, _auth: dict = WRITE):
    name = request.name.strip()
    key = _key(name)
    if not key:
        raise HTTPException(status_code=400, detail='A festival needs a name')
    aliases = _clean_aliases(name, request.aliases)
    editions = _clean_editions(request.editions)
    conn = _connect()
    try:
        with transaction(conn), conn.cursor() as cursor:
            cursor.execute('SELECT id FROM rules_festivals WHERE normalized_name = %s', (key,))
            if cursor.fetchone():
                raise HTTPException(status_code=409, detail=f"'{name}' already exists")
            cursor.execute(
                'INSERT INTO rules_festivals (name, normalized_name, active) VALUES (%s, %s, %s)',
                (name, key, 1 if request.active else 0),
            )
            festival_id = cursor.lastrowid
            _write_children(cursor, festival_id, aliases, editions)
    finally:
        conn.close()
    curation_rules.refresh(FESTIVAL_HELPER)
    return {'status': 'ok', 'id': festival_id}


@router.put('/{festival_id}')
def update_festival(festival_id: int, request: FestivalRequest, _auth: dict = WRITE):
    name = request.name.strip()
    key = _key(name)
    if not key:
        raise HTTPException(status_code=400, detail='A festival needs a name')
    aliases = _clean_aliases(name, request.aliases)
    editions = _clean_editions(request.editions)
    conn = _connect()
    try:
        with transaction(conn), conn.cursor() as cursor:
            cursor.execute('SELECT id FROM rules_festivals WHERE id = %s', (festival_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail='Unknown festival')
            cursor.execute('SELECT id FROM rules_festivals WHERE normalized_name = %s AND id <> %s', (key, festival_id))
            if cursor.fetchone():
                raise HTTPException(status_code=409, detail=f"'{name}' is already another festival")
            cursor.execute(
                'UPDATE rules_festivals SET name = %s, normalized_name = %s, active = %s WHERE id = %s',
                (name, key, 1 if request.active else 0, festival_id),
            )
            _write_children(cursor, festival_id, aliases, editions)
    finally:
        conn.close()
    curation_rules.refresh(FESTIVAL_HELPER)
    return {'status': 'ok'}


@router.delete('/{festival_id}')
def delete_festival(festival_id: int, _auth: dict = WRITE):
    """Remove a festival outright. To stop matching without losing the data, set `active` off."""
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM rules_festivals WHERE id = %s', (festival_id,))
            removed = cursor.rowcount
            conn.commit()
    finally:
        conn.close()
    if not removed:
        raise HTTPException(status_code=404, detail='Unknown festival')
    curation_rules.refresh(FESTIVAL_HELPER)
    return {'status': 'ok'}


@router.post('/probe')
def probe(request: ProbeRequest, _auth: dict = READ):
    """What the tagger would recognise in this text, with the rules as they are saved.

    Built from the tables rather than the process-wide helper, so the answer reflects a
    save made a second ago rather than whatever a tagger process last loaded.
    """
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            rows = _load_all(cursor)
    finally:
        conn.close()
    helper = FestivalHelper(preload=False)
    helper.set_festivals(
        [
            Festival(
                name=row['name'],
                aliases=row['aliases'] or [row['name']],
                editions={edition['year']: date.fromisoformat(edition['date']) for edition in row['editions']},
            )
            for row in rows
            if row['active']
        ]
    )
    return {'matches': helper.get_all(request.text)}
