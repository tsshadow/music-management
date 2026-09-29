"""What was actually listened to, as opposed to what is in the library.

/api/analytics answers questions about the collection -- how many tracks carry a
BPM, which labels are biggest. This router answers the other kind: what did
somebody play, when, and how often. The two never share a query base, because a
library filter selects tracks and a listening filter selects events; the year
filter in analytics_filters.py is a *release* year, which is the wrong year here.

Two tables hold those events and only one of them is joinable. ``scrobble_listens``
is a listen that found its track; ``scrobble_unmatched_listens`` is a listen whose
artist and title never matched anything in the library, which on production is the
majority -- 33.461 against 20.299 on 2026-09-06, so 62% of the history. Dropping
the unmatched half would make every total a lie by roughly a factor of two, so
counts, time series and sources read both tables and every response says how many
of its listens were unmatched.

Rankings cannot read both. A row with no ``track_id`` has no artist id and no
label, and ranking on its raw strings would invent a second, differently-spelled
artist list next to the real one. So /top-* is matched-only and carries the
unmatched count with it, for the page to show as the caveat it is.

Duration is reported in three parts rather than one. Only 876 of 20.299 matched
listens ever recorded how long they played; the rest can at best borrow the
track's full duration, which assumes every one of them ran to the end. An
unmatched listen has no track to borrow from at all, so its duration is unknown
rather than zero. ``measured``, ``imputed`` and ``unknown`` are returned
separately so a page can show an estimate without pretending it was measured.

Time is the last trap. ``listened_at`` is a TIMESTAMP and the database container
runs on UTC, so HOUR() reports a UTC hour and DATE() a UTC day -- both wrong for
"when do I listen" by the reader's offset, which moves an evening listen into the
small hours. A fixed offset would fix summer and break winter, so the caller names
a zone instead and the bucketing happens in Python, where DST is a solved problem.

Genre and release year are properties of a *track*, so they can only ever be
asked of a matched listen. Filtering on either therefore drops every unmatched
listen, not because they fail the filter but because they cannot be tested
against it. Every response under such a filter says how many were dropped that
way (``excluded_unmatched``), so the page can print it next to the filter rather
than let the totals shrink by 60% without explanation.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query

from services.music_manager.database import get_db_connection
from services.music_manager.identity import same_username
from services.music_manager.routers.users import verify_api_key

router = APIRouter(tags=['listening'])

BUCKETS = ('day', 'week', 'month')

MAX_LIMIT = 100

#: /top-genres feeds the page's genre picker as well as its chart, and the picker wants every
#: genre the listener ever played. 500 is well above the ~200 white genres on production.
MAX_GENRE_LIMIT = 500

#: How many values one filter dimension may carry. A chip bar never gets near it; a crafted URL
#: with thousands of `genre=` values would otherwise become an IN list of that length.
MAX_FILTER_VALUES = 50

#: Bounds a year filter value is validated against -- a sanity check on input, not a claim about
#: which years exist. Release dates on production run from 1996 to today.
YEAR_MIN, YEAR_MAX = 1000, 2999

#: The `year=` value that selects tracks without a usable release date.
UNKNOWN_YEAR = 'unknown'


def release_year_sql(track: str) -> str:
    """The release year of the track aliased ``track``, or NULL when it has none.

    The same source the feeds read (``_RELEASE_DATE`` in feeds/queries.py): the servers' own
    ``library_tracks.release_date`` first; when that is NULL -- no server holds the file -- the
    ml-analyzer's date, but only if all its rows agree; and an empty string, which is the sync's
    decision that no date could be agreed on, stays unknown rather than falling through. The
    analyzer fallback is a correlated lookup on ``idx_af_internal_track_id`` rather than the
    feeds' grouped derived table, because here it is evaluated per listen inside a WHERE and the
    CASE only reaches it for the few hundred tracks whose own date is NULL.

    ``release_date`` is a string ('YYYY-MM-DD' on production), so the year is its first four
    characters, and only when those are digits.
    """
    analyzer = (
        "(SELECT CASE WHEN COUNT(DISTINCT NULLIF(af.release_date, '')) = 1 "
        "THEN MIN(NULLIF(af.release_date, '')) END "
        f'FROM library_track_audio_features af WHERE af.internal_track_id = {track}.id)'
    )
    released = f"(CASE WHEN {track}.release_date IS NULL THEN {analyzer} ELSE NULLIF({track}.release_date, '') END)"
    return f"(CASE WHEN {released} REGEXP '^[0-9]{{4}}' THEN CAST(LEFT({released}, 4) AS UNSIGNED) END)"


@dataclass(frozen=True)
class TrackFilter:
    """Which *tracks* a request is about: by genre, by release year, or both.

    Within a dimension the values are alternatives (Hardstyle OR Uptempo Hardcore; 2015 OR the
    range 2018-2020 OR unknown); across dimensions they must all hold. A genre is matched by
    name against rules_genres, never a blacklisted one, so a name that does not exist simply
    matches nothing and the answer is empty rather than an error.
    """

    genres: tuple[str, ...] = ()
    years: tuple[int, ...] = ()
    unknown_year: bool = False
    year_from: int | None = None
    year_to: int | None = None

    @property
    def year_active(self) -> bool:
        """Whether any release-year condition was asked for."""
        return bool(self.years) or self.unknown_year or self.year_from is not None or self.year_to is not None

    @property
    def active(self) -> bool:
        """Whether this filter excludes anything -- and with it every unmatched listen."""
        return bool(self.genres) or self.year_active

    def clause(self, track_col: str) -> tuple[list[str], list]:
        """Conditions on the listen whose track id is ``track_col``.

        EXISTS against the track rather than a join, so a listen stays one row whatever the
        track carries: a track with two of the selected genres must still count once.
        """
        clauses: list[str] = []
        params: list = []
        if self.genres:
            marks = ', '.join(['%s'] * len(self.genres))
            clauses.append(
                'EXISTS (SELECT 1 FROM library_track_genres fg JOIN rules_genres fr ON fr.id = fg.genre_id'
                f" WHERE fg.track_id = {track_col} AND fr.state <> 'black' AND fr.name IN ({marks}))"
            )
            params.extend(self.genres)
        if self.year_active:
            year = release_year_sql('ft')
            alternatives: list[str] = []
            if self.years:
                alternatives.append(f'{year} IN ({", ".join(["%s"] * len(self.years))})')
                params.extend(self.years)
            if self.year_from is not None and self.year_to is not None:
                alternatives.append(f'{year} BETWEEN %s AND %s')
                params.extend([self.year_from, self.year_to])
            elif self.year_from is not None:
                alternatives.append(f'{year} >= %s')
                params.append(self.year_from)
            elif self.year_to is not None:
                alternatives.append(f'{year} <= %s')
                params.append(self.year_to)
            if self.unknown_year:
                alternatives.append(f'{year} IS NULL')
            clauses.append(
                f'EXISTS (SELECT 1 FROM library_tracks ft WHERE ft.id = {track_col} AND ({" OR ".join(alternatives)}))'
            )
        return clauses, params


# One row per hour that saw a listen, rather than one row per listen: the
# rollup is what makes a Python-side timezone conversion affordable. Whole
# history is roughly three years, so this is thousands of rows, not 54.000.
_HOURLY_SQL = """
    SELECT slot, SUM(matched) AS matched, SUM(unmatched) AS unmatched
    FROM (
        SELECT DATE_FORMAT(listened_at, '%%Y-%%m-%%d %%H') AS slot,
               COUNT(*) AS matched, 0 AS unmatched
        FROM scrobble_listens WHERE {matched_where}
        GROUP BY slot
        UNION ALL
        SELECT DATE_FORMAT(listened_at, '%%Y-%%m-%%d %%H') AS slot,
               0 AS matched, COUNT(*) AS unmatched
        FROM scrobble_unmatched_listens WHERE {unmatched_where}
        GROUP BY slot
    ) AS listens
    GROUP BY slot
    ORDER BY slot
