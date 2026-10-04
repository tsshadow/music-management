"""What the grouping would do, without writing anything.

Run against the real library before the worker is ever let near it: a group of two
hundred tracks is a bug in the key, not a collection, and it has to be visible
before rows are written rather than after.

    python -m tools.song_version_report

Also reports how many library_tracks rows carry more than one media file, which
answers whether a FLAC and an MP3 of one release collapse today or whether the
duration float in track_uid splits them.
"""

from __future__ import annotations

import collections
import json
import sys

from services.music_manager.song_versions import version_kind, work_key

LARGEST_GROUPS = 25

_ROWS = '''
    SELECT t.id, t.title, t.duration_secs, t.form, a.name AS artist,
           (SELECT mf.file_path FROM library_media_files mf WHERE mf.track_id = t.id LIMIT 1) AS file_path
    FROM library_tracks t
    LEFT JOIN library_artists a ON a.id = t.primary_artist_id
'''

_MULTI_FILE = '''
    SELECT COUNT(*) AS n FROM (
        SELECT track_id FROM library_media_files
        WHERE track_id IS NOT NULL
        GROUP BY track_id HAVING COUNT(*) > 1
    ) AS multi
'''


def summarize(rows: list[dict]) -> dict:
    """Group the rows in memory and describe the result."""
    groups: dict[str, list[dict]] = collections.defaultdict(list)
    kinds: collections.Counter = collections.Counter()

    for row in rows:
        groups[work_key(row['artist'], row['title'], row['id'], row.get('duration_secs'), row.get('form'))].append(row)
        kinds[version_kind(row['title'])] += 1

    ordered = sorted(groups.items(), key=lambda item: len(item[1]), reverse=True)
    largest = [
        {
            'work_key': key,
            'size': len(members),
            'titles': [member['title'] for member in members],
        }
        for key, members in ordered[:LARGEST_GROUPS]
        if len(members) > 1
    ]

    return {
        'tracks': len(rows),
        'works': len(groups),
        'single_version_works': sum(1 for members in groups.values() if len(members) == 1),
        'largest_groups': largest,
        'kinds': dict(kinds),
    }


def main() -> int:
    from services.music_manager.database import get_db_connection

    conn = get_db_connection()
    if not conn:
        print('song-version-report: no database connection', file=sys.stderr)
        return 1
    try:
        with conn.cursor() as cursor:
            cursor.execute(_ROWS)
            rows = cursor.fetchall()
            cursor.execute(_MULTI_FILE)
            multi_file_tracks = cursor.fetchone()['n']
    finally:
        conn.close()

    report = summarize(rows)
    report['tracks_with_several_files'] = multi_file_tracks
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
