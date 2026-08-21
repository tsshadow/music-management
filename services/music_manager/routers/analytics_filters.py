"""One definition of what a library selection is.

Both /api/library/advanced and every /api/analytics endpoint build their WHERE
clause here. Keeping it in one place is what lets the browser and a later player
page pose identical questions -- a player asking for an artist's BPM spread sends
the same `artist` parameter the sidebar sends.

Kept free of response models so it can be unit-tested on its own, and importable
from library.py without a circular import.
"""
from dataclasses import dataclass, field

from fastapi import Query

# A bare number in the search box means BPM rather than text, but only inside a
# range where that reading is plausible; 2024 is a year, not a tempo.
BPM_SEARCH_MIN = 50.0
BPM_SEARCH_MAX = 300.0
BPM_SEARCH_TOLERANCE = 2.0

# Every consumer selects from this same shape, so a filter fragment written here
# is valid in all of them. LEFT JOIN throughout: a track without audio features
# or without an artist is still a track. Both joins are one-to-one -- artists on
# primary_artist_id, audio features on a unique track_uid -- so this yields
# exactly one row per track and SUM() over it stays meaningful.
FROM_CLAUSE = """
    FROM library_tracks t
    LEFT JOIN library_artists a ON t.primary_artist_id = a.id
    LEFT JOIN library_track_audio_features af ON af.internal_track_id = t.id
"""

_LABEL_EXISTS = ("EXISTS (SELECT 1 FROM library_track_labels tl "
                 "JOIN library_labels l ON tl.label_id = l.id "
                 "WHERE tl.track_id = t.id AND l.name {op})")

_GENRE_EXISTS = ("EXISTS (SELECT 1 FROM library_track_genres tg "
                 "JOIN rules_genres rg ON tg.genre_id = rg.id "
                 "WHERE tg.track_id = t.id AND rg.name {op})")


@dataclass
class LibraryFilter:
    q: str = ''
    artist: list[str] = field(default_factory=list)
    genre: list[str] = field(default_factory=list)
    label: list[str] = field(default_factory=list)
    bpm_min: float | None = None
    bpm_max: float | None = None
    year_min: int | None = None
    year_max: int | None = None
    analyzed: bool | None = None


def _clean(values):
    return [v.strip() for v in (values or []) if v and v.strip()]


def _term_clause(term, clauses, params):
    """One search term: a plausible tempo, otherwise free text."""
    try:
        bpm = float(term)
    except ValueError:
        bpm = None
    if bpm is not None and BPM_SEARCH_MIN < bpm < BPM_SEARCH_MAX:
        clauses.append('(COALESCE(af.tempo, af.bpm_tag) BETWEEN %s AND %s)')
        params.extend([bpm - BPM_SEARCH_TOLERANCE, bpm + BPM_SEARCH_TOLERANCE])
        return
    pattern = f'%{term}%'
    clauses.append('(t.title LIKE %s OR a.name LIKE %s OR '
                   + _LABEL_EXISTS.format(op='LIKE %s') + ')')
    params.extend([pattern, pattern, pattern])


def build_filter(f: LibraryFilter):
    """Return a WHERE fragment (without the keyword) and its positional params.

    Values repeated within one parameter are OR; separate parameters are AND.
    Every user-supplied value travels as a parameter, never as literal SQL.
    """
    clauses = []
    params = []

    for term in (f.q or '').split(' '):
        if term.strip():
            _term_clause(term.strip(), clauses, params)

    genres = _clean(f.genre)
    if genres:
        placeholders = ', '.join(['%s'] * len(genres))
        clauses.append(_GENRE_EXISTS.format(op=f'IN ({placeholders})'))
        params.extend(genres)

    artists = _clean(f.artist)
    if artists:
        placeholders = ', '.join(['%s'] * len(artists))
        clauses.append(f'a.name IN ({placeholders})')
        params.extend(artists)

    labels = _clean(f.label)
    if labels:
        placeholders = ', '.join(['%s'] * len(labels))
        clauses.append(_LABEL_EXISTS.format(op=f'IN ({placeholders})'))
        params.extend(labels)

    if f.bpm_min is not None:
        clauses.append('COALESCE(af.tempo, af.bpm_tag) >= %s')
        params.append(f.bpm_min)
    if f.bpm_max is not None:
        clauses.append('COALESCE(af.tempo, af.bpm_tag) <= %s')
        params.append(f.bpm_max)

    if f.year_min is not None:
        clauses.append('af.release_year >= %s')
        params.append(f.year_min)
    if f.year_max is not None:
        clauses.append('af.release_year <= %s')
        params.append(f.year_max)

    if f.analyzed is True:
        clauses.append('af.track_id IS NOT NULL')
    elif f.analyzed is False:
        clauses.append('af.track_id IS NULL')

    if not clauses:
        return '1=1', []
    return ' AND '.join(clauses), params


def parse_filter(
    q: str = Query(''),
    artist: list[str] = Query(default=[]),
    genre: list[str] = Query(default=[]),
    label: list[str] = Query(default=[]),
    bpm_min: float | None = Query(None, ge=0, le=400),
    bpm_max: float | None = Query(None, ge=0, le=400),
    year_min: int | None = Query(None, ge=1900, le=2100),
    year_max: int | None = Query(None, ge=1900, le=2100),
    analyzed: bool | None = Query(None),
) -> LibraryFilter:
    """FastAPI dependency turning query parameters into a LibraryFilter."""
    return LibraryFilter(
        q=q, artist=artist, genre=genre, label=label,
        bpm_min=bpm_min, bpm_max=bpm_max,
        year_min=year_min, year_max=year_max, analyzed=analyzed,
    )
