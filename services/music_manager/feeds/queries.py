"""Every SQL string the feeds package uses, as `(sql, params)` builders.

The only module in `feeds/` that writes SQL -- `build.py` (Task 10) is the only
one that touches a connection, and everything else here works on plain rows and
dicts so it can be unit-tested without a database. Every user-supplied value
travels as a query parameter; nothing is ever interpolated into these strings
from a value. `dominant_genre_query` is where that is easiest to get wrong: its
`dimension` picks between two fixed queries rather than building one, and the
only thing formatted into either is a run of bare `%s` placeholders (the shape
`routers/analytics_filters.py` uses, and the one `security:sast` accepts).

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
#
# That agreement rule is the release date's alone. `MIN(tempo)`, `MIN(bpm_tag)`
# and `MIN(release_year)` do *not* follow it: they pick the smallest value of
# however many rows the track has, disagreement and all. That is deliberate --
# `bpm` is displayed and never filtered or ranked on, and `release_year` is
# carried but read by nothing, so an arbitrary-but-stable pick cannot change
# which tracks a feed contains or in what order. Anything that starts selecting
# on either of them has to revisit this.
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

#: The release date a feed filters and sorts on. `library_tracks.release_date` is the servers'
#: own reading of the file tag, settled hourly by release_date_sync, and it is preferred
#: because it covers the whole library; the audio-features column behind it covers only the
#: tracks the ml-analyzer processed and on production was never filled at all.
#:
#: A CASE and not a COALESCE, because the two empty values do not mean the same thing. NULL is
#: "no server holds this file", a gap, and the analyzer's value is better than nothing. The
#: empty string is "a server holds it and no date could be agreed on" -- a decision the sync
#: made after weighing every file on every server, and falling through it would resurrect
#: exactly the date that was just rejected. COALESCE cannot tell those apart and would treat
#: both as a gap.
_RELEASE_DATE = "CASE WHEN t.release_date IS NULL THEN af.release_date ELSE NULLIF(t.release_date, '') END"

#: Whether this listener has played the *song*, not just this file: a listen of any version of
#: the track's work counts (docs/bug-reports/096). Two EXISTS rather than one with an OR, so the
#: first stays an index lookup on the track and the second one on idx_tracks_work_id; for a
#: track without a work the second compares against NULL and is simply false. Two `%s`, both the
#: username.
_SONG_HEARD = (
    '(EXISTS (SELECT 1 FROM scrobble_listens sl WHERE sl.track_id = t.id AND sl.username = %s)'
    ' OR EXISTS (SELECT 1 FROM library_tracks hv JOIN scrobble_listens hl ON hl.track_id = hv.id'
    ' WHERE hv.work_id = t.work_id AND hl.username = %s))'
)

#: The song's rating for this listener, the display roll-up of the song-versions design (ratings
#: stay stored per track_uid, they are only *shown* per song): the canonical's own rating when it
#: has one, else the highest on any other version, else -- for a track without a work -- the
#: track's own through the `r` join. The canonical's own rating wins over a higher one elsewhere
#: because a rating given from a list is written to the canonical; under a plain maximum, lowering
#: a song's rating from a list could never take effect. Two `%s`, both the username, textually
#: before the `r` join's.
_SONG_RATING = (
    'COALESCE((SELECT rc.rating FROM library_tracks c'
    " JOIN rating_tracks rc ON rc.entity_type = 'track' AND rc.entity_id = c.track_uid AND rc.username = %s"
    ' WHERE c.id = w.canonical_track_id),'
    ' (SELECT MAX(rv.rating) FROM library_tracks v'
    " JOIN rating_tracks rv ON rv.entity_type = 'track' AND rv.entity_id = v.track_uid AND rv.username = %s"
    ' WHERE v.work_id = t.work_id), r.rating)'
)


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

    Both `GROUP_CONCAT`s are ordered, as `candidates_query`'s is: an unordered
    one is stable in practice and guaranteed nowhere, and the two queries
    describing the same track differently is the kind of difference that shows
    up as an unreproducible profile rather than as an error.
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
            t.id AS track_id,
            t.track_uid,
            s.listened_at,
            s.match_method,
            s.played_secs,
            a.name AS artist,
            COALESCE(af.tempo, af.bpm_tag) AS bpm,
            (SELECT GROUP_CONCAT(l.name ORDER BY l.name SEPARATOR ',')
             FROM library_track_labels tl
             JOIN library_labels l ON l.id = tl.label_id
             WHERE tl.track_id = t.id) AS labels,
            (SELECT GROUP_CONCAT(rg.name ORDER BY rg.name SEPARATOR ',')
             FROM library_track_genres tg
             JOIN rules_genres rg ON rg.id = tg.genre_id
             WHERE tg.track_id = t.id AND rg.state <> 'black') AS genres
        FROM scrobble_listens s
        JOIN library_tracks t ON t.id = s.track_id
        LEFT JOIN library_artists a ON a.id = t.primary_artist_id
        {_AUDIO_FEATURES_SUBQUERY}
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
    # Both pools ask about the song, not the file: a rip of a song heard in its official
    # version is not "unheard", and a song loved in one version is loved in all of them.
    if 'unheard' in pools:
        clauses.append(f'NOT {_SONG_HEARD}')
        params.extend([username, username])
    if 'loved' in pools:
        clauses.append(f'{_SONG_RATING} >= %s')
        params.extend([username, username, policy.loved_min_rating])
    if not clauses:
        return None
    return '(' + ' OR '.join(clauses) + ')'


def candidates_query(
    username: str, policy: FeedPolicy, now: datetime, entity_filter: tuple[str, str] | None = None
) -> tuple[str, list]:
    """Everything eligible to appear in `policy`'s feed for `username`.

    Mirrors the `/api/library/advanced` track shape, plus the fields specific to
    a feed: `track_uid` (what a rating and a listen are keyed on), `has_label`,
    `is_soundcloud` (the label bonus and the SoundCloud penalty), `rating` (a
    score adjustment, and the `loved` pool's membership rule), `heard` (whether
    this listener has ever played the song, the only signal
    `policy.heard_rank_penalty` has to rank on), `work_id` and
    `canonical_track_id` (what the song collapse groups on), and the agreed release date out
    of the grouped audio-features subquery. Rating is never a WHERE-clause
    filter on its own -- only `_pool_clause` turns it into one, and only for
    `loved`.

    `label` is a single label and a track can carry several. Which one comes
    back decides the bucket a genre-less candidate competes in *and* the
    `label:<name>` reason the listener is shown for it, so `LIMIT 1` without an
    `ORDER BY` would leave both to the storage engine's mood. Alphabetical is
    not "the right label" -- for a multi-label track there is no such thing --
    but it is the same one on every run, which is what an explanation has to be.

    `entity_filter` is `('artist' | 'label', name)`, for the two rotating daily
    mixes (`daily-mix-artist`, `daily-mix-label`): everything else about the pool
    stays the same, only the candidate set narrows to one artist or one label.
    """
    # Positional order follows the %s tokens left to right in the SQL text, not
    # the order they are appended here: the song-level `heard` and `rating` live
    # in the SELECT list, textually ahead of the rating join, which is itself
    # ahead of every WHERE param.
    params: list = _select_params(username)

    where = [
        'EXISTS (SELECT 1 FROM library_media_files mf WHERE mf.track_id = t.id)',
        't.duration_secs > 0',
        't.duration_secs < %s',
    ]
    params.append(policy.max_track_seconds)

    if policy.release_window_days is not None:
        window_where, window_params = _release_window_conditions(policy.release_window_days, now)
        where.extend(window_where)
        params.extend(window_params)

    pool_clause = _pool_clause(username, policy, params)
    if pool_clause:
        where.append(pool_clause)

    if entity_filter is not None:
        dimension, name = entity_filter
        if dimension == 'artist':
            where.append('a.name = %s')
            params.append(name)
        elif dimension == 'label':
            where.append(
                'EXISTS (SELECT 1 FROM library_track_labels etl '
                'JOIN library_labels el ON el.id = etl.label_id '
                'WHERE etl.track_id = t.id AND el.name = %s)'
            )
            params.append(name)
        else:
            raise ValueError(f'unknown entity_filter dimension: {dimension!r}')

    return _candidate_select(' AND '.join(where)), params


def _release_window_conditions(window_days: int, now: datetime) -> tuple[list[str], list]:
    """The three conditions of a release window of `window_days`, and their two params.

    The window is closed at both ends. `release_date` is read out of a file tag, so
    a mistagged 2027 release passes the day-precision check and the lower bound,
    and then sorts to the top of every radar forever, because step 7 orders by
    release date descending. A feed that counts a mistagged future release as
    "released this week" is the measurement this whole V1 exists to take, taken
    wrong. Shared by `candidates_query` and `rotation_counts_query`, so the count
    that picks a rotating mix's artist and the candidates it then gets can never
    disagree about what "inside the window" means.
    """
    cutoff = (now.date() - timedelta(days=window_days)).isoformat()
    conditions = [
        f'LENGTH({_RELEASE_DATE}) = 10',
        f'{_RELEASE_DATE} >= %s',
        f'{_RELEASE_DATE} <= %s',
    ]
    return conditions, [cutoff, now.date().isoformat()]


#: The column a rotating mix's candidates are counted per. The artist is the track's
#: primary artist, exactly what `candidates_query`'s `a.name = %s` filters on; the
#: label comes from its own join, so a track on two labels counts for both, exactly
#: as the `EXISTS` in `candidates_query` would admit it into either label's mix.
_ROTATION_DIMENSIONS = {
    'artist': ('a.name', ''),
    'label': (
        'el.name',
        'JOIN library_track_labels etl ON etl.track_id = t.id JOIN library_labels el ON el.id = etl.label_id',
    ),
}


def rotation_counts_query(
    username: str,
    policy: FeedPolicy,
    now: datetime,
    dimension: str,
    names: list[str],
    windows: tuple[int | None, ...],
) -> tuple[str, list]:
    """How many songs each of `names` would give `policy`'s rotating mix, per window.

    One grouped statement for the whole top ten, so choosing today's artist (or
    label) costs one query bounded to those names, not one candidate query per
    name tried (bug report 110). It applies `candidates_query`'s own filters --
    a media file, the duration bounds, the unheard-or-loved pool -- and counts
    `COUNT(DISTINCT work, else track)`, the same key `build.song_key` collapses
    on, so a name's count is the number of places its mix could actually fill.
    One column per entry of `windows` (`songs_0`, `songs_1`, ...): the songs whose
    release date lies inside that window, or every song for a `None` window.

    Only `%s` placeholders are formatted in; `dimension` picks one of two fixed
    fragments and every name travels as a parameter. An empty `names` is refused
    rather than rendered as `IN ()`.
    """
    try:
        name_column, join = _ROTATION_DIMENSIONS[dimension]
    except KeyError:
        raise ValueError(f'unknown rotation dimension: {dimension!r}') from None
    if not names:
        raise ValueError('rotation_counts_query needs at least one name; skip the query instead')
    if not windows:
        raise ValueError('rotation_counts_query needs at least one window')

    song = 'COALESCE(t.work_id, -t.id)'
    columns = []
    # Params in text order: the window columns in the SELECT list, the rating
    # join's username, then every WHERE param.
    params: list = []
    for index, window in enumerate(windows):
        if window is None:
            columns.append(f'COUNT(DISTINCT {song}) AS songs_{index}')
            continue
        conditions, window_params = _release_window_conditions(window, now)
        columns.append(f"COUNT(DISTINCT CASE WHEN {' AND '.join(conditions)} THEN {song} END) AS songs_{index}")
        params.extend(window_params)
    params.append(username)

    where = [
        'EXISTS (SELECT 1 FROM library_media_files mf WHERE mf.track_id = t.id)',
        't.duration_secs > 0',
        't.duration_secs < %s',
    ]
    params.append(policy.max_track_seconds)
    pool_clause = _pool_clause(username, policy, params)
    if pool_clause:
        where.append(pool_clause)
    placeholders = ', '.join(['%s'] * len(names))
    where.append(f'{name_column} IN ({placeholders})')
    params.extend(names)

    sql = f"""
        SELECT {name_column} AS name, {', '.join(columns)}
        FROM library_tracks t
        LEFT JOIN library_works w ON w.id = t.work_id
        LEFT JOIN library_artists a ON a.id = t.primary_artist_id
        {join}
        {_AUDIO_FEATURES_SUBQUERY}
        LEFT JOIN rating_tracks r
            ON r.entity_type = 'track' AND r.entity_id = t.track_uid AND r.username = %s
        WHERE {' AND '.join(where)}
        GROUP BY {name_column}
    """
    return sql, params


def _select_params(username: str) -> list:
    """The parameters of `_candidate_select`'s own placeholders, in text order:
    `_SONG_HEARD` (two), `_SONG_RATING` (two), the `r` join (one)."""
    return [username] * 5


def _candidate_select(where_sql: str) -> str:
    """The candidate row shape, shared by `candidates_query` and `canonical_rows_query`.

    One SELECT for both, because the canonical a work is collapsed onto has to be
    scored on exactly the fields a candidate is: a second, hand-copied column list
    would drift, and a canonical scored without its label would lose the label
    bonus that is half the reason it is the canonical.

    `work_id` and `canonical_track_id` are what `build._collapse_to_songs` groups
    on; `heard` and `rating` are already song-level (see `_SONG_HEARD`,
    `_SONG_RATING`), so every version of one work carries the same two values.
    """
    return f"""
        SELECT
            t.id, t.title, t.track_uid, a.name AS artist, t.duration_secs,
            t.work_id, w.canonical_track_id,
            {_SONG_HEARD} AS heard,
            (SELECT l.name FROM library_labels l
             JOIN library_track_labels tl ON l.id = tl.label_id
             WHERE tl.track_id = t.id ORDER BY l.name LIMIT 1) AS label,
            EXISTS (SELECT 1 FROM library_track_labels tl2 WHERE tl2.track_id = t.id) AS has_label,
            (SELECT GROUP_CONCAT(rg.name ORDER BY rg.name SEPARATOR ',')
             FROM rules_genres rg
             JOIN library_track_genres tg ON rg.id = tg.genre_id
             WHERE tg.track_id = t.id AND rg.state <> 'black') AS genres,
            (SELECT mf.file_path FROM library_media_files mf
             WHERE mf.track_id = t.id LIMIT 1) AS file_path,
            COALESCE(af.tempo, af.bpm_tag) AS bpm,
            af.release_year,
            {_RELEASE_DATE} AS release_date,
            EXISTS (SELECT 1 FROM library_track_channels ltc
                    JOIN channels c ON c.id = ltc.channel_id
                    WHERE ltc.track_id = t.id AND c.platform = 'soundcloud') AS is_soundcloud,
            {_SONG_RATING} AS rating
        FROM library_tracks t
        LEFT JOIN library_works w ON w.id = t.work_id
        LEFT JOIN library_artists a ON a.id = t.primary_artist_id
        {_AUDIO_FEATURES_SUBQUERY}
        LEFT JOIN rating_tracks r
            ON r.entity_type = 'track' AND r.entity_id = t.track_uid AND r.username = %s
        WHERE {where_sql}
    """


def canonical_rows_query(username: str, track_ids: list[int]) -> tuple[str, list]:
    """The canonical versions a feed collapses onto, in the candidate row shape.

    A work's canonical is often not a candidate itself -- the official release can
    fall outside a window its SoundCloud rip is inside, or sit on a different
    duration side of a filter -- and the feed still has to play it (bug report 096:
    the radar served a 140 kbps rip of a song whose official version was in the
    library). None of the policy's filters apply here: the work already qualified
    through the version that was a candidate. The one condition kept is that a file
    exists, because a canonical without one cannot be played and the version that
    qualified is then the better answer.
    """
    if not track_ids:
        raise ValueError('canonical_rows_query needs at least one track id; skip the query instead')
    placeholders = ', '.join(['%s'] * len(track_ids))
    where = f'EXISTS (SELECT 1 FROM library_media_files mf WHERE mf.track_id = t.id) AND t.id IN ({placeholders})'
    return _candidate_select(where), _select_params(username) + list(track_ids)


_DOMINANT_GENRE_QUERIES = {
    'label': """
        SELECT l.name AS name, rg.name AS genre, COUNT(*) AS count
        FROM library_tracks t
        JOIN library_track_labels tl ON tl.track_id = t.id
        JOIN library_labels l ON l.id = tl.label_id
        JOIN library_track_genres tg ON tg.track_id = t.id
        JOIN rules_genres rg ON rg.id = tg.genre_id
        WHERE rg.state <> 'black' AND l.name IN ({placeholders})
        GROUP BY l.name, rg.name
    """,
    'artist': """
        SELECT a.name AS name, rg.name AS genre, COUNT(*) AS count
        FROM library_tracks t
        JOIN library_artists a ON a.id = t.primary_artist_id
        JOIN library_track_genres tg ON tg.track_id = t.id
        JOIN rules_genres rg ON rg.id = tg.genre_id
        WHERE rg.state <> 'black' AND a.name IN ({placeholders})
        GROUP BY a.name, rg.name
    """,
}


def dominant_genre_query(dimension: str, names: list[str]) -> tuple[str, list]:
    """Per-label or per-artist genre counts, feeding `buckets.dominant_genre`.

    Bounded to `names` on purpose. Unbounded, each of these groups over every
    `(label, genre)` and every `(artist, genre)` pair in a 300k-track library --
    two full-library aggregations on every single feed request, to answer a
    question about the handful of labels and artists the candidates of this one
    feed actually carry.

    `dimension` selects one of two fixed queries; it is never interpolated into
    either of them, and anything else is refused rather than guessed at. Only
    the `%s` placeholder list is formatted in (the shape
    `routers/analytics_filters.py` already uses, which `security:sast` accepts);
    every name travels as a parameter. An empty `names` is refused rather than
    rendered as `IN ()`, which is a syntax error -- the caller must skip the
    query instead.
    """
    try:
        template = _DOMINANT_GENRE_QUERIES[dimension]
    except KeyError:
        raise ValueError(f'unknown dominant_genre dimension: {dimension!r}') from None
    if not names:
        raise ValueError('dominant_genre_query needs at least one name; skip the query instead')
    placeholders = ', '.join(['%s'] * len(names))
    return template.format(placeholders=placeholders), list(names)


def hierarchy_query() -> str:
    """The whole subgenre graph: every `(subgenre, genre)` edge."""
    return 'SELECT subgenre, genre FROM rules_subgenre_hierarchy'


def exclusions_query(username: str) -> tuple[str, list]:
    """The entities this user has excluded from their own profile."""
    sql = 'SELECT entity_type, entity_name FROM feeds_profile_exclusions WHERE username = %s'
    return sql, [username]


def genre_hardness_digest_query() -> str:
    """One row that changes whenever any genre's hardness (or its curation state) does.

    `routers/feeds.py`'s `params_key` folds it into the key a spectrum-mix snapshot is
    stored under, so a curator's hardness edit ages those rows on the next read rather
    than the next day. An aggregate over the scored genres, not the rows themselves:
    this runs on every feed request, and the answer only has to differ, not explain.
    """
    return (
        'SELECT COUNT(*) AS genres, '
        "COALESCE(SUM(CRC32(CONCAT(name, '=', hardness, '=', state))), 0) AS checksum "
        'FROM rules_genres WHERE hardness IS NOT NULL'
    )


def genre_hardness_query(track_ids: list[int]) -> tuple[str, list]:
    """Per-track weighted genre hardness, bounded to one batch of tracks.

    Feeds `feeds.hardness.track_hardness`'s first fallback step: one row per track
    with `SUM(weight * hardness)` and `SUM(weight)`, restricted to genres that
    actually carry a `hardness` value -- a genre nobody has scored contributes to
    neither sum, which is what lets a track fall through to its label's mean instead
    of silently averaging in a `NULL`. Bounded to `track_ids` for the same reason
    `dominant_genre_query` is bounded to names: unbounded, this is one weighted
    average per track in the whole library, to answer a question about the tracks one
    feed request, or one band-edge computation, actually needs.
    """
    if not track_ids:
        raise ValueError('genre_hardness_query needs at least one track id; skip the query instead')
    placeholders = ', '.join(['%s'] * len(track_ids))
    sql = f"""
        SELECT tg.track_id AS track_id,
               SUM(tg.weight * rg.hardness) AS weighted_sum,
               SUM(tg.weight) AS weight_sum
        FROM library_track_genres tg
        JOIN rules_genres rg ON rg.id = tg.genre_id
        WHERE tg.track_id IN ({placeholders}) AND rg.hardness IS NOT NULL AND rg.state <> 'black'
        GROUP BY tg.track_id
    """
    return sql, list(track_ids)


_ENTITY_HARDNESS_QUERIES = {
    'label': """
        SELECT l.name AS name,
               SUM(tg.weight * rg.hardness) / SUM(tg.weight) AS mean_hardness,
               COUNT(DISTINCT tg.track_id) AS track_count
        FROM library_labels l
        JOIN library_track_labels tl ON tl.label_id = l.id
        JOIN library_track_genres tg ON tg.track_id = tl.track_id
        JOIN rules_genres rg ON rg.id = tg.genre_id
        WHERE rg.hardness IS NOT NULL AND rg.state <> 'black' AND l.name IN ({placeholders})
        GROUP BY l.name
        HAVING COUNT(DISTINCT tg.track_id) >= 5
    """,
    'artist': """
        SELECT a.name AS name,
               SUM(tg.weight * rg.hardness) / SUM(tg.weight) AS mean_hardness,
               COUNT(DISTINCT tg.track_id) AS track_count
        FROM library_artists a
        JOIN library_tracks t ON t.primary_artist_id = a.id
        JOIN library_track_genres tg ON tg.track_id = t.id
        JOIN rules_genres rg ON rg.id = tg.genre_id
        WHERE rg.hardness IS NOT NULL AND rg.state <> 'black' AND a.name IN ({placeholders})
        GROUP BY a.name
        HAVING COUNT(DISTINCT tg.track_id) >= 5
    """,
}


def entity_hardness_query(dimension: str, names: list[str]) -> tuple[str, list]:
    """A label's or artist's mean hardness, over the tracks that gave it one.

    The second and third fallback steps in `track_hardness`'s chain. The `HAVING`
    floor (`feeds.hardness.MIN_TRACKS_FOR_ENTITY_MEAN`, kept in sync by hand since it
    is baked into the SQL text) means a label or artist with only a handful of scored
    tracks is not trusted to speak for the tracks that have none -- one outlier
    release must not decide what an unrelated track on the same label inherits.
    Bounded to `names` the same way `dominant_genre_query` is, and for the same
    reason: unbounded, this groups over every label or artist in the library.
    """
    try:
        template = _ENTITY_HARDNESS_QUERIES[dimension]
    except KeyError:
        raise ValueError(f'unknown entity_hardness dimension: {dimension!r}') from None
    if not names:
        raise ValueError('entity_hardness_query needs at least one name; skip the query instead')
    placeholders = ', '.join(['%s'] * len(names))
    return template.format(placeholders=placeholders), list(names)
