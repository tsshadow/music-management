"""The Library tab's cards about the collection and the system, each read with its own query.

The whole-collection figures (the BPM shelf, the library size, the genre spread, the total
length, the arrival coverage) are the same for every period and every reader, so they are
read once a day per process (`CollectionFacts`, rule 5 of the snapshot rules).
"""

from __future__ import annotations

import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from services.music_manager.wrapped.cards import NO_ARRIVAL_DATE, basis, blocked, empty, gated, ok
from services.music_manager.wrapped.data import PeriodData, to_local, utc_bounds

SHELF_SQL = """
    SELECT FLOOR(bpm / 5) * 5 AS bucket, COUNT(*) AS n
    FROM library_track_effective_bpm
    WHERE confidence <> 'low'
    GROUP BY bucket
"""

LIBRARY_SQL = """
    SELECT COUNT(*) AS tracks,
           SUM(form IS NULL OR form NOT IN ('interview', 'preview')) AS music,
           COALESCE(SUM(duration_secs), 0) AS secs,
           COUNT(arrived_at) AS arrived
    FROM library_tracks
"""

GENRE_SPREAD_SQL = """
    SELECT rg.name, COUNT(*) AS tracks
    FROM library_track_genres tg
    JOIN rules_genres rg ON rg.id = tg.genre_id AND rg.state <> 'black'
    GROUP BY rg.id, rg.name
    ORDER BY tracks DESC, rg.name
    LIMIT 10
"""


@dataclass
class CollectionFacts:
    """Whole-collection figures, the same for every period."""

    shelf: dict[int, int] = field(default_factory=dict)
    tracks: int = 0
    music: int = 0
    secs: float = 0.0
    arrived: int = 0
    genres: list[dict] = field(default_factory=list)


_facts_lock = threading.Lock()
_facts_cache: dict[date, CollectionFacts] = {}


def read_collection_facts(cursor) -> CollectionFacts:
    """Read the whole-collection figures: two index scans and one pass over library_tracks."""
    facts = CollectionFacts()
    cursor.execute(SHELF_SQL)
    facts.shelf = {int(row['bucket']): int(row['n']) for row in cursor.fetchall() or [] if row['bucket'] is not None}
    cursor.execute(LIBRARY_SQL)
    row = cursor.fetchone() or {}
    facts.tracks = int(row.get('tracks') or 0)
    facts.music = int(row.get('music') or 0)
    facts.secs = float(row.get('secs') or 0)
    facts.arrived = int(row.get('arrived') or 0)
    cursor.execute(GENRE_SPREAD_SQL)
    facts.genres = [{'genre': r['name'], 'tracks': int(r['tracks'])} for r in cursor.fetchall() or []]
    return facts


def collection_facts(cursor, today: date | None = None) -> CollectionFacts:
    """The figures of today, read on the first call of the day and kept in this process."""
    today = today or datetime.now(UTC).date()
    with _facts_lock:
        cached = _facts_cache.get(today)
        if cached is not None:
            return cached
    facts = read_collection_facts(cursor)
    with _facts_lock:
        _facts_cache.clear()
        _facts_cache[today] = facts
    return facts


def _whole_years(data: PeriodData) -> tuple[int, int] | None:
    start, end = data.date_from, data.date_to
    if start.month == 1 and start.day == 1 and end.month == 12 and end.day == 31:
        return start.year, end.year
    return None


def release_condition(data: PeriodData) -> tuple[str, list]:
    """A WHERE fragment on `t` for tracks released in the period: by year, or by day in a custom range."""
    years = _whole_years(data)
    if years:
        return "t.release_date REGEXP '^[0-9]{4}' AND LEFT(t.release_date, 4) BETWEEN %s AND %s", [
            str(years[0]),
            str(years[1]),
        ]
    return "CHAR_LENGTH(t.release_date) = 10 AND t.release_date BETWEEN %s AND %s", [
        data.date_from.isoformat(),
        data.date_to.isoformat(),
    ]


RELEASES_COUNT_SQL = 'SELECT COUNT(*) AS tracks FROM library_tracks t WHERE {cond}'

