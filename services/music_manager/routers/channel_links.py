"""Propose, confirm and reject links from a channel to its label or artist.

The matching itself is pure and lives in `services.music_manager.channel_links`; this module
reads its inputs, stores its outcome in `channel_link_proposals`, and writes
`channels.label_id` / `channels.artist_id` when a curator confirms. The review flow mirrors
`/api/label-proposals`: reads need an API key, decisions need `rules.manage`, and a decided
row is never touched by the next search. A channel the search proposed nothing for can be
linked by hand (`PUT /channels/{id}/{kind}`, with `/channels` and `/targets` as the pickers).
Every link change queues the channel's files for the tagger, which is what makes a link change
the tags (ApplyChannelLinkRule). See docs/designs/channel-links/.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from services.common.channels import is_label
from services.common.Helpers.ProcessedFilesHelper import ProcessedFilesHelper
from services.common.Helpers.RescanInvalidator import rescan_invalidator
from services.music_manager import channel_links as links
from services.music_manager.curation_rules import actor_name
from services.music_manager.curation_rules import refresh as refresh_helper
from services.music_manager.database import get_db_connection, transaction
from services.music_manager.rbac import require_permission
from services.music_manager.routers.users import verify_api_key

router = APIRouter(tags=['channel-links'])

require_rules_manage = require_permission('rules.manage')

STATUSES = ('new', 'confirmed', 'rejected', 'stale')

#: The Cache registry key of the tagger's view of the links (ChannelLinkHelper).
CHANNEL_LINK_HELPER = 'channelLinkHelper'

# Complete statements per kind, never assembled from parts: the kind picks a whole literal.
LINKED_QUERY = {
    links.LABEL: 'SELECT label_id AS linked FROM channels WHERE id = %s FOR UPDATE',
    links.ARTIST: 'SELECT artist_id AS linked FROM channels WHERE id = %s FOR UPDATE',
}
TARGET_EXISTS_QUERY = {
    links.LABEL: 'SELECT id FROM library_labels WHERE id = %s',
    links.ARTIST: 'SELECT id FROM library_artists WHERE id = %s',
}
LINK_QUERY = {
    links.LABEL: 'UPDATE channels SET label_id = %s WHERE id = %s',
    links.ARTIST: 'UPDATE channels SET artist_id = %s WHERE id = %s',
}
UNLINK_QUERY = {
    links.LABEL: 'UPDATE channels SET label_id = NULL WHERE id = %s',
    links.ARTIST: 'UPDATE channels SET artist_id = NULL WHERE id = %s',
}

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
    WHERE p.status = %s AND (%s IS NULL OR p.kind = %s)
    ORDER BY track_count DESC, c.name
"""

# Hand-linking (issue #58). Every search orders a name equal to the query first, then one that
# starts with it, so the one the curator is typing towards is on top.
CHANNEL_SEARCH_QUERY = """
    SELECT c.id, c.platform, c.name, c.label_id, l.name AS label_name, c.artist_id, a.name AS artist_name,
           COALESCE(tc.track_count, 0) AS track_count, COALESCE(p.open_proposals, 0) AS open_proposals
    FROM channels c
    LEFT JOIN library_labels l ON l.id = c.label_id
    LEFT JOIN library_artists a ON a.id = c.artist_id
    LEFT JOIN (
        SELECT channel_id, COUNT(*) AS track_count FROM library_track_channels GROUP BY channel_id
    ) tc ON tc.channel_id = c.id
    LEFT JOIN (
        SELECT channel_id, COUNT(*) AS open_proposals FROM channel_link_proposals
        WHERE status = 'new' GROUP BY channel_id
    ) p ON p.channel_id = c.id
    WHERE c.platform IN (%s, %s) AND c.name LIKE %s
    ORDER BY c.name = %s DESC, c.name LIKE %s DESC, track_count DESC, c.name
    LIMIT %s
"""
# Placeholders and platform names are filtered out in Python (`channels.is_label`), so this asks
# for a few more than it returns.
LABEL_SEARCH_QUERY = """
    SELECT id, name FROM library_labels WHERE name LIKE %s
    ORDER BY name = %s DESC, name LIKE %s DESC, name
    LIMIT %s
"""
# The same set the proposals draw from: approved names the library has an id for.
ARTIST_SEARCH_QUERY = """
    SELECT DISTINCT a.id, a.name FROM rules_artists r
    JOIN library_artists a ON a.name = r.name
    WHERE r.state = 'white' AND a.name LIKE %s
    ORDER BY a.name = %s DESC, a.name LIKE %s DESC, a.name
    LIMIT %s
"""
TARGET_QUERY = {
    links.LABEL: 'SELECT id, name, 1 AS approved FROM library_labels WHERE id = %s',
    links.ARTIST: (
        'SELECT a.id, a.name, EXISTS (SELECT 1 FROM rules_artists r '
        "WHERE r.name = a.name AND r.state = 'white') AS approved FROM library_artists a WHERE a.id = %s"
    ),
}
# A hand link is stored like a confirmed proposal. An existing row for exactly this link -- open,
# rejected or withdrawn -- becomes the confirmed one: the curator has now said yes to it.
MANUAL_RECORD_QUERY = """
    INSERT INTO channel_link_proposals
        (channel_id, kind, target_id, target_name, source, status, decided_at, decided_by)
    VALUES (%s, %s, %s, %s, 'manual', 'confirmed', NOW(), %s)
    ON DUPLICATE KEY UPDATE status = 'confirmed', decided_at = NOW(), decided_by = VALUES(decided_by)
"""
STALE_RIVALS_QUERY = (
    "UPDATE channel_link_proposals SET status = 'stale', decided_at = NOW() "
    "WHERE channel_id = %s AND kind = %s AND status = 'new' AND target_id <> %s"
)
SEARCH_LIMIT_MAX = 50


