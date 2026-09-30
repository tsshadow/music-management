import hashlib
import json
import logging
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from services.common.config_store import ConfigStore as Settings
from services.common.Helpers.ProcessedFilesHelper import ProcessedFilesHelper
from services.music_manager.bpm.effective import EffectiveBpm, resolve_row
from services.music_manager.bpm.index import INPUTS_SQL
from services.music_manager.database import get_db_connection
from services.music_manager.genre_tint import genre_tint
from services.music_manager.library_paths import candidate_paths
from services.music_manager.routers.analytics_filters import (
    EFFECTIVE_BPM_APPROXIMATE_SQL,
    EFFECTIVE_BPM_SQL,
    FROM_CLAUSE,
    LibraryFilter,
    build_filter,
    parse_filter,
)
from services.music_manager.routers.bpm import reliable_confidence
from services.music_manager.routers.users import verify_api_key

router = APIRouter(tags=['library'])
settings = Settings()

# Sort keys the track table offers, mapped to SQL. The value is interpolated into the query, so a
# caller's sort parameter may only ever select a key here, never contribute text.
#
# Each key has two spellings of the same order: the first for the inner query that picks the
# page (over the joined tables), the second for the outer one that re-sorts that page (over the
# page's own columns, `page.*`, and `t`). `{d}` is the direction.
#
# A NULL release date and a missing BPM sort last in both directions: "unknown" is not older
# than 1970 or slower than 40 BPM, it is absent. The BPM sort breaks ties on the id: thousands
# of tracks share 150.00, and without a tie-break a page boundary between them is arbitrary, so
# paging could show a track twice and skip another.
_SORTS = {
    'created': ('t.created_at {d}', 't.created_at {d}'),
    'release': ('af.release_date IS NULL, af.release_date {d}', 'page.release_date IS NULL, page.release_date {d}'),
    'title': ('t.title {d}', 't.title {d}'),
    'bpm': (
        f'{EFFECTIVE_BPM_SQL} IS NULL, {EFFECTIVE_BPM_SQL} {{d}}, t.id {{d}}',
        'page.bpm IS NULL, page.bpm {d}, page.id {d}',
    ),
}


def _order_by(sort: str, direction: str, outer: bool = False) -> str:
    """The ORDER BY body for a requested sort, falling back to the default for anything unknown."""
    inner_order, outer_order = _SORTS.get(sort, _SORTS['created'])
    return (outer_order if outer else inner_order).format(d='ASC' if direction == 'asc' else 'DESC')


# The largest page either track list serves. The frontend asks for 100; anything
# above this is a request to walk the library in one response, which is what the
# uncapped `limit` allowed.
MAX_PAGE_SIZE = 500


