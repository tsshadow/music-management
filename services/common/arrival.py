"""When a track entered the library, and by which way (docs/designs/wrapped-page/technical.md).

`library_tracks.arrived_at` is the moment the scanner first created the track's row, and
`arrived_source` the top folder its file came in through. NULL in both means "before arrival
dates were kept": the library was rebuilt in July 2026, so `created_at` says nothing about
when a file arrived, and `tools/backfill_arrival_dates.py` fills what the download archives
and the ingestion records can prove.

A retag can change a file's track_uid, which gives it a new track row. That row is not a new
arrival, so the scanner carries the arrival of the row the file left over to it
(`carry_arrival`). A track's arrival is the earliest arrival of its files, and an unknown
arrival counts as the earliest of all: a file from before the dates were kept makes the whole
track unknown.
"""

from services.common.track_form import _top_folder

SOUNDCLOUD = 'soundcloud'
YOUTUBE = 'youtube'
TELEGRAM = 'telegram'
LABEL = 'label'
IMPORT = 'import'
UNKNOWN = 'unknown'

# Top folder (lower case) to source. Every other folder under the music root is a manual
# import: import, Lidarr, Hitzone, Podcasts, Livesets and the rest on production.
_FOLDER_SOURCES = {
    'soundcloud': SOUNDCLOUD,
    'youtube': YOUTUBE,
    'telegram': TELEGRAM,
    'eps': LABEL,
}


def arrival_source(path: str | None, music_root: str | None) -> str:
    """The way a file came into the library, read from its top folder below the music root."""
    folder = _top_folder(path, music_root)
    if not folder:
        return UNKNOWN
    return _FOLDER_SOURCES.get(folder, IMPORT)


def merged_arrival(old: dict | None, new: dict | None) -> tuple:
    """The arrival a track keeps when a file moves from track OLD to track NEW.

    Each argument is a row with `arrived_at` and `arrived_source`. The earlier arrival wins, and
    an unknown arrival on either side makes the result unknown: `(None, None)`.
    """
    if not old or not new or old.get('arrived_at') is None or new.get('arrived_at') is None:
        return None, None
    earlier = old if old['arrived_at'] < new['arrived_at'] else new
    return earlier['arrived_at'], earlier.get('arrived_source')


def carry_arrival(cursor, old_track_id: int, new_track_id: int) -> None:
    """Give track NEW the arrival it has once a file moved to it from track OLD (see merged_arrival)."""
    cursor.execute(
        'SELECT id, arrived_at, arrived_source FROM library_tracks WHERE id IN (%s, %s)',
        (old_track_id, new_track_id),
    )
    rows = {row['id']: row for row in cursor.fetchall()}
    arrived_at, source = merged_arrival(rows.get(old_track_id), rows.get(new_track_id))
    cursor.execute(
        'UPDATE library_tracks SET arrived_at = %s, arrived_source = %s WHERE id = %s',
        (arrived_at, source, new_track_id),
    )