"""


class ListeningScope:
    """Which listens a request is about: whose, between when, and in whose day.

    ``from`` and ``to`` are dates in the caller's zone, not in the database's.
    Asking for January in Amsterdam and getting the UTC January would move two
    hours of New Year's Eve into the wrong year, so the boundaries are converted
    here once and travel as UTC instants from then on.
    """

    def __init__(
        self,
        username: str | None,
        date_from: date | None,
        date_to: date | None,
        zone: ZoneInfo,
        track_filter: TrackFilter | None = None,
    ):
        self.username = username
        self.date_from = date_from
        self.date_to = date_to
        self.zone = zone
        self.track_filter = track_filter or TrackFilter()

    @property
    def filtered(self) -> bool:
        """Whether a genre or year filter is active, which excludes every unmatched listen."""
        return self.track_filter.active

    def _as_utc(self, day: date, days_after: int = 0) -> datetime:
        local = datetime.combine(day + timedelta(days=days_after), time.min, tzinfo=self.zone)
        return local.astimezone(UTC).replace(tzinfo=None)

    def where(self) -> tuple[str, list]:
        """A WHERE fragment on who and when only, valid against either listens table.

        This ignores the genre and year filter on purpose: it is what counts the unmatched
        listens a filter excluded. Queries that select listens use ``matched_where`` or
        ``unmatched_where`` instead.

        Columns are unqualified on purpose. ``username`` and ``listened_at`` exist
        only on the two listens tables, never on the library tables joined next to
        them, so an unqualified name cannot become ambiguous -- and leaving the
        alias out keeps this a constant string rather than one built per caller.
        """
        clauses, params = [], []
        if self.username:
            clauses.append('username = %s')
            params.append(self.username)
        if self.date_from:
            clauses.append('listened_at >= %s')
            params.append(self._as_utc(self.date_from))
        if self.date_to:
            # Exclusive on the next local midnight, so the last day is whole
            # however late in it somebody listened.
            clauses.append('listened_at < %s')
            params.append(self._as_utc(self.date_to, days_after=1))
        if not clauses:
            return '1=1', []
        return ' AND '.join(clauses), params

    def matched_where(self, track_col: str) -> tuple[str, list]:
        """``where()`` plus the genre and year filter, for ``scrobble_listens``.

        ``track_col`` names the listen's track id as the query spells it -- ``l.track_id`` where
        the table is aliased, ``scrobble_listens.track_id`` where it is not. Unlike ``username``
        it cannot stay unqualified, because library_track_labels and library_track_genres, which
        some of these queries join, carry a ``track_id`` of their own.
        """
        where, params = self.where()
        clauses, extra = self.track_filter.clause(track_col)
        if not clauses:
            return where, params
        return ' AND '.join([where, *clauses]), [*params, *extra]

    def unmatched_where(self) -> tuple[str, list]:
        """``where()`` for ``scrobble_unmatched_listens``, empty under a genre or year filter.

        An unmatched listen has no track, so it has no genre and no release year, and a filter
        on either cannot include it. ``1=0`` rather than skipping the query keeps every caller's
        shape the same; MariaDB answers an impossible WHERE without reading the table.
        """
        where, params = self.where()
        if self.filtered:
            return where + ' AND 1=0', params
        return where, params


def parse_scope(
    username: str | None = Query(None),
    date_from: date | None = Query(None, alias='from'),
    date_to: date | None = Query(None, alias='to'),
    tz: str = Query('UTC'),
    genre: list[str] = Query([]),
    year: list[str] = Query([]),
    year_from: int | None = Query(None, ge=YEAR_MIN, le=YEAR_MAX),
    year_to: int | None = Query(None, ge=YEAR_MIN, le=YEAR_MAX),
    auth: dict = Depends(verify_api_key),
) -> ListeningScope:
    """Turn query parameters into a scope, refusing another user's history.

    A system key may ask about anyone, and about everyone at once when it names
    nobody. A user key is pinned to its own account: the API key is the only
    credential the frontend has and the LMS proxy forwards it without checking
    whose history is being asked for, so honouring ``?username=`` from a user key
    would make every listener's history readable by every other listener.
    """
    if date_from and date_to and date_to < date_from:
        raise HTTPException(status_code=400, detail="'to' is before 'from'")
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status_code=400, detail=f'Unknown timezone: {tz}') from None
    track_filter = parse_track_filter(genre, year, year_from, year_to)

    if auth.get('type') == 'system':
        return ListeningScope(username, date_from, date_to, zone, track_filter)
    own = (auth.get('user') or {}).get('username')
    # Account names are case-insensitive (services/music_manager/identity.py).
    if username and not same_username(username, own):
        raise HTTPException(status_code=403, detail="Not allowed to read another user's listening history")
    return ListeningScope(own, date_from, date_to, zone, track_filter)


def parse_track_filter(genres: list[str], years: list[str], year_from: int | None, year_to: int | None) -> TrackFilter:
    """Validate the genre and year query parameters into a ``TrackFilter``.

    A malformed value is a 400: ``year=abc`` is a broken request. An unknown but well-formed
    value is not -- ``genre=Polka`` is a question with an empty answer, and answering it with an
    error would take down every panel of the page at once. Blank and repeated values are
    dropped, so a stray ``genre=`` means no filter.
    """
    names = tuple(dict.fromkeys(g.strip() for g in genres if g and g.strip()))
    picked: list[int] = []
    unknown = False
    for raw in years:
        value = (raw or '').strip()
        if not value:
            continue
        if value.lower() == UNKNOWN_YEAR:
            unknown = True
            continue
        if not value.isdigit() or not YEAR_MIN <= int(value) <= YEAR_MAX:
            raise HTTPException(
                status_code=400, detail=f"Invalid year {raw!r}: expected {YEAR_MIN}-{YEAR_MAX} or '{UNKNOWN_YEAR}'"
            )
        picked.append(int(value))
    if len(names) > MAX_FILTER_VALUES or len(picked) > MAX_FILTER_VALUES:
        raise HTTPException(status_code=400, detail=f'At most {MAX_FILTER_VALUES} values per filter')
    if year_from is not None and year_to is not None and year_to < year_from:
        raise HTTPException(status_code=400, detail="'year_to' is before 'year_from'")
    return TrackFilter(
        genres=names,
        years=tuple(sorted(set(picked))),
        unknown_year=unknown,
        year_from=year_from,
        year_to=year_to,
    )


def _rows(sql: str, params, fetch='all'):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, tuple(params))
            return cursor.fetchone() if fetch == 'one' else cursor.fetchall()
    finally:
        conn.close()


def _unmatched_disclosure(scope: ListeningScope) -> dict[str, int]:
    """How many unmatched listens the scope holds, and how many a filter excluded.

    Always counted over who and when only. Without a genre or year filter those listens are in
    scope and merely unrankable (``unmatched``); with one they are out of scope altogether
    (``excluded_unmatched``). One of the two is always zero.
    """
    where, params = scope.where()
    row = _rows(
        'SELECT COUNT(*) AS unmatched FROM scrobble_unmatched_listens WHERE ' + where,
        params,
        fetch='one',
    )
    count = int((row or {}).get('unmatched') or 0)
    if scope.filtered:
        return {'unmatched': 0, 'excluded_unmatched': count}
    return {'unmatched': count, 'excluded_unmatched': 0}


def _hourly(scope: ListeningScope):
    """Listens per UTC hour, already converted to the caller's local hour.

    Yields ``(local_datetime, matched, unmatched)``. A whole UTC hour is assumed
    to fall inside one local hour, which holds for every zone whose offset is a
    whole number of hours and is off by at most one bucket for the handful at
    :30 or :45.
    """
    matched_where, matched_params = scope.matched_where('scrobble_listens.track_id')
    unmatched_where, unmatched_params = scope.unmatched_where()
    sql = _HOURLY_SQL.replace('{matched_where}', matched_where).replace('{unmatched_where}', unmatched_where)
    rows = _rows(sql, [*matched_params, *unmatched_params])
    out = []
    for row in rows:
        slot = row['slot']
        if not slot:
            continue
        moment = datetime.strptime(slot, '%Y-%m-%d %H').replace(tzinfo=UTC).astimezone(scope.zone)
        out.append((moment, int(row['matched'] or 0), int(row['unmatched'] or 0)))
    out.sort(key=lambda item: item[0])
    return out


def _bucket_key(moment: datetime, bucket: str) -> str:
    if bucket == 'day':
        return moment.strftime('%Y-%m-%d')
    if bucket == 'month':
        return moment.strftime('%Y-%m')
    # ISO week, so a week belongs to the year holding its Thursday and the last
    # days of December can read as week 1 of the next year. That is the standard
    # every calendar in this app already follows.
    iso = moment.isocalendar()
    return f'{iso.year}-W{iso.week:02d}'


def _iso(value):
    return value.isoformat() if value is not None else None


def _share(part: int, whole: int):
    """A share of nothing is undefined, not zero."""
    return round(part / whole, 4) if whole else None


@router.get('/summary')
def summary(scope: ListeningScope = Depends(parse_scope)):
    """Totals for the scope, with the three kinds of "how long" kept apart.

    ``measured_secs`` sums only listens that reported how long they played, and
    counts a reported zero as measured. ``imputed_secs`` is the fallback: the
    track's full duration for a matched listen that never reported one, which
    assumes it ran to the end. An unmatched listen has neither, so it lands in
    ``unknown_duration_listens`` and contributes no seconds at all -- which makes
    ``estimated_secs`` a floor rather than a guess at the whole.

    Under a genre or year filter the unmatched listens are counted but not included: they land
    in ``excluded_unmatched`` and every other unmatched figure is zero.
    """
    matched_where, matched_params = scope.matched_where('l.track_id')
    where, params = scope.where()
    matched = (
        _rows(
            """
            SELECT
                COUNT(*) AS listens,
                COUNT(DISTINCT l.track_id) AS tracks,
                COUNT(DISTINCT t.primary_artist_id) AS artists,
                SUM(l.played_secs IS NOT NULL) AS measured_listens,
                SUM(l.played_secs IS NULL AND t.duration_secs IS NOT NULL) AS imputed_listens,
                COALESCE(SUM(l.played_secs), 0) AS measured_secs,
                COALESCE(SUM(CASE WHEN l.played_secs IS NULL THEN t.duration_secs END), 0) AS imputed_secs,
                MIN(l.listened_at) AS first_listen,
                MAX(l.listened_at) AS last_listen
            FROM scrobble_listens l
            LEFT JOIN library_tracks t ON t.id = l.track_id
            WHERE """
            + matched_where,
            matched_params,
            fetch='one',
        )
        or {}
    )
    # Over who and when only, so a filtered request still learns how many it excluded.
    unmatched = (
        _rows(
            """
            SELECT
                COUNT(*) AS listens,
                SUM(played_secs IS NOT NULL) AS measured_listens,
                COALESCE(SUM(played_secs), 0) AS measured_secs,
                MIN(listened_at) AS first_listen,
                MAX(listened_at) AS last_listen
            FROM scrobble_unmatched_listens
            WHERE """
            + where,
            params,
            fetch='one',
        )
        or {}
    )

    excluded_unmatched = 0
    if scope.filtered:
        excluded_unmatched = int(unmatched.get('listens') or 0)
        unmatched = {}
    matched_listens = int(matched.get('listens') or 0)
    unmatched_listens = int(unmatched.get('listens') or 0)
    total = matched_listens + unmatched_listens
    measured_listens = int(matched.get('measured_listens') or 0) + int(unmatched.get('measured_listens') or 0)
    imputed_listens = int(matched.get('imputed_listens') or 0)
    measured_secs = float(matched.get('measured_secs') or 0) + float(unmatched.get('measured_secs') or 0)
    imputed_secs = float(matched.get('imputed_secs') or 0)

    firsts = [d for d in (matched.get('first_listen'), unmatched.get('first_listen')) if d]
    lasts = [d for d in (matched.get('last_listen'), unmatched.get('last_listen')) if d]

    return {
        'listens': total,
        'matched': matched_listens,
        'unmatched': unmatched_listens,
        'unmatched_share': _share(unmatched_listens, total),
        'filtered': scope.filtered,
        'excluded_unmatched': excluded_unmatched,
        'tracks': int(matched.get('tracks') or 0),
        'artists': int(matched.get('artists') or 0),
        'measured_listens': measured_listens,
        'imputed_listens': imputed_listens,
        'unknown_duration_listens': total - measured_listens - imputed_listens,
        'measured_share': _share(measured_listens, total),
        'measured_secs': round(measured_secs),
        'imputed_secs': round(imputed_secs),
        'estimated_secs': round(measured_secs + imputed_secs),
        'first_listen': _iso(min(firsts)) if firsts else None,
        'last_listen': _iso(max(lasts)) if lasts else None,
    }


@router.get('/timeline')
def timeline(bucket: str = Query('month'), scope: ListeningScope = Depends(parse_scope)):
    """Listens per day, week or month, matched and unmatched side by side.

    Buckets with no listens at all are left out rather than zero-filled: the
    range can be the whole history, and the page knows its own axis. Buckets that
    hold only unmatched listens do appear, which is most of 2024 and exactly the
    shape a reader needs before trusting the rankings.
    """
    if bucket not in BUCKETS:
        raise HTTPException(status_code=400, detail=f'Unknown bucket, expected one of {", ".join(BUCKETS)}')
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for moment, matched, unmatched in _hourly(scope):
        entry = totals[_bucket_key(moment, bucket)]
        entry[0] += matched
        entry[1] += unmatched
    return {
        'bucket': bucket,
        'timezone': str(scope.zone),
        'buckets': [
            {'bucket': key, 'matched': matched, 'unmatched': unmatched, 'listens': matched + unmatched}
            for key, (matched, unmatched) in sorted(totals.items())
        ],
    }


@router.get('/clock')
def clock(scope: ListeningScope = Depends(parse_scope)):
    """Listens per hour of the day and per weekday, in the caller's zone.

    Every hour and every weekday is returned, including the empty ones: a chart
    that only receives the hours somebody listened in draws a different shape
    every time and hides the gaps, which here are the interesting part.
    """
    hours = [0] * 24
    # 0 = Monday .. 6 = Sunday, which is the order the page lists them in.
    weekdays = [0] * 7
    for moment, matched, unmatched in _hourly(scope):
        count = matched + unmatched
        hours[moment.hour] += count
        weekdays[moment.weekday()] += count
    return {'timezone': str(scope.zone), 'hours': hours, 'weekdays': weekdays}


@router.get('/sources')
def sources(scope: ListeningScope = Depends(parse_scope)):
    """Where the listening happened -- web player, phone, car, the legacy interface.

    ``source`` predates being recorded properly, so historical rows carry whatever
    the importer put there, and it names provenance rather than a device: an
    imported ListenBrainz history is one source however many players produced it.
    NULL becomes 'unknown' rather than being dropped, so these counts still add up
    to the total /summary reports.
    """
    matched_where, matched_params = scope.matched_where('scrobble_listens.track_id')
    unmatched_where, unmatched_params = scope.unmatched_where()
    rows = _rows(
        """
        SELECT source, SUM(matched) AS matched, SUM(unmatched) AS unmatched
        FROM (
            SELECT COALESCE(source, 'unknown') AS source, COUNT(*) AS matched, 0 AS unmatched
            FROM scrobble_listens WHERE """
        + matched_where
        + """
            GROUP BY COALESCE(source, 'unknown')
            UNION ALL
            SELECT COALESCE(source, 'unknown') AS source, 0 AS matched, COUNT(*) AS unmatched
            FROM scrobble_unmatched_listens WHERE """
        + unmatched_where
        + """
            GROUP BY COALESCE(source, 'unknown')
        ) AS listens
        GROUP BY source
        ORDER BY SUM(matched) + SUM(unmatched) DESC
        """,
        [*matched_params, *unmatched_params],
    )
    return {
        'sources': [
            {
                'source': r['source'],
                'matched': int(r['matched'] or 0),
                'unmatched': int(r['unmatched'] or 0),
                'listens': int(r['matched'] or 0) + int(r['unmatched'] or 0),
            }
            for r in rows
        ]
    }


def _ranking(sql: str, scope: ListeningScope, limit: int):
    where, params = scope.matched_where('l.track_id')
    rows = _rows(sql.replace('{where}', where), [*params, limit])
    return {**_unmatched_disclosure(scope), 'items': rows}


@router.get('/top-tracks')
def top_tracks(limit: int = Query(20, ge=1, le=MAX_LIMIT), scope: ListeningScope = Depends(parse_scope)):
    """Most played tracks. Matched listens only -- see the module docstring."""
    result = _ranking(
        """
        SELECT t.id AS track_id,
               t.title,
               a.name AS artist,
               COUNT(*) AS listens,
               ROUND(COALESCE(SUM(COALESCE(l.played_secs, t.duration_secs)), 0)) AS estimated_secs,
               MAX(l.listened_at) AS last_listen
        FROM scrobble_listens l
        JOIN library_tracks t ON t.id = l.track_id
        LEFT JOIN library_artists a ON a.id = t.primary_artist_id
        WHERE {where}
        GROUP BY t.id, t.title, a.name
        ORDER BY listens DESC, last_listen DESC
        LIMIT %s
        """,
        scope,
        limit,
    )
    return {
        'unmatched': result['unmatched'],
        'excluded_unmatched': result['excluded_unmatched'],
        'tracks': [
            {
                'track_id': r['track_id'],
                'title': r['title'],
                'artist': r['artist'],
                'listens': int(r['listens'] or 0),
                'estimated_secs': int(r['estimated_secs'] or 0),
                'last_listen': _iso(r['last_listen']),
            }
            for r in result['items']
        ],
    }


@router.get('/top-artists')
def top_artists(limit: int = Query(20, ge=1, le=MAX_LIMIT), scope: ListeningScope = Depends(parse_scope)):
    """Most played artists, by the track's primary artist.

    A track has exactly one primary artist, so this counts every listen once. A
    featured artist does not appear here; crediting one would mean joining
    library_track_artists and counting a single listen several times, which is a
    different metric and belongs under a different name.
    """
    result = _ranking(
        """
        SELECT a.id AS artist_id,
               a.name AS artist,
               COUNT(*) AS listens,
               COUNT(DISTINCT t.id) AS tracks,
               ROUND(COALESCE(SUM(COALESCE(l.played_secs, t.duration_secs)), 0)) AS estimated_secs
        FROM scrobble_listens l
        JOIN library_tracks t ON t.id = l.track_id
        JOIN library_artists a ON a.id = t.primary_artist_id
        WHERE {where}
        GROUP BY a.id, a.name
        ORDER BY listens DESC, a.name
        LIMIT %s
        """,
        scope,
        limit,
    )
    return {
        'unmatched': result['unmatched'],
        'excluded_unmatched': result['excluded_unmatched'],
        'artists': [
            {
                'artist_id': r['artist_id'],
                'artist': r['artist'],
                'listens': int(r['listens'] or 0),
                'tracks': int(r['tracks'] or 0),
                'estimated_secs': int(r['estimated_secs'] or 0),
            }
            for r in result['items']
        ],
    }


@router.get('/top-labels')
def top_labels(limit: int = Query(20, ge=1, le=MAX_LIMIT), scope: ListeningScope = Depends(parse_scope)):
    """Most played labels.

    ``library_track_labels`` is keyed on (track_id, label_id), so grouping by
    label id counts each listen once inside each label. A track carrying two
    labels therefore counts for both, which is right for a ranking -- the listen
    genuinely belongs to both -- and wrong for a percentage. That is why no share
    is returned here: the column does not add up to the total.
    """
    result = _ranking(
        """
        SELECT lb.id AS label_id,
               lb.name AS label,
               COUNT(*) AS listens,
               COUNT(DISTINCT t.id) AS tracks
        FROM scrobble_listens l
        JOIN library_tracks t ON t.id = l.track_id
        JOIN library_track_labels tl ON tl.track_id = t.id
        JOIN library_labels lb ON lb.id = tl.label_id
        WHERE {where}
        GROUP BY lb.id, lb.name
        ORDER BY listens DESC, lb.name
        LIMIT %s
        """,
        scope,
        limit,
    )
    return {
        'unmatched': result['unmatched'],
        'excluded_unmatched': result['excluded_unmatched'],
        'labels': [
            {
                'label_id': r['label_id'],
                'label': r['label'],
                'listens': int(r['listens'] or 0),
                'tracks': int(r['tracks'] or 0),
            }
            for r in result['items']
        ],
    }


@router.get('/top-genres')
def top_genres(limit: int = Query(20, ge=1, le=MAX_GENRE_LIMIT), scope: ListeningScope = Depends(parse_scope)):
    """Most played genres. Matched listens only, and the column does not add up.

    ``library_track_genres`` is keyed on (track_id, genre_id) and a track routinely carries
    several -- Hardcore and Uptempo Hardcore, say -- so a listen counts once inside *each* of
    its genres. The rows overlap and their sum exceeds the matched total; ``matched`` and
    ``untagged`` come back beside them so the page can say so with numbers. A blacklisted genre
    is a tag curation rejected and is left out, as in /api/analytics/genre-distribution.

    Under a genre filter this shows the selected genres *and* every genre the selected tracks
    also carry -- which is what a reader filtering on Hardstyle wants to see: what else those
    tracks are.
    """
    where, params = scope.matched_where('l.track_id')
    rows = _rows(
        """
        SELECT rg.id AS genre_id,
               rg.name AS genre,
               COUNT(*) AS listens,
               COUNT(DISTINCT l.track_id) AS tracks
        FROM scrobble_listens l
        JOIN library_track_genres tg ON tg.track_id = l.track_id
        JOIN rules_genres rg ON rg.id = tg.genre_id AND rg.state <> 'black'
        WHERE """
        + where
        + """
        GROUP BY rg.id, rg.name
        ORDER BY listens DESC, rg.name
        LIMIT %s
        """,
        [*params, limit],
    )
    totals = (
        _rows(
            """
            SELECT COUNT(*) AS matched,
                   SUM(NOT EXISTS (
                       SELECT 1 FROM library_track_genres ug
                       JOIN rules_genres ur ON ur.id = ug.genre_id AND ur.state <> 'black'
                       WHERE ug.track_id = l.track_id
                   )) AS untagged
            FROM scrobble_listens l
            WHERE """
            + where,
            params,
            fetch='one',
        )
        or {}
    )
    return {
        **_unmatched_disclosure(scope),
        'matched': int(totals.get('matched') or 0),
        'untagged': int(totals.get('untagged') or 0),
        'genres': [
            {
                'genre_id': r['genre_id'],
                'genre': r['genre'],
                'listens': int(r['listens'] or 0),
                'tracks': int(r['tracks'] or 0),
            }
            for r in rows
        ],
    }


@router.get('/years')
def release_years(scope: ListeningScope = Depends(parse_scope)):
    """Listens by the release year of what was played. Matched listens only.

    Unlike genres, every listen has exactly one release year or none, so ``years`` plus
    ``unknown`` adds up to ``matched``. A track without a usable date -- a quarter of the
    listened-to library on production, mostly the empty string the date sync writes when the
    servers disagree -- goes to ``unknown`` rather than disappearing. Only the years that occur
    are returned; decades are the page's arithmetic, not a second endpoint.
    """
    where, params = scope.matched_where('l.track_id')
    rows = _rows(
        """
        SELECT y.release_year AS year, COUNT(*) AS listens, COUNT(DISTINCT y.track_id) AS tracks
        FROM (
            SELECT l.track_id, """
        + release_year_sql('t')
        + """ AS release_year
            FROM scrobble_listens l
            JOIN library_tracks t ON t.id = l.track_id
            WHERE """
        + where
        + """
        ) AS y
        GROUP BY y.release_year
        ORDER BY y.release_year
        """,
        params,
    )
    years, unknown = [], {'listens': 0, 'tracks': 0}
    for r in rows:
        entry = {'listens': int(r['listens'] or 0), 'tracks': int(r['tracks'] or 0)}
        if r['year'] is None:
            unknown = entry
        else:
            years.append({'year': int(r['year']), **entry})
    return {
        **_unmatched_disclosure(scope),
        'matched': sum(y['listens'] for y in years) + unknown['listens'],
        'unknown': unknown,
        'years': years,
    }