@router.get('/tracks')
def get_tracks(
    q: str = '',
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    _auth: dict = Depends(verify_api_key),
):
    """Newest-first track list with a free-text search over title, artist and label.

    `page` starts at 1 and `limit` is capped at MAX_PAGE_SIZE: page 0 produced a
    negative OFFSET, which MariaDB rejects with a 500. The SoundCloud and YouTube
    source URLs are no longer part of each row. They were two correlated
    `filename LIKE '%<basename>%'` scans of the download archives per track --
    unindexable over TEXT columns -- and no client ever read them; the redownload
    endpoint resolves a track's source itself.
    """
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    offset = (page - 1) * limit
    try:
        with conn.cursor() as cursor:
            # Plain literals, no interpolation: both statements take the search three times.
            query = """
                SELECT
                    t.id, t.title, a.name AS artist, t.display_artist,
                    (SELECT l.name FROM library_labels l
                     JOIN library_track_labels tl ON l.id = tl.label_id
                     WHERE tl.track_id = t.id LIMIT 1) AS label,
                    (SELECT GROUP_CONCAT(g.name SEPARATOR ', ') FROM rules_genres g
                     JOIN library_track_genres tg ON g.id = tg.genre_id
                     WHERE tg.track_id = t.id) AS genre,
                    (SELECT mf.file_path FROM library_media_files mf WHERE mf.track_id = t.id LIMIT 1) AS file_path,
                    ml.ml_genre,
                    eb.bpm AS bpm,
                    eb.approximate AS bpm_approximate,
                    CAST(t.created_at AS CHAR) AS created_at
                FROM library_tracks t
                LEFT JOIN library_artists a ON t.primary_artist_id = a.id
                LEFT JOIN library_track_ml_labels ml ON t.track_uid = ml.track_id
                LEFT JOIN library_track_effective_bpm eb ON eb.track_id = t.id
                WHERE t.title LIKE %s OR a.name LIKE %s OR
                      EXISTS (SELECT 1 FROM library_track_labels tl
                              JOIN library_labels l ON tl.label_id = l.id
                              WHERE tl.track_id = t.id AND l.name LIKE %s)
                ORDER BY t.created_at DESC
                LIMIT %s OFFSET %s
            """
            search_pattern = f'%{q}%'
            cursor.execute(query, (search_pattern, search_pattern, search_pattern, limit, offset))
            tracks = cursor.fetchall()
            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM library_tracks t
                LEFT JOIN library_artists a ON t.primary_artist_id = a.id
                WHERE t.title LIKE %s OR a.name LIKE %s OR
                      EXISTS (SELECT 1 FROM library_track_labels tl
                              JOIN library_labels l ON tl.label_id = l.id
                              WHERE tl.track_id = t.id AND l.name LIKE %s)
                """,
                (search_pattern, search_pattern, search_pattern),
            )
            total = cursor.fetchone()['total']
            return {'tracks': tracks, 'total': total, 'page': page, 'limit': limit}
    finally:
        conn.close()


@router.get('/advanced')
def get_advanced_library(
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=MAX_PAGE_SIZE),
    sort: str = 'created',
    direction: str = 'desc',
    f: LibraryFilter = Depends(parse_filter),
    _auth: dict = Depends(verify_api_key),
):
    """Filtered track list for the library browser.

    The previous version selected musical_key, energy, danceability, valence and
    popularity. None of those columns exist in production -- db_init.py lists them
    in a CREATE TABLE IF NOT EXISTS that is a no-op against the existing table --
    so every request failed with "Unknown column 'af.musical_key'". They are gone
    rather than added, because nothing writes them.

    Paging is bounded the same way as /tracks: `page` from 1, `limit` up to
    MAX_PAGE_SIZE.

    Two steps in one statement: the inner query filters, sorts and pages over the joined
    tables and carries only narrow columns; the outer one adds the per-track subqueries
    (label, genres, file) for the page alone. With those subqueries in the sorting query
    MariaDB evaluated them for every track before the sort -- the BPM sort took 7.5 s over
    the 328k tracks on production; paged first it takes about one (issue #141).

    `bpm` is the effective BPM (analytics_filters.EFFECTIVE_BPM_SQL), with `bpm_approximate`
    set when it is not a measurement and `bpm_source` saying where it came from (`manual` when
    set by hand); the BPM sort puts tracks without one last.
    """
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')

    offset = (page - 1) * limit
    where, params = build_filter(f)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    page.id, t.title, page.artist, t.display_artist, t.duration_secs,
                    (SELECT l.name FROM library_labels l
                     JOIN library_track_labels tl ON l.id = tl.label_id
                     WHERE tl.track_id = t.id LIMIT 1) AS label,
                    (SELECT GROUP_CONCAT(rg.name ORDER BY rg.name SEPARATOR ',')
                     FROM rules_genres rg
                     JOIN library_track_genres tg ON rg.id = tg.genre_id
                     WHERE tg.track_id = t.id AND rg.state <> 'black') AS genres,
                    (SELECT mf.file_path FROM library_media_files mf
                     WHERE mf.track_id = t.id LIMIT 1) AS file_path,
                    page.bpm,
                    page.bpm_approximate,
                    page.bpm_source,
                    page.release_year,
                    page.release_date,
                    CAST(t.created_at AS CHAR) AS created_at
                FROM (
                    SELECT t.id, a.name AS artist,
                           {EFFECTIVE_BPM_SQL} AS bpm,
                           {EFFECTIVE_BPM_APPROXIMATE_SQL} AS bpm_approximate,
                           eb.source AS bpm_source,
                           af.release_year, af.release_date
                    {FROM_CLAUSE}
                    WHERE {where}
                    ORDER BY {_order_by(sort, direction)}
                    LIMIT %s OFFSET %s
                ) page
                JOIN library_tracks t ON t.id = page.id
                ORDER BY {_order_by(sort, direction, outer=True)}
            """,
                (*params, limit, offset),
            )
            tracks = cursor.fetchall()

            for track in tracks:
                raw = track.get('genres')
                track['genres'] = [g for g in (raw or '').split(',') if g]

            cursor.execute(f'SELECT COUNT(DISTINCT t.id) AS total {FROM_CLAUSE} WHERE {where}', tuple(params))
            total = cursor.fetchone()['total']

            return {'tracks': tracks, 'total': total, 'page': page, 'limit': limit}
    finally:
        conn.close()


