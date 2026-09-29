"""Build the "Oude hitjes" feed for one listener: gather rows, hand them to `old_hits`, shape a `Feed`.

The only module of this feed that touches a connection; the rules live in `old_hits.py` and
the SQL in `old_hits_queries.py`. The order of work (docs/designs/old-hits-feed/technical.md,
"Algorithm"):

1. The listener's ratings and listens, rolled up per song -> the songs they have touched.
2. Artist affinity from those songs; for the most liked artists, the stored external top-list
   matches and the works with many library versions -> the candidate hits.
3. The age of every candidate song (earliest date over its versions, the artist as fallback).
4. The three tiers, each in its daily-stable order.
5. Display rows for the head of each tier (the canonical version where it has a file), which
   also drops what cannot play and what the listener excluded from their profile.
6. Fill the tiers, interleave, and return the tracks with a `reason` per track.
"""

from __future__ import annotations

from datetime import datetime

from services.music_manager.feeds import clock
from services.music_manager.feeds.build import EMPTY_FUNNEL, Feed
from services.music_manager.feeds.old_hits import (
    OLD_HITS_SLUG,
    OLD_HITS_SUBTITLE,
    OLD_HITS_TITLE,
    TIERS,
    OldHitsConfig,
    Song,
    age_cutoff,
    artist_affinity,
    fill_tiers,
    interleave,
    is_old,
    reason_for,
    song_key,
    song_rating,
    tier_favourites,
    tier_hits,
    tier_worn,
)
from services.music_manager.feeds.old_hits_queries import (
    artist_dated_query,
    listens_query,
    popular_query,
    ratings_query,
    track_dates_query,
    versions_query,
    work_dates_query,
)
from services.music_manager.feeds.queries import canonical_rows_query, exclusions_query

#: How many of the listener's most liked artists tier 3 looks for hits by.
MAX_AFFINITY_ARTISTS = 300
#: Ids per `IN (...)` list.
CHUNK = 500
#: The longest track the feed plays, the same ceiling the daily mixes use.
MAX_TRACK_SECONDS = 600


def _rows(conn, sql: str, params=None) -> list[dict]:
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        return list(cursor.fetchall())


def _chunked_rows(conn, builder, ids: list, *extra) -> list[dict]:
    """`builder(chunk, *extra)` run over `ids` in chunks of `CHUNK`, rows concatenated."""
    rows: list[dict] = []
    for start in range(0, len(ids), CHUNK):
        sql, params = builder(ids[start : start + CHUNK], *extra)
        rows.extend(_rows(conn, sql, params))
    return rows


def _touched_songs(conn, username: str) -> dict[tuple, Song]:
    """Step 1: every song the listener rated or played, with the rating and play stats per song."""
    songs: dict[tuple, Song] = {}
    rating_rows = _rows(conn, *ratings_query(username))
    ratings = song_rating(rating_rows)
    for row in rating_rows:
        key = song_key(row)
        if key not in songs:
            songs[key] = Song(
                key=key,
                track_id=row['track_id'],
                artist_id=row.get('artist_id'),
                canonical_track_id=row.get('canonical_track_id'),
            )
        songs[key].rating = ratings[key]
    for row in _rows(conn, *listens_query(username)):
        key = song_key(row)
        song = songs.get(key)
        if song is None:
            song = songs[key] = Song(
                key=key,
                track_id=row['track_id'],
                artist_id=row.get('artist_id'),
                canonical_track_id=row.get('canonical_track_id'),
            )
        song.plays = int(row.get('plays') or 0)
        song.last_heard = row.get('last_heard')
    return songs


def _add_hits(conn, songs: dict[tuple, Song], artist_ids: list[int], cfg: OldHitsConfig) -> None:
    """Step 2: mark (or add) songs that are external top-list hits or have many library versions."""
    if not artist_ids:
        return
    for row in _chunked_rows(conn, popular_query, artist_ids):
        key = song_key(row)
        song = songs.get(key)
        if song is None:
            song = songs[key] = Song(
                key=key,
                track_id=row['track_id'],
                artist_id=row.get('artist_id'),
                canonical_track_id=row.get('canonical_track_id'),
            )
        position = int(row['position'])
        if song.popular_position is None or position < song.popular_position:
            song.popular_position = position
            song.popular_source = row['source']
    for row in _chunked_rows(conn, versions_query, artist_ids, cfg.min_versions):
        key = ('work', row['work_id'])
        song = songs.get(key)
        if song is None:
            song = songs[key] = Song(
                key=key,
                track_id=row['track_id'],
                artist_id=row.get('artist_id'),
                canonical_track_id=row.get('canonical_track_id'),
            )
        song.versions = int(row['versions'])


