"""Every SQL string the "Oude hitjes" feed runs, as `(sql, params)` builders.

Kept apart from `feeds/queries.py` so the daily mixes and this feed can change independently.
Every value travels as a parameter; the only thing formatted into a statement is a run of
bare `%s` placeholders, and an empty id list is refused rather than rendered as `IN ()`.

Each query starts from the listener's own, small tables (their ratings, their listens) or
from the bounded popular-tracks table, never from a scan of the 300k-track library: the
feed's candidate set is "what this listener has touched" plus "known hits of artists they
like", and both are a few thousand rows at most.

Sets, live sets and podcasts are left out everywhere (`form` other than `track`): an old
favourite is a song, not a two-hour recording.
"""

from __future__ import annotations

from datetime import date

_TRACK_FORM = "(t.form IS NULL OR t.form = 'track')"


def _placeholders(values: list, what: str) -> str:
    if not values:
        raise ValueError(f'{what} needs at least one id; skip the query instead')
    return ', '.join(['%s'] * len(values))


def ratings_query(username: str) -> tuple[str, list]:
    """Every track this listener rated, with its work, the work's canonical and its artist."""
    sql = f"""
        SELECT t.id AS track_id, t.work_id, w.canonical_track_id, t.primary_artist_id AS artist_id,
               r.rating
        FROM rating_tracks r
        JOIN library_tracks t ON t.track_uid = r.entity_id
        LEFT JOIN library_works w ON w.id = t.work_id
        WHERE r.entity_type = 'track' AND r.username = %s AND {_TRACK_FORM}
    """
    return sql, [username]


def listens_query(username: str) -> tuple[str, list]:
    """Per song this listener ever played: how often, and when last -- any version counts.

    Grouped on the same key `build.song_key` collapses on (the work, else minus the track id,
    so the two id spaces cannot collide). The representative columns are aggregates so the
    statement is valid under ONLY_FULL_GROUP_BY; within one work they agree anyway.
    """
    sql = f"""
        SELECT COALESCE(t.work_id, -t.id) AS song,
               MAX(t.work_id) AS work_id,
               MIN(t.id) AS track_id,
               MAX(w.canonical_track_id) AS canonical_track_id,
               MIN(t.primary_artist_id) AS artist_id,
               COUNT(*) AS plays,
               MAX(s.listened_at) AS last_heard
        FROM scrobble_listens s
        JOIN library_tracks t ON t.id = s.track_id
        LEFT JOIN library_works w ON w.id = t.work_id
        WHERE s.username = %s AND {_TRACK_FORM}
        GROUP BY COALESCE(t.work_id, -t.id)
    """
    return sql, [username]


def popular_query(artist_ids: list[int]) -> tuple[str, list]:
    """The stored top-list matches whose library track is by one of `artist_ids`.

    Joined on `matched_track_uid`, which survives a library rebuild; the work is read from
    the library as it is now, not from the `matched_work_id` stored at fetch time.
    """
    sql = f"""
        SELECT p.source, p.position, t.id AS track_id, t.work_id, w.canonical_track_id,
               t.primary_artist_id AS artist_id
        FROM artist_popular_tracks p
        JOIN library_tracks t ON t.track_uid = p.matched_track_uid
        LEFT JOIN library_works w ON w.id = t.work_id
        WHERE p.matched_track_uid IS NOT NULL
          AND t.primary_artist_id IN ({_placeholders(artist_ids, 'popular_query')})
          AND {_TRACK_FORM}
    """
    return sql, list(artist_ids)


def versions_query(artist_ids: list[int], min_versions: int) -> tuple[str, list]:
    """Works by one of `artist_ids` that the library holds at least `min_versions` versions of."""
    sql = f"""
        SELECT t.work_id, COUNT(*) AS versions, MIN(t.id) AS track_id,
               MAX(w.canonical_track_id) AS canonical_track_id, MIN(t.primary_artist_id) AS artist_id
        FROM library_tracks t
        JOIN library_works w ON w.id = t.work_id
        WHERE t.primary_artist_id IN ({_placeholders(artist_ids, 'versions_query')}) AND {_TRACK_FORM}
        GROUP BY t.work_id
        HAVING COUNT(*) >= %s
    """
    return sql, [*artist_ids, min_versions]


def work_dates_query(work_ids: list[int]) -> tuple[str, list]:
    """Per work, the earliest release date and the earliest analyzer release year of any version.

    `NULLIF(release_date, '')`: the empty string is release_date_sync's "no agreed date", a
    decision and not a date, so it must not win MIN().
    """
    sql = f"""
        SELECT t.work_id AS work_id,
               MIN(NULLIF(t.release_date, '')) AS earliest_date,
               MIN(CASE WHEN af.release_year > 1900 THEN af.release_year END) AS earliest_year
        FROM library_tracks t
        LEFT JOIN library_track_audio_features af ON af.internal_track_id = t.id
        WHERE t.work_id IN ({_placeholders(work_ids, 'work_dates_query')})
        GROUP BY t.work_id
    """
    return sql, list(work_ids)


def track_dates_query(track_ids: list[int]) -> tuple[str, list]:
    """`work_dates_query` for tracks that belong to no work."""
    sql = f"""
        SELECT t.id AS track_id,
               MIN(NULLIF(t.release_date, '')) AS earliest_date,
               MIN(CASE WHEN af.release_year > 1900 THEN af.release_year END) AS earliest_year
        FROM library_tracks t
        LEFT JOIN library_track_audio_features af ON af.internal_track_id = t.id
        WHERE t.id IN ({_placeholders(track_ids, 'track_dates_query')})
        GROUP BY t.id
    """
    return sql, list(track_ids)


def artist_dated_query(artist_ids: list[int], cutoff: date) -> tuple[str, list]:
    """Per artist, how many of its tracks carry a full release date, and how many of those are old."""
    sql = f"""
        SELECT t.primary_artist_id AS artist_id,
               COUNT(*) AS dated,
               SUM(CASE WHEN t.release_date < %s THEN 1 ELSE 0 END) AS old
        FROM library_tracks t
        WHERE t.primary_artist_id IN ({_placeholders(artist_ids, 'artist_dated_query')})
          AND LENGTH(t.release_date) = 10
        GROUP BY t.primary_artist_id
    """
    return sql, [cutoff.isoformat(), *artist_ids]
