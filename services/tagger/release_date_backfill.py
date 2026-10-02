"""Find the label-tree tracks that still carry only a year, and queue the ones the date ladder can lift.

The release-date ladder (`InferReleaseDateFromNfoRule`, docs/designs/release-info-enrichment/) runs
on every retag, so a retag is the whole repair; this decides which files get one. Candidates are the
tracks muma holds without a full release date (`library_tracks.release_date` is '' or NULL -- the
release-date sync leaves a year-only date out) whose file sits in the label tree, outside the import
queue. They are judged per release directory, the way the rule judges them:

    deezer          the .nfo links a Deezer album whose cached date matches the release year
    deezer-pending  the .nfo links Deezer, but nobody has asked yet (or a gone album is due again)
    deezer-gone     Deezer no longer has the album and the .nfo has no date either
    nfo-street / nfo-release / nfo-rip   an .nfo date line agreeing with the folder's year
    none            nothing better than the year

Measured on production on 2026-10-02 over the 22.689 EPs tracks of 2024-2026 with a year-only
date: 13.800 sit in a release whose .nfo links Deezer (5.711 albums; 59 of a sample of 60 answered
with a full date in the right year), 81 have only an .nfo date line, the rest nothing.

    python -m services.tagger.release_date_backfill                  # dry run: counts, nothing written
    python -m services.tagger.release_date_backfill --lookup 2000    # also ask Deezer for up to 2000 albums
    python -m services.tagger.release_date_backfill --apply          # queue (reason release_date_ladder)

`--lookup` writes only `release_store_lookups`; `--apply` writes only the tagger queue. Run inside the
music-manager container (database, /mnt/music, network). The tagger's own rounds do the writing.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from services.common.release_nfo import links as nfo_links
from services.common.store_lookup import Budget, StoreCache
from services.tagger.Song import NfoDate

#: The rescan reason the queued rows carry, so the queue can be watched and undone per reason.
REASON = 'release_date_ladder'
BATCH_SIZE = 500

CANDIDATES_SQL = (
    'SELECT mf.file_path FROM library_media_files mf JOIN library_tracks t ON t.id = mf.track_id '
    "WHERE mf.file_path LIKE %s AND (t.release_date IS NULL OR t.release_date = '')"
)

QUEUE_SQL = (
    'INSERT INTO tagger_processed_files (filepath, mtime, needs_rescan, rescan_reason) '
    'VALUES (%s, 0, TRUE, %s) '
    'ON DUPLICATE KEY UPDATE needs_rescan = TRUE, rescan_reason = VALUES(rescan_reason), '
    'attempts = 0, last_attempt = NULL'
)

#: The verdicts whose tracks a retag lifts.
LIFTABLE = ('deezer', 'nfo-street', 'nfo-release', 'nfo-rip')


@dataclass
class Plan:
    """Tracks and release directories per verdict."""

    tracks: dict[str, list[str]] = field(default_factory=dict)
    directories: Counter = field(default_factory=Counter)

    def add(self, verdict: str, paths: list[str]) -> None:
        """File one release directory's tracks under `verdict`."""
        self.tracks.setdefault(verdict, []).extend(paths)
        self.directories[verdict] += 1

    def counts(self) -> dict[str, dict[str, int]]:
        """Tracks and directories per verdict, for the report."""
        return {
            verdict: {'tracks': len(paths), 'directories': self.directories[verdict]}
            for verdict, paths in sorted(self.tracks.items())
        }

    def liftable(self) -> list[str]:
        """Every track a retag would give a better date."""
        return [path for verdict in LIFTABLE for path in self.tracks.get(verdict, [])]


def group_by_directory(paths: Iterable[str]) -> dict[str, list[str]]:
    """Track paths per release directory."""
    grouped: dict[str, list[str]] = {}
    for path in paths:
        grouped.setdefault(os.path.dirname(path), []).append(path)
    return grouped