RELEASES_LABELS_SQL = """
    SELECT lb.id AS label_id, lb.name, COUNT(DISTINCT x.track_id) AS tracks
    FROM (
        SELECT tl.track_id, tl.label_id
        FROM library_track_labels tl JOIN library_tracks t ON t.id = tl.track_id
        WHERE {cond}
        UNION
        SELECT tc.track_id, c.label_id
        FROM library_track_channels tc
        JOIN channels c ON c.id = tc.channel_id
        JOIN library_tracks t ON t.id = tc.track_id
        WHERE c.label_id IS NOT NULL AND {cond}
    ) x
    JOIN library_labels lb ON lb.id = x.label_id
    GROUP BY lb.id, lb.name
    ORDER BY tracks DESC, lb.name
    LIMIT 5
"""


def card_releases_of_year(cursor, data: PeriodData) -> dict:
    """Tracks in the collection released in the period, and the labels that released most of them."""
    cond, params = release_condition(data)
    cursor.execute(RELEASES_COUNT_SQL.replace('{cond}', cond), tuple(params))
    tracks = int((cursor.fetchone() or {}).get('tracks') or 0)
    if not tracks:
        return empty('releases_of_year')
    cursor.execute(RELEASES_LABELS_SQL.replace('{cond}', cond), (*params, *params))
    labels = [
        {'label_id': r['label_id'], 'label': r['name'], 'tracks': int(r['tracks'])} for r in cursor.fetchall() or []
    ]
    return ok('releases_of_year', {'tracks': tracks, 'labels': labels})


# The archives store added_at as a UTC DATETIME, like listened_at. Bucketed per UTC hour in the
# database and moved to the server zone in Python, as the listening clock does.
DOWNLOADS_SQL = """
    SELECT platform, slot, COUNT(*) AS n FROM (
        SELECT 'soundcloud' AS platform, DATE_FORMAT(added_at, '%%Y-%%m-%%d %%H') AS slot
        FROM downloads_soundcloud_archive WHERE added_at >= %s AND added_at < %s
        UNION ALL
        SELECT 'youtube' AS platform, DATE_FORMAT(added_at, '%%Y-%%m-%%d %%H') AS slot
        FROM downloads_youtube_archive WHERE added_at >= %s AND added_at < %s
    ) d
    GROUP BY platform, slot
"""

DOWNLOADS_TOP_SQL = """
    SELECT platform, account, n FROM (
        SELECT 'soundcloud' AS platform, account, COUNT(*) AS n
        FROM downloads_soundcloud_archive WHERE added_at >= %s AND added_at < %s GROUP BY account
        UNION ALL
        SELECT 'youtube' AS platform, account, COUNT(*) AS n
        FROM downloads_youtube_archive WHERE added_at >= %s AND added_at < %s GROUP BY account
    ) d
    ORDER BY n DESC, account
    LIMIT 1
"""

DOWNLOADS_UNDATED_SQL = """
    SELECT (SELECT COUNT(*) FROM downloads_soundcloud_archive WHERE added_at IS NULL)
         + (SELECT COUNT(*) FROM downloads_youtube_archive WHERE added_at IS NULL) AS undated
"""


def card_downloads(cursor, data: PeriodData) -> dict:
    """Downloads per local month and platform, and the followed channel that delivered most."""
    start, end = utc_bounds(data.scope)
    bounds = (start, end, start, end)
    cursor.execute(DOWNLOADS_SQL, bounds)
    months: dict[str, dict] = {}
    total = 0
    for row in cursor.fetchall() or []:
        if not row['slot']:
            continue
        moment = to_local(datetime.strptime(row['slot'], '%Y-%m-%d %H'), data.scope)
        key = moment.strftime('%Y-%m')
        entry = months.setdefault(key, {'month': key, 'soundcloud': 0, 'youtube': 0})
        entry[row['platform']] += int(row['n'])
        total += int(row['n'])
    if not total:
        return empty('downloads')
    cursor.execute(DOWNLOADS_TOP_SQL, bounds)
    top = cursor.fetchone()
    cursor.execute(DOWNLOADS_UNDATED_SQL)
    undated = int((cursor.fetchone() or {}).get('undated') or 0)
    return ok(
        'downloads',
        {
            'total': total,
            'months': [months[k] for k in sorted(months)],
            'top_channel': {'platform': top['platform'], 'channel': top['account'], 'downloads': int(top['n'])}
            if top
            else None,
            'undated': undated,
        },
        basis(total, total + undated, 'downloads'),
    )


