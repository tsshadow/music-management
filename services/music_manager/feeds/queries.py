"""Every SQL string the feeds package uses, as `(sql, params)` builders.

The only module in `feeds/` that writes SQL -- `build.py` (Task 10) is the only
one that touches a connection, and everything else here works on plain rows and
dicts so it can be unit-tested without a database. Every user-supplied value
travels as a query parameter; nothing is ever interpolated into these strings
from a value (see `dominant_genre_query`, which picks between two fixed queries
rather than building one from its argument).

The two join traps this module exists to close (see
docs/designs/feeds/technical.md, Invariants):

- `library_track_audio_features.internal_track_id` is not unique, so a plain
  join into it multiplies candidate rows and, with them, every score. Every
  query here reduces it to one row per track in a grouped subquery first.
- `af.track_id` is a file-path hash, not `library_tracks.track_uid` -- the join
  back to a track always goes through `internal_track_id`.
"""

from datetime import datetime, timedelta

from services.music_manager.feeds.policy import FeedPolicy

# One row per track: a disagreeing release_date across several files sharing a
# track counts as unknown rather than picking one of them arbitrarily.
_AUDIO_FEATURES_SUBQUERY = """
    LEFT JOIN (
        SELECT internal_track_id,
               MIN(tempo) AS tempo,
               MIN(bpm_tag) AS bpm_tag,
               MIN(release_year) AS release_year,
               CASE WHEN COUNT(DISTINCT NULLIF(release_date, '')) = 1
                    THEN MIN(NULLIF(release_date, '')) END AS release_date
        FROM library_track_audio_features
        WHERE internal_track_id IS NOT NULL
        GROUP BY internal_track_id
    ) af ON af.internal_track_id = t.id
"""


def listens_query(username: str | None, window_days: int, now: datetime) -> tuple[str, list]:
    """A user's (or everyone's) listening history for the profile.

    `username is None` is the server profile: every listen, from every
    account, is read the same way a single user's would be. Labels and genres
    come back as comma-joined strings -- the caller splits them, the same way
    `/api/library/advanced` already does for genres.

    The window's cutoff is computed in Python from the injected `now`, the same
    way `candidates_query` computes its release cutoff -- never `NOW()` in SQL,
    which cannot be frozen by a test and would let this query's window and the
    candidate query's window disagree at a clock boundary.
    """
    params: list = []
    where = []
    if username is not None:
        where.append('s.username = %s')
        params.append(username)
    cutoff = now - timedelta(days=window_days)
    where.append('s.listened_at >= %s')
    params.append(cutoff)

    sql = f"""
        SELECT
            t.track_uid,
            s.listened_at,
            s.match_method,
            s.played_secs,
            a.name AS artist,
            (SELECT GROUP_CONCAT(l.name SEPARATOR ',')
             FROM library_track_labels tl
             JOIN library_labels l ON l.id = tl.label_id
             WHERE tl.track_id = t.id) AS labels,
            (SELECT GROUP_CONCAT(rg.name SEPARATOR ',')
             FROM library_track_genres tg
             JOIN rules_genres rg ON rg.id = tg.genre_id
             WHERE tg.track_id = t.id AND rg.state <> 'black') AS genres
        FROM scrobble_listens s
        JOIN library_tracks t ON t.id = s.track_id
        LEFT JOIN library_artists a ON a.id = t.primary_artist_id
        WHERE {' AND '.join(where)}
    """
    return sql, params


def _pool_clause(username: str, policy: FeedPolicy, params: list) -> str | None:
    """Pools other than `any`, OR-ed inside one parenthesised group.

    `any` means no restriction at all, so its presence makes the whole group
    vacuous -- it is never combined with the others. Rating is a filter only
    here, for the `loved` pool's membership rule; everywhere else it is a score
    adjustment, never a WHERE clause.
    """
    pools = policy.pools
    if not pools or 'any' in pools:
        return None
    clauses = []
    if 'unheard' in pools:
        clauses.append('NOT EXISTS (SELECT 1 FROM scrobble_listens sl WHERE sl.track_id = t.id AND sl.username = %s)')
        params.append(username)
    if 'loved' in pools:
        clauses.append('r.rating >= %s')
        params.append(policy.loved_min_rating)
    if not clauses:
        return None
    return '(' + ' OR '.join(clauses) + ')'


