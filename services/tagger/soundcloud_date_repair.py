"""Queue the SoundCloud files whose DATE was cut to the year, so the tagger restores it.

From 0.72.0 (2026-09-22) until bug report 088 was fixed, every SoundCloud mp3 arrived with
only the year as its date: EmbedThumbnail rewrote the file as ID3v2.3 and ffmpeg dropped
month and day from yt-dlp's undelimited `upload_date`. The full date was never lost -- the
archive row keeps the info dict (`downloads_soundcloud_archive.info_json`), and
`SoundcloudSong` now completes a year-only DATE from that dict's `upload_date` when the
years agree. So a retag is the whole repair; this only decides which files get one.

Candidates are the archive rows added since the cutoff with a full `upload_date`. Each
file's DATE is read from disk, not from `library_ingestion_records`: that record is written
once and never updated, so it would still say "year only" after the repair. Reading the file
makes this re-runnable -- a repaired file reads as a full date and is left out the next time.

    python -m services.tagger.soundcloud_date_repair            # dry run: counts, writes nothing
    python -m services.tagger.soundcloud_date_repair --apply    # queue with reason soundcloud_full_date

Run inside the music-manager container, which has both the database and /mnt/music. The
five-minute tagger round does the writing; nothing is retagged here.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from services.tagger.Song.ReleaseDate import completed_date

#: The rescan reason the queued rows carry, so the queue can be watched and undone per reason.
REASON = 'soundcloud_full_date'

#: The first year-only arrival on production was 2026-09-22 10:24, 37 minutes after the first
#: record written by 0.72.0. An hour earlier leaves room for the deploy itself.
DEFAULT_SINCE = '2026-09-22 09:00:00'

#: Queued in chunks, like ProcessedFilesHelper.mark_paths_for_rescan.
BATCH_SIZE = 500

CANDIDATES_SQL = (
    "SELECT filename, JSON_VALUE(info_json, '$.upload_date') AS upload_date "
    'FROM downloads_soundcloud_archive '
    'WHERE added_at >= %s AND filename IS NOT NULL AND info_json IS NOT NULL '
    "AND JSON_VALUE(info_json, '$.upload_date') REGEXP '^[0-9]{8}$' "
    'ORDER BY id'
)

#: Upsert, not UPDATE: a file tagged straight from the download post-processor may have no
#: queue row yet. `attempts`/`last_attempt` are reset as for every retag asked for on purpose.
QUEUE_SQL = (
    'INSERT INTO tagger_processed_files (filepath, mtime, needs_rescan, rescan_reason) '
    'VALUES (%s, 0, TRUE, %s) '
    'ON DUPLICATE KEY UPDATE needs_rescan = TRUE, rescan_reason = VALUES(rescan_reason), '
    'attempts = 0, last_attempt = NULL'
)


@dataclass
class Plan:
    """What the dry run found, per verdict. Only `repair` is queued."""

    repair: list[str] = field(default_factory=list)
    full: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    other: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        """The size of each verdict, for the report."""
        return {name: len(getattr(self, name)) for name in ('repair', 'full', 'missing', 'other')}


def read_date(path: str) -> str | None:
    """The DATE on the file as the tagger reads it, '' when it has none, None when unreadable."""
    import mutagen

    try:
        audio = mutagen.File(path, easy=True)
    except Exception as exc:  # noqa: BLE001 - any unreadable file is reported, not fatal
        logging.warning('Could not read %s: %s', path, exc)
        return None
    if audio is None or audio.tags is None:
        return ''
    values = audio.tags.get('date') or ['']
    return str(values[0])


def classify(rows: Iterable[tuple[str, str]], read: Callable[[str], str | None] = read_date) -> Plan:
    """Sort each (path, upload_date) by what its file says now."""
    plan = Plan()
    for path, upload_date in rows:
        if not os.path.exists(path):
            plan.missing.append(path)
            continue
        current = read(path)
        if current is None:
            plan.missing.append(path)
        elif completed_date(current, upload_date):
            plan.repair.append(path)
        elif len(''.join(ch for ch in current if ch.isdigit())) >= 8:
            plan.full.append(path)
        else:
            # No date, or a year that disagrees with the upload date: not this defect.
            plan.other.append(path)
    return plan


def candidates(cursor, since: str) -> list[tuple[str, str]]:
    """(path, upload_date) for every archive row added since `since` with a full upload date."""
    cursor.execute(CANDIDATES_SQL, (since,))
    return [(row[0], row[1]) for row in cursor.fetchall()]


def queue(cursor, paths: list[str]) -> int:
    """Put `paths` on the tagger queue with REASON. Returns how many were handed over."""
    for start in range(0, len(paths), BATCH_SIZE):
        cursor.executemany(QUEUE_SQL, [(path, REASON) for path in paths[start : start + BATCH_SIZE]])
    return len(paths)


def run(connection, since: str, apply: bool, read: Callable[[str], str | None] = read_date) -> dict:
    """The dry run, and the queueing when `apply` is set. Returns the report."""
    with connection.cursor() as cursor:
        plan = classify(candidates(cursor, since), read)
        queued = 0
        if apply and plan.repair:
            queued = queue(cursor, plan.repair)
            connection.commit()
    return {
        'since': since,
        'applied': bool(apply),
        'reason': REASON,
        'counts': plan.counts(),
        'queued': queued,
        'repair': plan.repair,
        'missing': plan.missing,
        'other': plan.other,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; prints the report as JSON."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n', maxsplit=1)[0])
    parser.add_argument('--since', default=DEFAULT_SINCE, help='archive rows added from this moment on')
    parser.add_argument('--apply', action='store_true', help='queue the files; without it nothing is written')
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s', stream=sys.stderr)

    from services.common.Helpers.DatabaseConnector import DatabaseConnector

    with DatabaseConnector().connection() as connection:
        report = run(connection, args.since, args.apply)
    json.dump(report, sys.stdout, ensure_ascii=False, indent=1)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
