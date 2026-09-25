"""Propose, confirm and reject links from a channel to its label or artist.

The matching itself is pure and lives in `services.music_manager.channel_links`; this module
reads its inputs, stores its outcome in `channel_link_proposals`, and writes
`channels.label_id` / `channels.artist_id` when a curator confirms. The review flow mirrors
`/api/label-proposals`: reads need an API key, decisions need `rules.manage`, and a decided
row is never touched by the next search. See docs/designs/channel-links/.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from services.music_manager import channel_links as links
from services.music_manager.curation_rules import actor_name
from services.music_manager.database import get_db_connection, transaction
from services.music_manager.rbac import require_permission
from services.music_manager.routers.users import verify_api_key

router = APIRouter(tags=['channel-links'])

require_rules_manage = require_permission('rules.manage')

STATUSES = ('new', 'confirmed', 'rejected', 'stale')

# Which channels column and which library table each kind of link points at.
LINK_COLUMN = {links.LABEL: 'label_id', links.ARTIST: 'artist_id'}
TARGET_TABLE = {links.LABEL: 'library_labels', links.ARTIST: 'library_artists'}

CHANNELS_QUERY = 'SELECT id, platform, name, label_id, artist_id FROM channels WHERE platform IN (%s, %s)'
LABELS_QUERY = 'SELECT id, name FROM library_labels'
# The link needs a library id, so an approved name the library has never seen is no candidate.
APPROVED_ARTISTS_QUERY = """
    SELECT a.id, a.name FROM rules_artists r
    JOIN library_artists a ON a.name = r.name
    WHERE r.state = 'white'
"""
ALIASES_QUERY = """
    SELECT a.id, a.name, al.alias FROM library_artist_aliases al
    JOIN library_artists a ON a.id = al.artist_id
"""
# A black spelling with a white canonical is the curator saying "this spelling is that artist".
REDIRECTS_QUERY = """
    SELECT a.id, a.name, r.name AS spelling FROM rules_artists r
    JOIN rules_artists w ON w.name = r.canonical_name AND w.state = 'white'
    JOIN library_artists a ON a.name = w.name
    WHERE r.state = 'black' AND r.canonical_name IS NOT NULL