def candidates_query(username: str, policy: FeedPolicy, now: datetime) -> tuple[str, list]:
    """Everything eligible to appear in `policy`'s feed for `username`.

    Mirrors the `/api/library/advanced` track shape, plus the fields specific to
    a feed: `track_uid` (what a rating and a listen are keyed on), `has_label`,
    `is_soundcloud` (the label bonus and the SoundCloud penalty), `rating` (a
    score adjustment, and the `loved` pool's membership rule), `heard` (whether
    this listener has ever played the track, the only signal
    `policy.heard_rank_penalty` has to rank on), and the agreed release date out
    of the grouped audio-features subquery. Rating is never a WHERE-clause
    filter on its own -- only `_pool_clause` turns it into one, and only for
    `loved`.
    """
    # Positional order follows the %s tokens left to right in the SQL text, not
    # the order they are appended here: `heard`'s EXISTS lives in the SELECT
    # list, textually ahead of the rating join, which is itself ahead of every
    # WHERE param.
    params: list = [username, username]

    where = [
        'EXISTS (SELECT 1 FROM library_media_files mf WHERE mf.track_id = t.id)',
        't.duration_secs > 0',
        't.duration_secs < %s',
    ]
    params.append(policy.max_track_seconds)

    if policy.release_window_days is not None:
        # The window is closed at both ends. `release_date` is read out of a file
        # tag, so a mistagged 2027 release passes the day-precision check and the
        # lower bound, and then sorts to the top of every radar forever, because
        # step 7 orders by release date descending. A feed that counts a
        # mistagged future release as "released this week" is the measurement
        # this whole V1 exists to take, taken wrong.
        cutoff = (now.date() - timedelta(days=policy.release_window_days)).isoformat()
        where.append('LENGTH(af.release_date) = 10')
        where.append('af.release_date >= %s')
        params.append(cutoff)
        where.append('af.release_date <= %s')
        params.append(now.date().isoformat())

    pool_clause = _pool_clause(username, policy, params)
    if pool_clause:
        where.append(pool_clause)

    sql = f"""
        SELECT
            t.id, t.title, t.track_uid, a.name AS artist, t.duration_secs,
            EXISTS (SELECT 1 FROM scrobble_listens sl
                    WHERE sl.track_id = t.id AND sl.username = %s) AS heard,
            (SELECT l.name FROM library_labels l
             JOIN library_track_labels tl ON l.id = tl.label_id
             WHERE tl.track_id = t.id LIMIT 1) AS label,
            EXISTS (SELECT 1 FROM library_track_labels tl2 WHERE tl2.track_id = t.id) AS has_label,
            (SELECT GROUP_CONCAT(rg.name ORDER BY rg.name SEPARATOR ',')
             FROM rules_genres rg
             JOIN library_track_genres tg ON rg.id = tg.genre_id
             WHERE tg.track_id = t.id AND rg.state <> 'black') AS genres,
            (SELECT mf.file_path FROM library_media_files mf
             WHERE mf.track_id = t.id LIMIT 1) AS file_path,
            COALESCE(af.tempo, af.bpm_tag) AS bpm,
            af.release_year,
            af.release_date,
            EXISTS (SELECT 1 FROM library_track_channels ltc
                    JOIN channels c ON c.id = ltc.channel_id
                    WHERE ltc.track_id = t.id AND c.platform = 'soundcloud') AS is_soundcloud,
            r.rating
        FROM library_tracks t
        LEFT JOIN library_artists a ON a.id = t.primary_artist_id
        {_AUDIO_FEATURES_SUBQUERY}
        LEFT JOIN rating_tracks r
            ON r.entity_type = 'track' AND r.entity_id = t.track_uid AND r.username = %s
        WHERE {' AND '.join(where)}
    """
    return sql, params


_DOMINANT_GENRE_QUERIES = {
    'label': """
        SELECT l.name AS name, rg.name AS genre, COUNT(*) AS count
        FROM library_tracks t
        JOIN library_track_labels tl ON tl.track_id = t.id
        JOIN library_labels l ON l.id = tl.label_id
        JOIN library_track_genres tg ON tg.track_id = t.id
        JOIN rules_genres rg ON rg.id = tg.genre_id
        WHERE rg.state <> 'black'
        GROUP BY l.name, rg.name
    """,
    'artist': """
        SELECT a.name AS name, rg.name AS genre, COUNT(*) AS count
        FROM library_tracks t
        JOIN library_artists a ON a.id = t.primary_artist_id
        JOIN library_track_genres tg ON tg.track_id = t.id
        JOIN rules_genres rg ON rg.id = tg.genre_id
        WHERE rg.state <> 'black'
        GROUP BY a.name, rg.name
    """,
}


def dominant_genre_query(dimension: str) -> str:
    """Per-label or per-artist genre counts, feeding `buckets.dominant_genre`.

    `dimension` selects one of two fixed queries; it is never interpolated into
    either of them. Anything else is refused rather than guessed at.
    """
    try:
        return _DOMINANT_GENRE_QUERIES[dimension]
    except KeyError:
        raise ValueError(f'unknown dominant_genre dimension: {dimension!r}') from None


def hierarchy_query() -> str:
    """The whole subgenre graph: every `(subgenre, genre)` edge."""
    return 'SELECT subgenre, genre FROM rules_subgenre_hierarchy'


def exclusions_query(username: str) -> tuple[str, list]:
    """The entities this user has excluded from their own profile."""
    sql = 'SELECT entity_type, entity_name FROM feeds_profile_exclusions WHERE username = %s'
    return sql, [username]