GROWTH_SQL = """
    SELECT COALESCE(arrived_source, 'unknown') AS source, COUNT(*) AS n
    FROM library_tracks
    WHERE arrived_at >= %s AND arrived_at < %s
    GROUP BY source
"""


def card_growth(cursor, data: PeriodData, facts: CollectionFacts) -> dict:
    """Tracks that arrived in the period, by the way they came in (decision 3)."""
    if not facts.arrived:
        return blocked('growth', NO_ARRIVAL_DATE)
    cursor.execute(GROWTH_SQL, utc_bounds(data.scope))
    sources = sorted(
        ({'source': r['source'], 'tracks': int(r['n'])} for r in cursor.fetchall() or []),
        key=lambda e: (-e['tracks'], e['source']),
    )
    total = sum(e['tracks'] for e in sources)
    return gated(
        'growth',
        total,
        1,
        lambda: {'tracks': total, 'sources': sources, 'unknown_arrival': facts.tracks - facts.arrived},
        basis(facts.arrived, facts.tracks, 'tracks'),
    )


EDITIONS_SQL = """
    SELECT title, performance_date
    FROM library_tracks
    WHERE form = 'liveset' AND performance_date >= %s AND performance_date <= %s
"""


def card_festival_editions(cursor, data: PeriodData, festivals) -> dict:
    """Live sets in the collection played at an event in the period, and the festivals they name."""
    cursor.execute(EDITIONS_SQL, (data.date_from.isoformat(), data.date_to.isoformat()))
    rows = cursor.fetchall() or []
    counts: Counter = Counter()
    for row in rows:
        for match in festivals.get_all(row.get('title') or ''):
            counts[match['festival']] += 1
    top = sorted(counts, key=lambda f: (-counts[f], f))[:5]
    return gated(
        'festival_editions',
        len(rows),
        1,
        lambda: {'sets': len(rows), 'festivals': [{'festival': f, 'sets': counts[f]} for f in top]},
    )


def card_shelf(facts: CollectionFacts) -> dict:
    """The collection's BPM curve and its genre spread."""
    shelf_total = sum(facts.shelf.values())
    return gated(
        'shelf',
        shelf_total,
        1,
        lambda: {
            'buckets': [{'bpm': b, 'tracks': facts.shelf[b]} for b in sorted(facts.shelf)],
            'genres': facts.genres,
        },
        basis(shelf_total, facts.tracks, 'tracks'),
    )


def card_start_now(facts: CollectionFacts, now: datetime) -> dict:
    """The total length of the collection, and when you would finish it if you started now."""
    return gated(
        'start_now',
        int(facts.secs),
        1,
        lambda: {
            'total_secs': round(facts.secs),
            'finish': (now + timedelta(seconds=facts.secs)).date().isoformat(),
        },
    )


def card_unplayed(data: PeriodData, facts: CollectionFacts) -> dict:
    """How much of the collection nobody played in the period."""
    played = len({listen.track_id for listen in data.linked})
    unplayed = max(facts.music - played, 0)
    return gated(
        'unplayed',
        facts.music,
        1,
        lambda: {'unplayed': unplayed, 'library': facts.music, 'share': round(unplayed / facts.music, 6)},
    )


SYSTEM_SQL = """
    SELECT
      (SELECT COUNT(*) FROM library_track_bpm WHERE status = 'ok' AND analyzed_at >= %s AND analyzed_at < %s)
        AS bpm_measured,
      (SELECT COUNT(*) FROM news_bulletins WHERE created_at >= %s AND created_at < %s) AS bulletins,
      (SELECT COUNT(*) FROM rating_tracks WHERE updated_at >= %s AND updated_at < %s) AS ratings,
      (SELECT COUNT(*) FROM events WHERE level = 'CRITICAL' AND created_at >= %s AND created_at < %s) AS criticals
"""


def card_system(cursor, data: PeriodData) -> dict:
    """What MuMa itself did: BPM measurements, news bulletins, ratings, critical alerts."""
    start, end = utc_bounds(data.scope)
    cursor.execute(SYSTEM_SQL, (start, end) * 4)
    row = cursor.fetchone() or {}
    values = {key: int(row.get(key) or 0) for key in ('bpm_measured', 'bulletins', 'ratings', 'criticals')}
    return gated('system', sum(values.values()), 1, lambda: values)