"""
# Only an open row takes the new name and source: a decided one keeps what was decided.
RECORD_QUERY = """
    INSERT INTO channel_link_proposals (channel_id, kind, target_id, target_name, source)
    VALUES (%s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        target_name = IF(status = 'new', VALUES(target_name), target_name),
        source = IF(status = 'new', VALUES(source), source)
"""
OPEN_QUERY = "SELECT id, channel_id, kind, target_id FROM channel_link_proposals WHERE status = 'new'"
LIST_QUERY = """
    SELECT p.id, p.channel_id, c.platform, c.name AS channel_name, p.kind, p.target_id, p.target_name,
           p.source, p.status, COALESCE(tc.track_count, 0) AS track_count, p.created_at, p.decided_at
    FROM channel_link_proposals p
    JOIN channels c ON c.id = p.channel_id
    LEFT JOIN (
        SELECT channel_id, COUNT(*) AS track_count FROM library_track_channels GROUP BY channel_id
    ) tc ON tc.channel_id = p.channel_id
    WHERE p.status = %s{kind_filter}
    ORDER BY track_count DESC, c.name
"""


def _connect():
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='No database connection')
    return conn


def _rows(cursor, query: str, params: tuple = ()) -> list[dict[str, Any]]:
    cursor.execute(query, params)
    return list(cursor.fetchall())


def load_indexes(cursor) -> tuple[list[links.Channel], list[links.CandidateIndex]]:
    """Every considered channel and the candidate indexes for both kinds, in five statements."""
    channels = [
        links.Channel(r['id'], r['platform'], r['name'], r['label_id'], r['artist_id'])
        for r in _rows(cursor, CHANNELS_QUERY, links.PLATFORMS)
    ]
    labels = links.label_index((r['id'], r['name']) for r in _rows(cursor, LABELS_QUERY))
    artists = links.artist_index(
        [(r['id'], r['name']) for r in _rows(cursor, APPROVED_ARTISTS_QUERY)],
        [(r['id'], r['name'], r['alias']) for r in _rows(cursor, ALIASES_QUERY)],
        [(r['id'], r['name'], r['spelling']) for r in _rows(cursor, REDIRECTS_QUERY)],
    )
    return channels, [labels, artists]


def refresh_proposals(cursor) -> dict[str, int]:
    """Run the search and store its outcome. Returns the counts the Koppelingen tab reports.

    New triples are inserted; open rows the search no longer produces are withdrawn
    (`stale`). Decided rows are left alone either way, which is what keeps a rejection a
    rejection. Running it twice in a row changes nothing the second time.
    """
    channels, indexes = load_indexes(cursor)
    run = links.propose_links(channels, indexes)
    wanted = {proposal.key for proposal in run.proposals}
    created = 0
    for proposal in run.proposals:
        cursor.execute(
            RECORD_QUERY,
            (proposal.channel_id, proposal.kind, proposal.target_id, proposal.target_name, proposal.source),
        )
        # 1 for an inserted row; 0 (unchanged) or 2 (updated) for one that was already there.
        if cursor.rowcount == 1:
            created += 1
    withdrawn = 0
    for row in _rows(cursor, OPEN_QUERY):
        if (row['channel_id'], row['kind'], row['target_id']) not in wanted:
            cursor.execute(
                "UPDATE channel_link_proposals SET status = 'stale', decided_at = NOW() "
                "WHERE id = %s AND status = 'new'",
                (row['id'],),
            )
            withdrawn += 1
    return {'created': created, 'open': len(wanted), 'withdrawn': withdrawn, 'ambiguous': run.ambiguous}


@router.get('/proposals')
def list_proposals(status: str = 'new', kind: str | None = None, _auth: dict = Depends(verify_api_key)):
    """Proposals of one status, busiest channel first, so the decisions that matter most come first."""
    if status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status, expected one of {', '.join(STATUSES)}")
    if kind is not None and kind not in links.KINDS:
        raise HTTPException(status_code=400, detail=f"Invalid kind, expected one of {', '.join(links.KINDS)}")
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            params: tuple = (status,)
            kind_filter = ''
            if kind:
                kind_filter = ' AND p.kind = %s'
                params = (status, kind)
            return _rows(cursor, LIST_QUERY.format(kind_filter=kind_filter), params)
    finally:
        conn.close()


@router.post('/proposals/refresh')
def refresh(_auth: dict = Depends(require_rules_manage)):
    """Compare every SoundCloud and YouTube channel again and file what holds. See `refresh_proposals`."""
    conn = _connect()
    try:
        with transaction(conn), conn.cursor() as cursor:
            return refresh_proposals(cursor)
    finally:
        conn.close()


def _proposal(cursor, proposal_id: int) -> dict[str, Any]:
    cursor.execute(
        'SELECT id, channel_id, kind, target_id, status FROM channel_link_proposals WHERE id = %s FOR UPDATE',
        (proposal_id,),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail='Unknown proposal')
    return row


@router.post('/proposals/{proposal_id}/confirm')
def confirm(proposal_id: int, auth: dict = Depends(require_rules_manage)):
    """Link the channel to the proposed label or artist.

    Idempotent: a confirmed proposal confirms again without writing. A target that was
    deleted since turns the proposal stale instead -- committed, not an error, because the
    row is simply out of date. The channel's other open proposals of the same kind are
    withdrawn: a channel has one label and one artist.
    """
    conn = _connect()
    try:
        with transaction(conn), conn.cursor() as cursor:
            row = _proposal(cursor, proposal_id)
            kind, channel_id, target_id = row['kind'], row['channel_id'], row['target_id']
            outcome = {'channel_id': channel_id, 'kind': kind, 'target_id': target_id}
            if row['status'] == 'confirmed':
                return {'status': 'confirmed', **outcome}
            if row['status'] != 'new':
                raise HTTPException(status_code=409, detail=f"The proposal is {row['status']}")
            column = LINK_COLUMN[kind]
            cursor.execute(f'SELECT {column} AS linked FROM channels WHERE id = %s FOR UPDATE', (channel_id,))
            channel = cursor.fetchone()
            linked = channel['linked'] if channel else None
            if linked is not None and linked != target_id:
                raise HTTPException(status_code=409, detail=f'The channel is already linked to another {kind}')
            cursor.execute(f'SELECT id FROM {TARGET_TABLE[kind]} WHERE id = %s', (target_id,))
            if not cursor.fetchone():
                cursor.execute(
                    "UPDATE channel_link_proposals SET status = 'stale', decided_at = NOW() WHERE id = %s",
                    (proposal_id,),
                )
                return {'status': 'stale', **outcome}
            cursor.execute(f'UPDATE channels SET {column} = %s WHERE id = %s', (target_id, channel_id))
            cursor.execute(
                "UPDATE channel_link_proposals SET status = 'confirmed', decided_at = NOW(), decided_by = %s "
                'WHERE id = %s',
                (actor_name(auth), proposal_id),
            )
            cursor.execute(
                "UPDATE channel_link_proposals SET status = 'stale', decided_at = NOW() "
                "WHERE channel_id = %s AND kind = %s AND status = 'new' AND id <> %s",
                (channel_id, kind, proposal_id),
            )
            return {'status': 'confirmed', **outcome}
    finally:
        conn.close()


@router.post('/proposals/{proposal_id}/reject')
def reject(proposal_id: int, auth: dict = Depends(require_rules_manage)):
    """A rejected proposal never returns, however often the search runs. Idempotent."""
    conn = _connect()
    try:
        with transaction(conn), conn.cursor() as cursor:
            row = _proposal(cursor, proposal_id)
            if row['status'] == 'rejected':
                return {'status': 'rejected'}
            if row['status'] == 'confirmed':
                raise HTTPException(status_code=409, detail='The proposal is confirmed; unlink the channel instead')
            cursor.execute(
                "UPDATE channel_link_proposals SET status = 'rejected', decided_at = NOW(), decided_by = %s "
                'WHERE id = %s',
                (actor_name(auth), proposal_id),
            )
            return {'status': 'rejected'}
    finally:
        conn.close()


@router.delete('/channels/{channel_id}/{kind}')
def unlink(channel_id: int, kind: str, auth: dict = Depends(require_rules_manage)):
    """Remove a link, and reject the proposal that led to it so the next search does not offer it again."""
    if kind not in links.KINDS:
        raise HTTPException(status_code=400, detail=f"Invalid kind, expected one of {', '.join(links.KINDS)}")
    conn = _connect()
    try:
        with transaction(conn), conn.cursor() as cursor:
            cursor.execute('SELECT id FROM channels WHERE id = %s', (channel_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail='Unknown channel')
            cursor.execute(f'UPDATE channels SET {LINK_COLUMN[kind]} = NULL WHERE id = %s', (channel_id,))
            cursor.execute(
                "UPDATE channel_link_proposals SET status = 'rejected', decided_at = NOW(), decided_by = %s "
                "WHERE channel_id = %s AND kind = %s AND status = 'confirmed'",
                (actor_name(auth), channel_id, kind),
            )
            return {'status': 'unlinked'}
    finally:
        conn.close()