def judge(directory: str, store: StoreCache, read_nfo: Callable[[str], str | None] | None = None) -> str:
    """The verdict for one release directory; see the module docstring."""
    text = (read_nfo or NfoDate.read_nfo)(directory) or ''
    dirname = os.path.basename(directory)
    year = NfoDate.dirname_year(dirname)
    link = next((link for link in nfo_links(text) if link.store == 'deezer'), None)
    pending = gone = False
    if link is not None:
        album = store.lookup(link)
        if album is None or store.is_stale(album):
            pending = True
        elif album.found and album.full_date and (year is None or int(album.full_date[:4]) == year):
            return 'deezer'
        elif not album.found:
            gone = True
    kind, resolved = NfoDate.resolve(text, dirname) if text else (None, None)
    if resolved is not None:
        return {'street': 'nfo-street', 'release': 'nfo-release'}.get(kind, 'nfo-rip')
    if pending:
        return 'deezer-pending'
    return 'deezer-gone' if gone else 'none'


def plan(grouped: dict[str, list[str]], store: StoreCache, read_nfo=None) -> Plan:
    """Judge every release directory."""
    result = Plan()
    for directory in sorted(grouped):
        result.add(judge(directory, store, read_nfo), grouped[directory])
    return result


def fill_cache(grouped: dict[str, list[str]], store: StoreCache, limit: int, read_nfo=None) -> dict[str, int]:
    """Ask Deezer about up to `limit` albums no answer is stored for yet. Writes only the cache table."""
    budget = Budget(limit)
    asked = 0
    for directory in sorted(grouped):
        if not budget.allows():
            break
        text = (read_nfo or NfoDate.read_nfo)(directory) or ''
        link = next((link for link in nfo_links(text) if link.store == 'deezer'), None)
        if link is None:
            continue
        album = store.lookup(link)
        if album is not None and not store.is_stale(album):
            continue
        before = budget.remaining
        store.lookup(link, budget)
        asked += int(before != budget.remaining)
    return {'asked': asked, 'throttled': int(budget.throttled)}


def candidates(cursor, eps_root: str, queue) -> list[str]:
    """Paths of the label-tree tracks without a full release date, the import queue left out."""
    cursor.execute(CANDIDATES_SQL, (eps_root.rstrip('/') + '/%',))
    return [str(row[0]) for row in cursor.fetchall() if not queue.contains(str(row[0]))]


def queue_paths(cursor, paths: list[str]) -> int:
    """Put `paths` on the tagger queue with REASON."""
    for start in range(0, len(paths), BATCH_SIZE):
        cursor.executemany(QUEUE_SQL, [(path, REASON) for path in paths[start : start + BATCH_SIZE]])
    return len(paths)


def run(
    connection, eps_root: str, queue, store: StoreCache, lookup: int = 0, apply: bool = False, read_nfo=None
) -> dict:
    """The dry run, the optional cache fill and the optional queueing. Returns the report."""
    with connection.cursor() as cursor:
        grouped = group_by_directory(candidates(cursor, eps_root, queue))
    filled = fill_cache(grouped, store, lookup, read_nfo) if lookup > 0 else None
    result = plan(grouped, store, read_nfo)
    queued = 0
    if apply:
        with connection.cursor() as cursor:
            queued = queue_paths(cursor, result.liftable())
        connection.commit()
    return {
        'eps_root': eps_root,
        'directories': len(grouped),
        'tracks': sum(len(paths) for paths in grouped.values()),
        'lookup': filled,
        'counts': result.counts(),
        'liftable_tracks': len(result.liftable()),
        'applied': bool(apply),
        'reason': REASON,
        'queued': queued,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; prints the report as JSON."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n', maxsplit=1)[0])
    parser.add_argument('--lookup', type=int, default=0, help='ask Deezer for up to N uncached albums first')
    parser.add_argument('--apply', action='store_true', help='queue the liftable tracks; without it nothing is queued')
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s', stream=sys.stderr)

    from services.common.config_store import ConfigStore
    from services.common.Helpers.DatabaseConnector import DatabaseConnector
    from services.common.import_queue import ImportQueue

    settings = ConfigStore()
    with DatabaseConnector().connection() as connection:
        report = run(
            connection,
            settings.eps_folder_path,
            ImportQueue.from_settings(settings),
            StoreCache(),
            lookup=args.lookup,
            apply=args.apply,
        )
    json.dump(report, sys.stdout, ensure_ascii=False, indent=1)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
