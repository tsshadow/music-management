"""Linking listens to tracks, and retrying the ones that did not link.

The rules live in scrobble_matching.py; this module owns the SQL. Both scrobble
entry points in routers/scrobbler.py call find_track() here, so the live path and
the import path cannot drift apart again -- they used to hold two copies of the
same query.

Design: docs/superpowers/specs/2026-08-21-scrobble-rematching-design.md
"""
from __future__ import annotations

import os
import sys
import time

from services.music_manager.database import get_db_connection
from services.music_manager.scrobble_matching import (
    MatchTier,
    base_title,
    enabled_tiers,
    normalize,
    similarity,
)

BATCH_SIZE = int(os.getenv('SCROBBLE_REMATCH_BATCH', '500'))
FUZZY_THRESHOLD = int(os.getenv('SCROBBLE_FUZZY_THRESHOLD', '90'))
INTERVAL_SECONDS = int(os.getenv('SCROBBLE_REMATCH_INTERVAL', '3600'))

# How long before a row that missed is tried again, by attempt count. A row that
# will never match costs one lookup a week rather than one a cycle.
RETRY_HOURS = [1, 24, 168]

_BACKFILL_ARTISTS = (
    'SELECT id, name FROM library_artists WHERE normalized_name IS NULL LIMIT %s'
)
_BACKFILL_TRACKS = (
    'SELECT id, title FROM library_tracks WHERE normalized_title IS NULL LIMIT %s'
)


def tiers() -> list[MatchTier]:
    return enabled_tiers(os.getenv('SCROBBLE_MATCH_TIERS'))


def backfill_normalized(cursor, limit: int = BATCH_SIZE) -> int:
    """Fill normalized columns wherever they are missing.

    Deliberately not left to the writers. Tracks are inserted from four places
    and artists from one more, and a fifth will be added by someone who has not
    read the design -- a row with a NULL key would then be permanently
    unmatchable, which is the silent failure this whole change is removing.
    """
    filled = 0

    cursor.execute(_BACKFILL_ARTISTS, (limit,))
    for row in cursor.fetchall():
        cursor.execute(
            'UPDATE library_artists SET normalized_name = %s WHERE id = %s',
            (normalize(row['name'])[:191], row['id']),
        )
        filled += 1

    cursor.execute(_BACKFILL_TRACKS, (limit,))
    for row in cursor.fetchall():
        title = row['title']
        cursor.execute(
            'UPDATE library_tracks SET normalized_title = %s, normalized_base_title = %s '
            'WHERE id = %s',
            (normalize(title)[:191], normalize(base_title(title))[:191], row['id']),
        )
        filled += 1

    return filled


def find_track(cursor, artist: str, title: str) -> tuple[int, MatchTier, int | None] | None:
    """The track this listen belongs to, which tier found it, and how sure.

    Tiers are tried in ladder order and the first hit wins, so a cheap certain
    answer is never overtaken by an expensive uncertain one.
    """
    for tier in tiers():
        found = _try_tier(cursor, tier, artist, title)
        if found:
            return found
    return None


def _try_tier(cursor, tier, artist, title):
    if tier is MatchTier.EXACT:
        cursor.execute(
            'SELECT t.id FROM library_tracks t '
            'JOIN library_artists a ON t.primary_artist_id = a.id '
            'WHERE a.name = %s AND t.title = %s LIMIT 1',
            (artist, title),
        )
        row = cursor.fetchone()
        return (row['id'], tier, None) if row else None

    if tier is MatchTier.NORMALIZED:
        cursor.execute(
            'SELECT t.id FROM library_tracks t '
            'JOIN library_artists a ON t.primary_artist_id = a.id '
            'WHERE a.normalized_name = %s AND t.normalized_title = %s LIMIT 1',
            (normalize(artist)[:191], normalize(title)[:191]),
        )
        row = cursor.fetchone()
        return (row['id'], tier, None) if row else None

    if tier is MatchTier.BASE_TITLE:
        cursor.execute(
            'SELECT t.id FROM library_tracks t '
            'JOIN library_artists a ON t.primary_artist_id = a.id '
            'WHERE a.normalized_name = %s AND t.normalized_base_title = %s LIMIT 1',
            (normalize(artist)[:191], normalize(base_title(title))[:191]),
        )
        row = cursor.fetchone()
        return (row['id'], tier, None) if row else None

    if tier is MatchTier.FUZZY:
        return _try_fuzzy(cursor, artist, title)

    return None


