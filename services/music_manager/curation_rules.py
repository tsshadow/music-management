"""Shared storage logic behind the artist, label and genre edit pages.

The rule tables predate those pages: `/api/rules/artist-genres` and
`/api/rules/label-genres` in management.py already write them, and the Tagger tab in
the frontend already lists them. Putting the writes here rather than in the new router
means both paths get the same three things — validation against the curated genre list,
a record of who wrote the rule, and the cache refresh without which the running tagger
never sees it.

Everything in here takes an open cursor and leaves the transaction to the caller.
"""

import re
import unicodedata

from fastapi import HTTPException

from services.common.Helpers import Cache
from services.common.Helpers.GenreRulesHelper import WHITE

#: Registry keys in `Cache.databaseHelpers`, one per rule table these pages write.
ARTIST_GENRE_HELPER = 'artistGenreHelper'
LABEL_GENRE_HELPER = 'labelGenreHelper'
SUBGENRE_HELPER = 'subgenreHelper'
PODCAST_HELPER = 'podcastHelper'
# The tagger's ResolveGenreRule reads its decisions from this one.
GENRE_RULES_HELPER = 'genre_rules'
ARTIST_REDIRECT_HELPER = 'rules_ignored_artists'

MBID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)

#: The source name an MBID is filed under in the *_external_ids tables.
MUSICBRAINZ = 'musicbrainz'


def normalize_genre(name: str) -> str:
    """Casing-, accent- and punctuation-insensitive genre key.

    Deliberately the same rule as `GenreRulesHelper.normalize` and as
    `normalizeGenre` in the frontend, so all three agree on when two spellings are
    one genre.
    """
    decomposed = unicodedata.normalize('NFKD', name or '')
    without_accents = ''.join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub('[^a-z0-9]+', ' ', without_accents.lower()).strip()


def actor_name(auth: dict) -> str:
    """Who to record as the author of a rule.

    Mirrors what management.py's genre decision endpoint stores in `decided_by`: a
    username when a person is behind the request, the auth type otherwise.
    """
    user = (auth or {}).get('user')
    if isinstance(user, dict) and user.get('username'):
        return str(user['username'])[:64]
    return str((auth or {}).get('type') or 'human')[:64]


def parse_mbid(value: str | None) -> str | None:
    """Validate a MusicBrainz id, or None to clear it."""
    if value is None:
        return None
    candidate = value.strip().lower()
    if not candidate:
        return None
    if not MBID_PATTERN.match(candidate):
        raise HTTPException(status_code=400, detail='Not a MusicBrainz id (expected 8-4-4-4-12 hex)')
    return candidate


def require_white_genre(cursor, genre_id: int) -> dict:
    """The genre a rule may point at: one curation has accepted.

    400 rather than 404 for a missing row as well: from the page's point of view both
    are the same mistake, picking a target that is not available to pick.
    """
    cursor.execute('SELECT id, name, state FROM rules_genres WHERE id = %s', (genre_id,))
    genre = cursor.fetchone()
    if not genre:
        raise HTTPException(status_code=400, detail='Unknown genre')
    if genre['state'] != WHITE:
        raise HTTPException(status_code=400, detail=f"Genre '{genre['name']}' has not been accepted by curation")
    return genre


def find_genre_by_name(cursor, name: str) -> dict | None:
    cursor.execute(
        'SELECT id, name, state, occurrences FROM rules_genres WHERE normalized_name = %s', (normalize_genre(name),)
    )
    return cursor.fetchone()


def find_artist(cursor, name: str) -> dict | None:
    cursor.execute('SELECT id, name, sort_name, mbid FROM library_artists WHERE name = %s', (name,))
    return cursor.fetchone()


def find_label(cursor, name: str) -> dict | None:
    cursor.execute('SELECT id, name, mbid, parent_label_id FROM library_labels WHERE name = %s', (name,))
    return cursor.fetchone()