class LinkRequest(BaseModel):
    """The label or artist to link a channel to, by its library id."""

    target_id: int


def _connect():
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='No database connection')
    return conn


def _rows(cursor, query: str, params: tuple = ()) -> list[dict[str, Any]]:
    cursor.execute(query, params)
    return list(cursor.fetchall())


def queue_retag(channel_id: int) -> int:
    """After a link change: let this process's tagger see it and queue the channel's files.

    Runs after the link is committed and never fails the request: a link that saved but did
    not queue a retag is repaired by the daily walk, while a refused save would make the
    curator retry a write that already landed. Returns how many files were queued.
    """
    try:
        refresh_helper(CHANNEL_LINK_HELPER)
        return rescan_invalidator.invalidate_by_channel(channel_id, ProcessedFilesHelper.CHANNEL_LINK)
    except Exception as e:  # pylint: disable=broad-except
        logging.warning('Channel %s linked but queueing its files for retag failed: %s', channel_id, e)
        return 0


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
            return _rows(cursor, LIST_QUERY, (status, kind, kind))
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
    withdrawn: a channel has one label and one artist. A new link queues the channel's files
    for the tagger (`queued`); a repeat queues nothing.
    """
    conn = _connect()
    try:
        with transaction(conn), conn.cursor() as cursor:
            row = _proposal(cursor, proposal_id)
            kind, channel_id, target_id = row['kind'], row['channel_id'], row['target_id']
            outcome = {'channel_id': channel_id, 'kind': kind, 'target_id': target_id}
            if row['status'] == 'confirmed':
                return {'status': 'confirmed', **outcome, 'queued': 0}
            if row['status'] != 'new':
                raise HTTPException(status_code=409, detail=f"The proposal is {row['status']}")
            cursor.execute(LINKED_QUERY[kind], (channel_id,))
            channel = cursor.fetchone()
            linked = channel['linked'] if channel else None
            if linked is not None and linked != target_id:
                raise HTTPException(status_code=409, detail=f'The channel is already linked to another {kind}')
            cursor.execute(TARGET_EXISTS_QUERY[kind], (target_id,))
            if not cursor.fetchone():
                cursor.execute(
                    "UPDATE channel_link_proposals SET status = 'stale', decided_at = NOW() WHERE id = %s",
                    (proposal_id,),
                )
                return {'status': 'stale', **outcome, 'queued': 0}
            cursor.execute(LINK_QUERY[kind], (target_id, channel_id))
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
    finally:
        conn.close()
    return {'status': 'confirmed', **outcome, 'queued': queue_retag(channel_id)}


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


def _require_kind(kind: str) -> None:
    if kind not in links.KINDS:
        raise HTTPException(status_code=400, detail=f"Invalid kind, expected one of {', '.join(links.KINDS)}")


def _linked(cursor, kind: str, channel_id: int) -> int | None:
    """The channel's current link of this kind, locked for the transaction; 404 for no channel."""
    cursor.execute(LINKED_QUERY[kind], (channel_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail='Unknown channel')
    return row['linked']


@router.delete('/channels/{channel_id}/{kind}')
def unlink(channel_id: int, kind: str, auth: dict = Depends(require_rules_manage)):
    """Remove a link, and reject the proposal that led to it so the next search does not offer it again.

    The channel's files are queued for the tagger, which takes the label back off them (the
    publisher is recomputed on every pass). Unlinking a channel with no link queues nothing.
    """
    _require_kind(kind)
    conn = _connect()
    try:
        with transaction(conn), conn.cursor() as cursor:
            was_linked = _linked(cursor, kind, channel_id) is not None
            cursor.execute(UNLINK_QUERY[kind], (channel_id,))
            cursor.execute(
                "UPDATE channel_link_proposals SET status = 'rejected', decided_at = NOW(), decided_by = %s "
                "WHERE channel_id = %s AND kind = %s AND status = 'confirmed'",
                (actor_name(auth), channel_id, kind),
            )
    finally:
        conn.close()
    return {'status': 'unlinked', 'queued': queue_retag(channel_id) if was_linked else 0}


@router.put('/channels/{channel_id}/{kind}')
def link(channel_id: int, kind: str, payload: LinkRequest, auth: dict = Depends(require_rules_manage)):
    """Link a channel to a label or artist by hand, for a channel the search proposed nothing for.

    Stored as a confirmed `manual` row (or turns the existing row for exactly this link into the
    confirmed one), and withdraws the channel's other open proposals of that kind, as confirming
    does. Only an approved artist and a real label may be linked: anything else would approve a
    name, or promote a placeholder, through the back door. A channel already linked to something
    else of that kind has to be unlinked first. Linking the same target again changes nothing.
    """
    _require_kind(kind)
    target_id = payload.target_id
    conn = _connect()
    try:
        with transaction(conn), conn.cursor() as cursor:
            linked = _linked(cursor, kind, channel_id)
            cursor.execute(TARGET_QUERY[kind], (target_id,))
            target = cursor.fetchone()
            if not target:
                raise HTTPException(status_code=404, detail=f'Unknown {kind}')
            outcome = {'channel_id': channel_id, 'kind': kind, 'target_id': target_id, 'target_name': target['name']}
            if linked == target_id:
                return {'status': 'linked', **outcome, 'queued': 0}
            if linked is not None:
                raise HTTPException(
                    status_code=409, detail=f'The channel is already linked to another {kind}; unlink it first'
                )
            if kind == links.ARTIST and not target['approved']:
                raise HTTPException(status_code=409, detail='Only an approved artist can be linked')
            if kind == links.LABEL and not is_label(target['name']):
                raise HTTPException(status_code=409, detail='A placeholder or platform is not a label')
            cursor.execute(LINK_QUERY[kind], (target_id, channel_id))
            cursor.execute(MANUAL_RECORD_QUERY, (channel_id, kind, target_id, target['name'], actor_name(auth)))
            cursor.execute(STALE_RIVALS_QUERY, (channel_id, kind, target_id))
    finally:
        conn.close()
    return {'status': 'linked', **outcome, 'queued': queue_retag(channel_id)}


def _limit(limit: int) -> int:
    return max(1, min(int(limit), SEARCH_LIMIT_MAX))


@router.get('/channels')
def search_channels(q: str = '', limit: int = Query(20), _auth: dict = Depends(verify_api_key)):
    """SoundCloud and YouTube channels whose name contains `q`, with their links, for the hand-link picker."""
    needle = q.strip()
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            rows = _rows(
                cursor,
                CHANNEL_SEARCH_QUERY,
                (
                    *links.PLATFORMS,
                    links.like_pattern(needle),
                    needle,
                    links.like_pattern(needle, anywhere=False),
                    _limit(limit),
                ),
            )
    finally:
        conn.close()
    return [
        {
            'id': row['id'],
            'platform': row['platform'],
            'name': row['name'],
            'track_count': int(row['track_count'] or 0),
            'label': {'id': row['label_id'], 'name': row['label_name']} if row['label_id'] else None,
            'artist': {'id': row['artist_id'], 'name': row['artist_name']} if row['artist_id'] else None,
            'open_proposals': int(row['open_proposals'] or 0),
        }
        for row in rows
    ]


@router.get('/targets')
def search_targets(kind: str, q: str = '', limit: int = Query(20), _auth: dict = Depends(verify_api_key)):
    """Labels, or approved artists, whose name contains `q`: what a channel may be linked to."""
    _require_kind(kind)
    needle = q.strip()
    if not needle:
        return []
    wanted = _limit(limit)
    query = LABEL_SEARCH_QUERY if kind == links.LABEL else ARTIST_SEARCH_QUERY
    # A few extra labels, because placeholders are dropped after the query.
    fetch = wanted + 10 if kind == links.LABEL else wanted
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            rows = _rows(
                cursor,
                query,
                (links.like_pattern(needle), needle, links.like_pattern(needle, anywhere=False), fetch),
            )
    finally:
        conn.close()
    if kind == links.LABEL:
        rows = [row for row in rows if is_label(row['name'])]
    return [{'id': row['id'], 'name': row['name']} for row in rows[:wanted]]