def _mark_old(conn, songs: dict[tuple, Song], cfg: OldHitsConfig, now: datetime) -> None:
    """Step 3: `song.old` for every song, from its versions' dates or, undated, its artist's."""
    cutoff = age_cutoff(clock.feed_date(now), cfg.min_age_years)
    work_ids = sorted(key[1] for key in songs if key[0] == 'work')
    track_ids = sorted(key[1] for key in songs if key[0] == 'track')
    dates: dict[tuple, tuple] = {}
    for row in _chunked_rows(conn, work_dates_query, work_ids):
        dates[('work', row['work_id'])] = (row.get('earliest_date'), row.get('earliest_year'))
    for row in _chunked_rows(conn, track_dates_query, track_ids):
        dates[('track', row['track_id'])] = (row.get('earliest_date'), row.get('earliest_year'))

    undated_artists = sorted(
        {
            song.artist_id
            for key, song in songs.items()
            if song.artist_id is not None and not any(dates.get(key, (None, None)))
        }
    )
    artist_counts: dict[int, tuple[int, int]] = {}
    for start in range(0, len(undated_artists), CHUNK):
        sql, params = artist_dated_query(undated_artists[start : start + CHUNK], cutoff)
        for row in _rows(conn, sql, params):
            artist_counts[row['artist_id']] = (int(row.get('dated') or 0), int(row.get('old') or 0))

    for key, song in songs.items():
        earliest_date, earliest_year = dates.get(key, (None, None))
        dated, old = artist_counts.get(song.artist_id, (0, 0)) if song.artist_id is not None else (0, 0)
        year = int(earliest_year) if earliest_year else None
        song.old = is_old(str(earliest_date) if earliest_date else None, year, dated, old, cutoff)


def _exclusions(conn, username: str) -> dict[str, set[str]]:
    excluded: dict[str, set[str]] = {'artist': set(), 'label': set(), 'genre': set()}
    for row in _rows(conn, *exclusions_query(username)):
        excluded.setdefault(row['entity_type'], set()).add((row['entity_name'] or '').lower())
    return excluded


def _playable(row: dict, excluded: dict[str, set[str]]) -> bool:
    """Whether a display row may go out: a sane duration and nothing the listener excluded."""
    duration = row.get('duration_secs') or 0
    if not 0 < duration < MAX_TRACK_SECONDS:
        return False
    if (row.get('artist') or '').lower() in excluded['artist']:
        return False
    if (row.get('label') or '').lower() in excluded['label']:
        return False
    return not any(genre.lower() in excluded['genre'] for genre in row.get('genres') or [])


def _attach_rows(conn, username: str, pools: list[list[Song]], budget: int, excluded) -> list[list[Song]]:
    """Step 5: the head of each pool with its display row, unplayable and excluded songs dropped.

    The canonical is what plays when it has a file; otherwise the version that qualified.
    """
    heads = [pool[:budget] for pool in pools]
    ids = sorted(
        {
            track_id
            for pool in heads
            for song in pool
            for track_id in (song.canonical_track_id, song.track_id)
            if track_id is not None
        }
    )
    rows: dict[int, dict] = {}
    for start in range(0, len(ids), CHUNK):
        sql, params = canonical_rows_query(username, ids[start : start + CHUNK])
        for row in _rows(conn, sql, params):
            rows[row['id']] = {
                **row,
                'genres': [part for part in (row.get('genres') or '').split(',') if part],
                'heard': bool(row.get('heard')),
            }
    kept_pools = []
    for pool in heads:
        kept = []
        for song in pool:
            display = (rows.get(song.canonical_track_id) if song.canonical_track_id else None) or rows.get(
                song.track_id
            )
            if display is None or not _playable(display, excluded):
                continue
            song.row = display
            kept.append(song)
        kept_pools.append(kept)
    return kept_pools


def build_old_hits(conn, username: str, now: datetime, cfg: OldHitsConfig) -> Feed:
    """The "Oude hitjes" feed for `username` on the day of `now`, `cfg.size` tracks at most."""
    feed_date = clock.feed_date(now)
    songs = _touched_songs(conn, username)
    if not songs:
        return Feed(
            slug=OLD_HITS_SLUG,
            state='not_enough_data',
            scope='user',
            tracks=[],
            funnel=dict(EMPTY_FUNNEL),
            title=OLD_HITS_TITLE,
            subtitle=OLD_HITS_SUBTITLE,
        )
    affinity = artist_affinity(list(songs.values()))
    liked = sorted(affinity, key=lambda artist: (-affinity[artist], artist))[:MAX_AFFINITY_ARTISTS]
    _add_hits(conn, songs, sorted(liked), cfg)
    _mark_old(conn, songs, cfg, now)

    everything = list(songs.values())
    pools = [
        tier_favourites(everything, cfg, now, username, feed_date),
        tier_worn(everything, cfg, now, username, feed_date),
        tier_hits(everything, {artist: affinity[artist] for artist in liked}, cfg, now, username, feed_date),
    ]
    candidates = len({song.key for pool in pools for song in pool})
    budget = max(3 * cfg.size, 300)
    pools = _attach_rows(conn, username, pools, budget, _exclusions(conn, username))
    playable = len({song.key for pool in pools for song in pool})

    picked = fill_tiers(pools, cfg.shares, cfg.size, cfg.max_per_artist)
    ordered = interleave(picked)
    tracks = [
        {
            **song.row,
            'bucket': f'{OLD_HITS_SLUG}:{TIERS[tier]}',
            'reason': reason_for(song, tier),
        }
        for song, tier in ordered
    ]
    funnel = {
        'candidates': candidates,
        'bucketed': playable,
        'allocated': len(picked),
        'capped': len(picked),
        'emitted': len(tracks),
    }
    return Feed(
        slug=OLD_HITS_SLUG,
        state='ok' if tracks else 'no_matches',
        scope='user',
        tracks=tracks,
        funnel=funnel,
        title=OLD_HITS_TITLE,
        subtitle=OLD_HITS_SUBTITLE,
    )