def artist_track_count(cursor, name: str) -> int:
    """How many files a rule on this artist would retag.

    Counts through library_media_files rather than library_tracks: a track with no
    file on disk cannot be retagged, so counting it would overstate the work.
    """
    cursor.execute(
        '''
        SELECT COUNT(DISTINCT mf.track_id) AS affected
        FROM library_track_artists ta
        JOIN library_artists a ON a.id = ta.artist_id
        JOIN library_media_files mf ON mf.track_id = ta.track_id
        WHERE a.name = %s
    ''',
        (name,),
    )
    row = cursor.fetchone()
    return int((row or {}).get('affected') or 0)


def label_track_count(cursor, name: str) -> int:
    cursor.execute(
        '''
        SELECT COUNT(DISTINCT mf.track_id) AS affected
        FROM library_track_labels tl
        JOIN library_labels l ON l.id = tl.label_id
        JOIN library_media_files mf ON mf.track_id = tl.track_id
        WHERE l.name = %s
    ''',
        (name,),
    )
    row = cursor.fetchone()
    return int((row or {}).get('affected') or 0)


def artist_track_paths(cursor, name: str, limit: int) -> list[str]:
    cursor.execute(
        '''
        SELECT DISTINCT mf.file_path
        FROM library_track_artists ta
        JOIN library_artists a ON a.id = ta.artist_id
        JOIN library_media_files mf ON mf.track_id = ta.track_id
        WHERE a.name = %s
        LIMIT %s
    ''',
        (name, limit),
    )
    return [row['file_path'] for row in cursor.fetchall() if row.get('file_path')]


def label_track_paths(cursor, name: str, limit: int) -> list[str]:
    cursor.execute(
        '''
        SELECT DISTINCT mf.file_path
        FROM library_track_labels tl
        JOIN library_labels l ON l.id = tl.label_id
        JOIN library_media_files mf ON mf.track_id = tl.track_id
        WHERE l.name = %s
        LIMIT %s
    ''',
        (name, limit),
    )
    return [row['file_path'] for row in cursor.fetchall() if row.get('file_path')]


def artist_genre_rules(cursor, name: str) -> list[dict]:
    cursor.execute(
        '''
        SELECT r.genre_id, g.name, r.created_by
        FROM rules_artist_genres r
        JOIN rules_genres g ON g.id = r.genre_id
        WHERE r.artist_name = %s
        ORDER BY g.name
    ''',
        (name,),
    )
    return list(cursor.fetchall())


def label_genre_rules(cursor, name: str) -> list[dict]:
    cursor.execute(
        '''
        SELECT r.genre_id, g.name, r.created_by
        FROM rules_label_genres r
        JOIN rules_genres g ON g.id = r.genre_id
        WHERE r.label_name = %s
        ORDER BY g.name
    ''',
        (name,),
    )
    return list(cursor.fetchall())


def add_artist_genre_rule(cursor, artist_name: str, genre_id: int, actor: str) -> None:
    cursor.execute(
        '''
        INSERT INTO rules_artist_genres (artist_name, genre_id, created_by)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE created_by = VALUES(created_by)
    ''',
        (artist_name, genre_id, actor),
    )


def remove_artist_genre_rule(cursor, artist_name: str, genre_id: int) -> None:
    cursor.execute('DELETE FROM rules_artist_genres WHERE artist_name = %s AND genre_id = %s', (artist_name, genre_id))


def add_label_genre_rule(cursor, label_name: str, genre_id: int, actor: str) -> None:
    cursor.execute(
        '''
        INSERT INTO rules_label_genres (label_name, genre_id, created_by)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE created_by = VALUES(created_by)
    ''',
        (label_name, genre_id, actor),
    )


def remove_label_genre_rule(cursor, label_name: str, genre_id: int) -> None:
    cursor.execute('DELETE FROM rules_label_genres WHERE label_name = %s AND genre_id = %s', (label_name, genre_id))


def refresh(helper_key: str) -> None:
    """Make a rule that was just written visible to the tagger in this process.

    Without this the write lands in the database and changes nothing until a restart:
    `Cache.databaseHelpers` preloads each lookup table once, at import. Other processes
    that tag (importer, downloader) catch up on their own -- see
    `LookupTableHelper.STALE_AFTER_SECONDS`.
    """
    Cache.reload(helper_key)