@router.get('/genres')
def get_library_genres(_auth: dict = Depends(verify_api_key)):
    """Genres tracks actually carry, with counts.

    This returned [] for as long as it existed: it joined rules_genres against
    library_track_genres, which had no rows until the scanner started writing it.
    Unknown genres are included so the sidebar can group them as awaiting
    curation rather than hide tracks that do have a genre in their tag.

    Each row carries the colour its tile is drawn in. Both the web UI and the
    mobile app render a genre as a coloured tile, and deriving that colour here
    is what keeps them from each owning a table that drifts.
    """
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT g.name AS genre, g.state AS state, COUNT(DISTINCT tg.track_id) AS count
                FROM rules_genres g
                JOIN library_track_genres tg ON g.id = tg.genre_id
                WHERE g.state <> 'black'
                GROUP BY g.id
                ORDER BY count DESC, g.name
            """)
            rows = cursor.fetchall()
            for row in rows:
                row['tint'] = genre_tint(row.get('genre'))
            return rows
    finally:
        conn.close()


@router.post('/tracks/{track_id}/rerun-parse')
def rerun_parse(track_id: int, _auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT file_path FROM library_media_files WHERE track_id = %s', (track_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail='Track file not found')
            filepath = row['file_path']
            helper = ProcessedFilesHelper()
            helper.mark_for_rescan(filepath, reason='rerun_parse')
            try:
                from services.music_manager.routers.scanner import scanner_manager
                from services.music_manager.routers.tagger import tagger_manager

                tagger_manager.tag_single(filepath)
                logging.info(f'Successfully executed immediate tagger rescan for {filepath}')
                scanner_manager.scan_single(filepath)
                logging.info(f'Successfully executed immediate scanner for {filepath}')
            except Exception as e:
                logging.warning(f'Could not execute immediate rescan/scan: {e}')
            return {'status': 'ok', 'message': f'Track {track_id} marked for rescan and immediate trigger attempted'}
    finally:
        conn.close()


@router.post('/tracks/rerun-parse-path')
def rerun_parse_path(path: str = Query(...), _auth: dict = Depends(verify_api_key)):
    """
    Triggers a re-tagging and re-scanning of a file based on its absolute path.
    Useful for external integrations like LMS.
    """
    filepath = path
    helper = ProcessedFilesHelper()
    helper.mark_for_rescan(filepath, reason='rerun_parse')
    try:
        from services.music_manager.routers.scanner import scanner_manager
        from services.music_manager.routers.tagger import tagger_manager

        tagger_manager.tag_single(filepath)
        logging.info(f'Successfully executed immediate tagger rescan for {filepath}')
        scanner_manager.scan_single(filepath)
        logging.info(f'Successfully executed immediate scanner for {filepath}')
    except Exception as e:
        logging.warning(f'Could not execute immediate rescan/scan for path {filepath}: {e}')
    return {'status': 'ok', 'message': f'Track at {filepath} marked for rescan and immediate trigger attempted'}


def _ingested_tags(cursor, file_path_hash: str) -> tuple[dict | None, dict]:
    """The ingestion record for one file and the tag set it carries, parsed.

    A record whose `tags_json` does not parse still counts as a record -- its `source`
    is real -- but contributes no tags rather than failing the whole answer.
    """
    cursor.execute(
        'SELECT source, tags_json, CAST(recorded_at AS CHAR) AS recorded_at '
        'FROM library_ingestion_records WHERE file_path_hash = %s LIMIT 1',
        (file_path_hash,),
    )
    ingestion = cursor.fetchone()
    if not ingestion or not ingestion.get('tags_json'):
        return ingestion, {}
    try:
        parsed = json.loads(ingestion['tags_json'])
    except (TypeError, ValueError):
        logging.warning('Unreadable tags_json on ingestion record %s', file_path_hash)
        return ingestion, {}
    return ingestion, parsed if isinstance(parsed, dict) else {}


def _archive_source(cursor, spellings: list[str]) -> tuple[str | None, str | None]:
    """The URL a file was downloaded from and which platform's archive had it.

    Matches the whole filename, not a substring: the archive stores the absolute path,
    and an equality over the candidate spellings finds the same row without the
    substring false positives. `/redownload` resolves its source the same way first
    (`_redownload_source`).
    """
    placeholders = ', '.join(['%s'] * len(spellings))
    for platform, table in (
        ('soundcloud', 'downloads_soundcloud_archive'),
        ('youtube', 'downloads_youtube_archive'),
    ):
        cursor.execute(f'SELECT url FROM {table} WHERE filename IN ({placeholders}) LIMIT 1', tuple(spellings))
        row = cursor.fetchone()
        if row and row.get('url'):
            return row['url'], platform
    return None, None


#: One track's BPM inputs, in the shape `effective.resolve_row` reads.
_TRACK_BPM_INPUTS_SQL = INPUTS_SQL.format(where='\n      AND t.id = %s')


def _effective_bpm(cursor, track_id: int) -> EffectiveBpm | None:
    """The track's effective BPM, resolved now by the one rule (bpm/effective.py), or None.

    Resolved live rather than read from library_track_effective_bpm: this is one track, the
    inputs are three primary-key probes, and the details sheet then shows a measurement the
    moment it is stored instead of after the next sync.
    """
    cursor.execute(_TRACK_BPM_INPUTS_SQL, (track_id,))
    row = cursor.fetchone()
    return resolve_row(row, reliable_confidence()) if row else None


def _bpm_fields(found: EffectiveBpm | None) -> dict:
    """The BPM fields of a track details answer; all None without a BPM."""
    if found is None:
        return {'bpm': None, 'bpm_source': None, 'bpm_confidence': None, 'bpm_approximate': None, 'bpm_folded': None}
    return {
        'bpm': found.bpm,
        'bpm_source': found.source,
        'bpm_confidence': found.confidence,
        'bpm_approximate': found.approximate,
        'bpm_folded': found.folded,
    }


def _track_facts(cursor, media: dict) -> tuple[list[dict], EffectiveBpm | None, str | None]:
    """Channels, effective BPM and ML genre for the track behind a media file; empty for a file without one.

    A channel carries the label or artist it was curated as, when it has one: that is what makes
    the channel row in the details sheet a place to go rather than a name to read.
    """
    channels: list[dict] = []
    bpm = None
    ml_genre = None
    if media['track_id'] is not None:
        cursor.execute(
            """
            SELECT c.platform, c.name, l.name AS label, a.name AS artist
            FROM library_track_channels tc
            JOIN channels c ON c.id = tc.channel_id
            LEFT JOIN library_labels l ON l.id = c.label_id
            LEFT JOIN library_artists a ON a.id = c.artist_id
            WHERE tc.track_id = %s
            ORDER BY c.platform, c.name
            """,
            (media['track_id'],),
        )
        channels = [
            {'platform': row['platform'], 'name': row['name'], 'label': row.get('label'), 'artist': row.get('artist')}
            for row in cursor.fetchall()
        ]
        bpm = _effective_bpm(cursor, media['track_id'])
    if media['track_uid']:
        cursor.execute(
            'SELECT ml_genre FROM library_track_ml_labels WHERE track_id = %s LIMIT 1', (media['track_uid'],)
        )
        row = cursor.fetchone()
        ml_genre = row['ml_genre'] if row else None
    return channels, bpm, ml_genre


@router.get('/tracks/by-path')
def get_track_by_path(path: str = Query(...), _auth: dict = Depends(verify_api_key)):
    """What MuMa knows about one file that LMS does not: the channel it came from, the
    source URL, the raw tag set the tagger wrote, and the effective BPM (bpm/effective.py:
    a measurement first, else the file tag or the old analyzer's tempo folded into the genre's
    band) with where it came from and whether it is approximate.

    Keyed on the path rather than a track id because the caller is the player, which holds
    the Subsonic song object and so the LMS-relative path -- it has no MuMa track id. Every
    spelling of that path is tried (`candidate_paths`), the same way the rating webhook joins.

    A file MuMa has not scanned is a 404, not an empty body: the sheet distinguishes "MuMa
    has nothing on this" from "MuMa could not be asked" by that.
    """
    spellings = candidate_paths(path)
    hashes = [hashlib.sha256(spelling.encode('utf-8')).hexdigest() for spelling in spellings]
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail='Database connection failed')
    try:
        with conn.cursor() as cursor:
            placeholders = ', '.join(['%s'] * len(hashes))
            cursor.execute(
                f"""
                SELECT mf.file_path, mf.file_path_hash, mf.track_id, t.track_uid,
                       CAST(t.created_at AS CHAR) AS created_at
                FROM library_media_files mf
                LEFT JOIN library_tracks t ON t.id = mf.track_id
                WHERE mf.file_path_hash IN ({placeholders})
                LIMIT 1
                """,
                tuple(hashes),
            )
            media = cursor.fetchone()
            if not media:
                raise HTTPException(status_code=404, detail='File not known to MuMa')

            channels, bpm, ml_genre = _track_facts(cursor, media)
            ingestion, tags = _ingested_tags(cursor, media['file_path_hash'])
            source_url, source_platform = _archive_source(cursor, spellings)
            return {
                'track_id': media['track_id'],
                'file_path': media['file_path'],
                'added_at': media['created_at'],
                'source': ingestion['source'] if ingestion else None,
                'recorded_at': ingestion['recorded_at'] if ingestion else None,
                'channels': channels,
                'source_url': source_url,
                'source_platform': source_platform,
                **_bpm_fields(bpm),
                'ml_genre': ml_genre,
                'tags': tags,
            }
    finally:
        conn.close()


def _escape_like(text: str) -> str:
    """`text` as a literal inside a LIKE pattern: `%` and `_` are wildcards there."""
    return text.replace('\\', '\\\\').replace('%', r'\%').replace('_', r'\_')


class AmbiguousSource(Exception):
    """More than one archived download could be the file, so none is picked."""


def _redownload_source(cursor, filepath: str) -> tuple[str | None, str | None]:
    """The URL a library file was downloaded from, and which platform's archive had it.

    Exact first: the stored path -- `filename` on the SoundCloud archive, `path` on the
    YouTube one -- against every spelling of the library path. This used to be
    `filename LIKE '%<name>%' LIMIT 1`, with the name's own `_` and `%` left as
    wildcards: `Intro.mp3` matched `DJ Intro.mp3`, and whichever row came first was
    downloaded over the file.

    Only when no stored path matches, the file name alone, exactly: equal to a bare
    name, or the last component of a stored path. A candidate whose stored path puts
    it in another folder is not this file, and if more than one source URL is still
    left the answer is `AmbiguousSource` rather than a guess.
    """
    spellings = candidate_paths(filepath)
    placeholders = ', '.join(['%s'] * len(spellings))
    for platform, table, path_column in (
        ('soundcloud', 'downloads_soundcloud_archive', 'filename'),
        ('youtube', 'downloads_youtube_archive', 'path'),
    ):
        cursor.execute(
            f'SELECT url, {path_column} AS stored FROM {table} '
            f'WHERE {path_column} IN ({placeholders}) AND url IS NOT NULL LIMIT 20',
            tuple(spellings),
        )
        # IN compares under the archive's case-insensitive collation; the path has to be
        # this one exactly, not a file whose name differs only in case.
        for row in cursor.fetchall() or []:
            if row.get('stored') in spellings and row.get('url'):
                return row['url'], platform

    name = os.path.basename(filepath)
    folder = os.path.basename(os.path.dirname(filepath))
    suffix = f'%/{_escape_like(name)}'
    candidates: dict[str, str] = {}
    for platform, query, args in (
        (
            'soundcloud',
            'SELECT url, filename AS stored FROM downloads_soundcloud_archive '
            'WHERE (filename = %s OR filename LIKE %s) AND url IS NOT NULL LIMIT 20',
            (name, suffix),
        ),
        (
            'youtube',
            "SELECT url, COALESCE(NULLIF(path, ''), filename) AS stored FROM downloads_youtube_archive "
            'WHERE filename = %s AND url IS NOT NULL LIMIT 20',
            (name,),
        ),
    ):
        cursor.execute(query, args)
        for row in cursor.fetchall() or []:
            stored = row.get('stored') or ''
            # The comparisons above run under the archive's case-insensitive collation;
            # this one is exact.
            if os.path.basename(stored) != name:
                continue
            stored_folder = os.path.basename(os.path.dirname(stored))
            if stored_folder and stored_folder != folder:
                continue
            candidates.setdefault(row['url'], platform)
    if len(candidates) > 1:
        raise AmbiguousSource(f'{len(candidates)} archived downloads are called {name}')
    if candidates:
        url, platform = next(iter(candidates.items()))
        return url, platform
    return None, None


@router.post('/tracks/{track_id}/redownload')
def redownload_track(track_id: int, background_tasks: BackgroundTasks, _auth: dict = Depends(verify_api_key)):
    """Fetch a track again from where it was downloaded and put it in place of the file.

    400 when no archive knows the file, 409 when the file name is all there is to go on
    and more than one archived download carries it.
    """
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT file_path FROM library_media_files WHERE track_id = %s', (track_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail='Track file not found')
            filepath = row['file_path']
            try:
                source_url, source_type = _redownload_source(cursor, filepath)
            except AmbiguousSource as exc:
                raise HTTPException(
                    status_code=409, detail=f'Several archived downloads could be this file ({exc}); not guessing'
                ) from exc
            if not source_url:
                raise HTTPException(status_code=400, detail='Could not find source URL in archive for redownload')
            background_tasks.add_task(run_redownload_task, source_url, source_type, filepath)
            return {'status': 'ok', 'message': f'Redownload started for {source_type} track: {source_url}'}
    finally:
        conn.close()


def run_redownload_task(url: str, source_type: str, target: str | None = None):
    """Download `url` again and, when `target` is given, replace that library file with it.

    The file is replaced atomically (see services/downloader/redownload.py), tagged, and
    its tagger queue row re-marked with the new mtime by the downloader's own
    post-processor. The row is also queued here for a retag: should the post-processor
    not reach its bookkeeping, the next round still reads the new file, and a row parked
    after repeated failures -- a damaged file is the usual reason to redownload -- starts
    its failure count over.
    """
    logging.info(f'Starting redownload task for {source_type}: {url}')
    try:
        if source_type == 'soundcloud':
            from services.downloader.soundcloud.soundcloud import SoundcloudDownloader

            soundcloud = SoundcloudDownloader(break_on_existing=False)
            soundcloud.redownload_mode = True
            ydl_opts = soundcloud._prepare_ydl_opts('', break_on_existing_arg=False, redownload=True)
            soundcloud.download_url(url, ydl_opts, replace=target)
        elif source_type == 'youtube':
            from services.downloader.youtube.youtube import YoutubeDownloader

            youtube = YoutubeDownloader(break_on_existing=False)
            youtube.download_link(url, breakOnExisting=False, redownload=True, replace=target)
        else:
            return
        if target and os.path.exists(target):
            ProcessedFilesHelper().mark_for_rescan(target, reason='redownload')
        logging.info(f'Redownload task completed for {url}')
    except Exception as e:
        logging.error(f'Redownload task failed for {url}: {e}', exc_info=True)