def _try_fuzzy(cursor, artist, title):
    """Fuzzy, but only inside a candidate set an exact key already narrowed.

    35.761 listens against 302.561 tracks is ten billion comparisons; nothing can
    do that. Narrowing on the normalized artist first -- or, when the artist is
    unknown, on the normalized base title -- leaves a handful of rows per listen.
    A listen that finds no candidate by either key is simply not fuzzy-matched,
    which is the right outcome for the large part of the import that is music
    this library does not have: it fails on an index lookup.
    """
    normalized_artist = normalize(artist)[:191]
    normalized_title = normalize(title)[:191]

    cursor.execute(
        'SELECT t.id, t.normalized_title FROM library_tracks t '
        'JOIN library_artists a ON t.primary_artist_id = a.id '
        'WHERE a.normalized_name = %s LIMIT 200',
        (normalized_artist,),
    )
    candidates = [(row['id'], row['normalized_title'] or '') for row in cursor.fetchall()]

    if not candidates:
        cursor.execute(
            'SELECT t.id, a.normalized_name FROM library_tracks t '
            'JOIN library_artists a ON t.primary_artist_id = a.id '
            'WHERE t.normalized_base_title = %s LIMIT 200',
            (normalize(base_title(title))[:191],),
        )
        candidates = [(row['id'], row['normalized_name'] or '') for row in cursor.fetchall()]
        subject = normalized_artist
    else:
        subject = normalized_title

    best_id, best_score = None, 0
    for candidate_id, candidate_text in candidates:
        score = similarity(subject, candidate_text)
        if score > best_score:
            best_id, best_score = candidate_id, score

    if best_id is not None and best_score >= FUZZY_THRESHOLD:
        return (best_id, MatchTier.FUZZY, best_score)
    return None


def record_match(cursor, track_id, listened_at, username, source, tier, score, mbid=None,
                 played_secs=None) -> None:
    """Write a listen that resolved to a library track.

    `played_secs` is how long the track was actually played. It stays NULL for every listen whose
    client never reported it -- imported history, and any client older than the change that added
    it -- so a reader has to treat "no playing time" as a real state rather than as zero.
    """
    cursor.execute(
        'INSERT INTO scrobble_listens '
        '(track_id, listened_at, username, source, mbid_track, match_method, match_score, played_secs) '
        'VALUES (%s, %s, %s, %s, %s, %s, %s, %s) '
        'ON DUPLICATE KEY UPDATE match_method = VALUES(match_method), '
        'match_score = VALUES(match_score), '
        'played_secs = COALESCE(VALUES(played_secs), played_secs)',
        (track_id, listened_at, username, source, mbid, tier.value, score, played_secs),
    )


def _retry_cutoff_sql() -> str:
    """A row is due when it has never been tried, or its window has passed."""
    branches = ' '.join(
        f'WHEN attempts <= {index + 1} THEN {hours}'
        for index, hours in enumerate(RETRY_HOURS)
    )
    return (
        'last_attempt_at IS NULL OR last_attempt_at < DATE_SUB(NOW(), INTERVAL '
        f'(CASE {branches} ELSE {RETRY_HOURS[-1]} END) HOUR)'
    )


def rematch_once(conn, limit: int = BATCH_SIZE) -> dict:
    """One pass: fill missing keys, then retry the listens that are due."""
    stats = {'backfilled': 0, 'tried': 0, 'linked': 0}

    with conn.cursor() as cursor:
        stats['backfilled'] = backfill_normalized(cursor, limit)
    conn.commit()

    with conn.cursor() as cursor:
        cursor.execute(
            'SELECT id, artist_name, track_title, listened_at, username, source, mbid_track, '
            'played_secs '
            'FROM scrobble_unmatched_listens '
            f'WHERE {_retry_cutoff_sql()} '
            'ORDER BY listened_at ASC LIMIT %s',
            (limit,),
        )
        due = cursor.fetchall()

    for row in due:
        stats['tried'] += 1
        with conn.cursor() as cursor:
            found = find_track(cursor, row['artist_name'], row['track_title'])
            if found:
                track_id, tier, score = found
                record_match(
                    cursor, track_id, row['listened_at'], row['username'],
                    row['source'], tier, score, row.get('mbid_track'),
                    row.get('played_secs'),
                )
                # Deleting is what makes the table an honest work queue: its size
                # is what is still missing, not a log of everything that arrived.
                cursor.execute(
                    'DELETE FROM scrobble_unmatched_listens WHERE id = %s', (row['id'],)
                )
                stats['linked'] += 1
            else:
                cursor.execute(
                    'UPDATE scrobble_unmatched_listens '
                    'SET attempts = attempts + 1, last_attempt_at = NOW() WHERE id = %s',
                    (row['id'],),
                )
        conn.commit()

    return stats


def run_scrobble_rematch() -> None:
    while True:
        try:
            conn = get_db_connection()
            if conn:
                try:
                    stats = rematch_once(conn)
                    if stats['linked']:
                        print(
                            f"scrobble-rematch: linked {stats['linked']} of "
                            f"{stats['tried']} retried"
                        )
                finally:
                    conn.close()
        except Exception as exc:
            print(f'scrobble-rematch: pass failed: {exc}', file=sys.stderr)
        time.sleep(INTERVAL_SECONDS)
