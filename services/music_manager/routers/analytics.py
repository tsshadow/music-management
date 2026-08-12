"""Filtered aggregations over the library.

Path names the metric, query parameters name the scope. That keeps the endpoint
count flat as scopes multiply, and lets a later player page reuse these directly:
"BPM statistics for this artist" is /api/analytics/bpm-histogram?artist=X, not a
new endpoint.
"""

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from services.music_manager.api_key import is_system_api_key
from services.music_manager.database import get_db_connection
from services.music_manager.routers.analytics_filters import (
    FROM_CLAUSE,
    LibraryFilter,
    build_filter,
    parse_filter,
)

router = APIRouter(tags=['analytics'])

# Years outside this range are tagging accidents, not releases.
YEAR_FLOOR = 1950
YEAR_CEILING = 2100


def verify_api_key(x_api_key: str | None = Header(None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail='Missing API Key')
    if is_system_api_key(x_api_key):
        return {'type': 'system'}
    from services.music_manager.routers.users import verify_token
    try:
        res = verify_token(x_api_key)
        if res.get('status') == 'ok':
            return res
    except Exception:
        pass
    raise HTTPException(status_code=401, detail='Invalid API key')


def _query(sql_builder, f: LibraryFilter, fetch='all'):
    """Run one filtered aggregation and return its rows."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    where, params = build_filter(f)
    sql, extra = sql_builder(where)
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, (*params, *extra))
            return cursor.fetchone() if fetch == 'one' else cursor.fetchall()
    finally:
        conn.close()


@router.get('/summary')
def summary(f: LibraryFilter = Depends(parse_filter), _auth: dict = Depends(verify_api_key)):
    """Counts and data coverage for the current selection.

    Two queries rather than one. FROM_CLAUSE yields exactly one row per track --
    library_artists joins on primary_artist_id, library_track_audio_features on a
    unique track_uid -- so SUM() over it is safe. Joining the genre and label
    tables would multiply those rows and inflate every SUM, so the distinct genre
    and label counts are asked separately.
    """
    def totals_sql(where):
        return (f"""
            SELECT
                COUNT(*) AS tracks,
                COUNT(DISTINCT a.id) AS artists,
                COALESCE(SUM(t.duration_secs), 0) AS total_duration_secs,
                SUM(COALESCE(af.tempo, af.bpm_tag) IS NOT NULL) AS with_bpm,
                SUM(EXISTS (SELECT 1 FROM library_track_genres tg
                            WHERE tg.track_id = t.id)) AS with_genre,
                SUM(t.primary_artist_id IS NOT NULL) AS with_artist,
                SUM(af.track_id IS NOT NULL) AS analyzed
            {FROM_CLAUSE}
            WHERE {where}
        """, ())

    def variety_sql(where):
        return (f"""
            SELECT
                COUNT(DISTINCT tg.genre_id) AS genres,
                COUNT(DISTINCT tl.label_id) AS labels
            {FROM_CLAUSE}
            LEFT JOIN library_track_genres tg ON tg.track_id = t.id
            LEFT JOIN library_track_labels tl ON tl.track_id = t.id
            WHERE {where}
        """, ())

    row = _query(totals_sql, f, fetch='one') or {}
    variety = _query(variety_sql, f, fetch='one') or {}
    tracks = row.get('tracks') or 0

    def share(key):
        return round((row.get(key) or 0) / tracks, 4) if tracks else 0

    return {
        'tracks': tracks,
        'artists': row.get('artists') or 0,
        'labels': variety.get('labels') or 0,
        'genres': variety.get('genres') or 0,
        'total_duration_secs': float(row.get('total_duration_secs') or 0),
        'coverage': {
            'bpm': share('with_bpm'),
            'genre': share('with_genre'),
            'artist': share('with_artist'),
            'analyzed': share('analyzed'),
        },
    }


@router.get('/genre-distribution')
def genre_distribution(limit: int = Query(50, ge=1, le=500),
                       f: LibraryFilter = Depends(parse_filter),
                       _auth: dict = Depends(verify_api_key)):
    def sql(where):
        return (f"""
            SELECT rg.name AS genre, rg.state AS state, COUNT(DISTINCT t.id) AS count
            {FROM_CLAUSE}
            JOIN library_track_genres tg2 ON tg2.track_id = t.id
            JOIN rules_genres rg ON rg.id = tg2.genre_id
            WHERE {where} AND rg.state <> 'black'
            GROUP BY rg.id
            ORDER BY count DESC
            LIMIT %s
        """, (limit,))

    return _query(sql, f)


@router.get('/bpm-histogram')
def bpm_histogram(bucket: int = Query(5, ge=1, le=50),
                  f: LibraryFilter = Depends(parse_filter),
                  _auth: dict = Depends(verify_api_key)):
    """Raw detected tempo.

    Librosa misreports half and double time, which is a data-quality problem to
    fix in the analyzer rather than hide behind a correction here.
    """
    def sql(where):
        return (f"""
            SELECT FLOOR(COALESCE(af.tempo, af.bpm_tag) / %s) * %s AS bucket_start,
                   COUNT(*) AS count
            {FROM_CLAUSE}
            WHERE {where} AND COALESCE(af.tempo, af.bpm_tag) BETWEEN 20 AND 400
            GROUP BY bucket_start
            ORDER BY bucket_start
        """, (bucket, bucket))

    return _query(sql, f)


@router.get('/year-histogram')
def year_histogram(f: LibraryFilter = Depends(parse_filter),
                   _auth: dict = Depends(verify_api_key)):
    def sql(where):
        return (f"""
            SELECT af.release_year AS year, COUNT(*) AS count
            {FROM_CLAUSE}
            WHERE {where} AND af.release_year BETWEEN %s AND %s
            GROUP BY af.release_year
            ORDER BY af.release_year
        """, (YEAR_FLOOR, YEAR_CEILING))

    return _query(sql, f)


@router.get('/top-artists')
def top_artists(limit: int = Query(20, ge=1, le=200),
                f: LibraryFilter = Depends(parse_filter),
                _auth: dict = Depends(verify_api_key)):
    def sql(where):
        return (f"""
            SELECT a.name AS artist, COUNT(DISTINCT t.id) AS count
            {FROM_CLAUSE}
            WHERE {where} AND a.name IS NOT NULL
            GROUP BY a.id
            ORDER BY count DESC
            LIMIT %s
        """, (limit,))

    return _query(sql, f)


@router.get('/top-labels')
def top_labels(limit: int = Query(20, ge=1, le=200),
               f: LibraryFilter = Depends(parse_filter),
               _auth: dict = Depends(verify_api_key)):
    def sql(where):
        return (f"""
            SELECT l.name AS label, COUNT(DISTINCT t.id) AS count
            {FROM_CLAUSE}
            JOIN library_track_labels tl2 ON tl2.track_id = t.id
            JOIN library_labels l ON l.id = tl2.label_id
            WHERE {where}
            GROUP BY l.id
            ORDER BY count DESC
            LIMIT %s
        """, (limit,))

    return _query(sql, f)


@router.get('/artist-search')
def artist_search(q: str = Query(..., min_length=2),
                  limit: int = Query(20, ge=1, le=100),
                  _auth: dict = Depends(verify_api_key)):
    """Type-ahead for the artist facet. 46k artists is far too many to list."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    term = q.strip()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT a.name AS artist, COUNT(t.id) AS count
                FROM library_artists a
                LEFT JOIN library_tracks t ON t.primary_artist_id = a.id
                WHERE a.name LIKE %s
                GROUP BY a.id
                ORDER BY (a.name LIKE %s) DESC, count DESC, a.name
                LIMIT %s
            """, (f'%{term}%', f'{term}%', limit))
            return cursor.fetchall()
    finally:
        conn.close()
