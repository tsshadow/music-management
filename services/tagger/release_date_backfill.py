"""Find the label-tree tracks whose release date the date ladder can still improve, and queue them.

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

A track with a full date is a candidate too when its DATE_SOURCE tag names a lower rung than the
best one its release has now (`SOURCE_RANKS` in the rule): an `nfo-rip`, `arrival` or `tag` date
under a Deezer date, an `arrival` date under an .nfo date line. Only the releases with a Deezer link
or an .nfo date are looked at, and only the tracks whose date differs from the best date have their
tag read. They get their own verdicts, so the report shows how many each lower rung loses:

    upgrade-from-<source>   a retag replaces the <source> date with the better rung
    upgrade-pending         the .nfo links Deezer, nobody has asked yet, and the track's rung is lower

A full date without DATE_SOURCE counts as the rung the rule infers for it (`infer_source`): the
rule wrote the .nfo's date or the file's DATE without naming a source before the ladder. Any other
full date without DATE_SOURCE is a person's. A person's date, an equal or higher rung, or a date
that already equals the best date is never a candidate: the rule leaves those alone too.

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

import mutagen

from services.common.release_nfo import links as nfo_links
from services.common.store_lookup import Budget, StoreCache
from services.tagger.Song import NfoDate
from services.tagger.Song.rules.InferReleaseDateFromNfoRule import SOURCE_RANKS, from_date_tag, infer_source

#: The rescan reason the queued rows carry, so the queue can be watched and undone per reason.
REASON = 'release_date_ladder'
BATCH_SIZE = 500

CANDIDATES_SQL = (
    'SELECT mf.file_path FROM library_media_files mf JOIN library_tracks t ON t.id = mf.track_id '
    "WHERE mf.file_path LIKE %s AND (t.release_date IS NULL OR t.release_date = '')"
)

#: The label-tree tracks that already have a full date; the ones on a lower rung may be upgraded.
DATED_SQL = (
    'SELECT mf.file_path, t.release_date FROM library_media_files mf JOIN library_tracks t ON t.id = mf.track_id '
    'WHERE mf.file_path LIKE %s AND LENGTH(t.release_date) >= 10'
)

#: Where each date tag lives per format: ID3 (MP3, WAV, AIFF), Vorbis comments, MP4.
DATE_SOURCE_KEYS = ('TXXX:DATE_SOURCE', 'date_source', '----:com.apple.iTunes:date_source')
ORIGINAL_DATE_KEYS = ('TDOR', 'originaldate', '----:com.apple.iTunes:originaldate')
DATE_KEYS = ('TDRC', 'date', '\xa9day')

QUEUE_SQL = (
    'INSERT INTO tagger_processed_files (filepath, mtime, needs_rescan, rescan_reason) '
    'VALUES (%s, 0, TRUE, %s) '
    'ON DUPLICATE KEY UPDATE needs_rescan = TRUE, rescan_reason = VALUES(rescan_reason), '
    'attempts = 0, last_attempt = NULL'
)

#: The verdicts whose tracks a retag lifts, besides every `upgrade-from-<source>`.
LIFTABLE = ('deezer', 'nfo-street', 'nfo-release', 'nfo-rip')
UPGRADE_PREFIX = 'upgrade-from-'
UPGRADE_PENDING = 'upgrade-pending'


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
        verdicts = list(LIFTABLE) + sorted(v for v in self.tracks if v.startswith(UPGRADE_PREFIX))
        return [path for verdict in verdicts for path in self.tracks.get(verdict, [])]

    def merge(self, other: Plan) -> None:
        """Add another plan's tracks and directories to this one."""
        for verdict, paths in other.tracks.items():
            self.tracks.setdefault(verdict, []).extend(paths)
        self.directories.update(other.directories)


def group_by_directory(paths: Iterable[str]) -> dict[str, list[str]]:
    """Track paths per release directory."""
    grouped: dict[str, list[str]] = {}
    for path in paths:
        grouped.setdefault(os.path.dirname(path), []).append(path)
    return grouped


@dataclass(frozen=True)
class Best:
    """The best rung a release directory offers now: verdict, its date, whether Deezer is unasked, and
    the .nfo's own `(date, source)` for telling a pre-ladder date from a person's."""

    verdict: str
    date: str | None = None
    pending: bool = False
    nfo: tuple[str, str] | None = None


@dataclass(frozen=True)
class DateTags:
    """The three date tags of one file, as text ('' when absent)."""

    source: str = ''
    original: str = ''
    date: str = ''

    def rung(self, best: Best) -> str:
        """The rung this file's date counts as: its DATE_SOURCE, else what the rule infers, else ''."""
        if self.source in SOURCE_RANKS:
            return self.source
        found = [best.nfo] if best.nfo else []
        from_tag = from_date_tag(self.date)
        if from_tag:
            found.append((from_tag, 'tag'))
        return infer_source(self.original, found) or ''


def best_available(directory: str, store: StoreCache, read_nfo: Callable[[str], str | None] | None = None) -> Best:
    """The best rung for one release directory, judged the way the rule judges it."""
    text = (read_nfo or NfoDate.read_nfo)(directory) or ''
    dirname = os.path.basename(directory)
    year = NfoDate.dirname_year(dirname)
    link = next((link for link in nfo_links(text) if link.store == 'deezer'), None)
    pending = gone = False
    deezer_date = None
    if link is not None:
        album = store.lookup(link)
        if album is None or store.is_stale(album):
            pending = True
        elif album.found and album.full_date and (year is None or int(album.full_date[:4]) == year):
            deezer_date = album.full_date
        elif not album.found:
            gone = True
    kind, resolved = NfoDate.resolve(text, dirname) if text else (None, None)
    nfo = None
    if resolved is not None:
        nfo = (resolved.isoformat(), {'street': 'nfo-street', 'release': 'nfo-release'}.get(kind or '', 'nfo-rip'))
    if deezer_date is not None:
        return Best('deezer', deezer_date, nfo=nfo)
    if nfo is not None:
        return Best(nfo[1], nfo[0], pending, nfo)
    if pending:
        return Best('deezer-pending', None, True)
    return Best('deezer-gone' if gone else 'none')


def judge(directory: str, store: StoreCache, read_nfo: Callable[[str], str | None] | None = None) -> str:
    """The verdict for one release directory; see the module docstring."""
    return best_available(directory, store, read_nfo).verdict


def read_date_tags(path: str) -> DateTags:
    """The file's DATE_SOURCE, ORIGINALDATE and DATE; empty when it cannot be read."""
    try:
        audio = mutagen.File(path)
    except Exception as exc:  # noqa: BLE001 - an unreadable file is simply not a candidate
        logging.debug('Could not read tags from %s: %s', path, exc)
        return DateTags()
    tags = getattr(audio, 'tags', None)
    if tags is None:
        return DateTags()
    return DateTags(_tag(tags, DATE_SOURCE_KEYS), _tag(tags, ORIGINAL_DATE_KEYS), _tag(tags, DATE_KEYS))


def _tag(tags, keys) -> str:
    """The first non-empty text under any of `keys`."""
    for key in keys:
        try:
            value = tags.get(key)
        except (KeyError, ValueError):
            value = None
        text = _first_text(value)
        if text:
            return text
    return ''


def _first_text(value) -> str:
    """The first text of a mutagen tag value: an ID3 frame, a list of strings, or MP4 bytes."""
    value = getattr(value, 'text', value)
    if isinstance(value, list):
        value = value[0] if value else ''
    if isinstance(value, bytes):
        value = value.decode('utf-8', 'replace')
    return str(value or '').strip()


def plan_upgrades(
    dated: dict[str, list[tuple[str, str]]],
    store: StoreCache,
    read_nfo=None,
    read_tags: Callable[[str], DateTags] = read_date_tags,
) -> Plan:
    """The full-date tracks on a lower rung than their release offers now; never a downgrade."""
    result = Plan()
    for directory in sorted(dated):
        best = best_available(directory, store, read_nfo)
        known_rank = SOURCE_RANKS.get(best.verdict)
        if known_rank is None and not best.pending:
            continue
        found: dict[str, list[str]] = {}
        for path, current in dated[directory]:
            # While Deezer is unasked, a date equal to the .nfo's may still be a day off.
            if best.date is not None and not best.pending and current[:10] == best.date[:10]:
                continue
            source = read_tags(path).rung(best)
            rank = SOURCE_RANKS.get(source)
            if rank is None:
                continue
            if known_rank is not None and rank > known_rank:
                found.setdefault(UPGRADE_PREFIX + source, []).append(path)
            elif best.pending and rank > SOURCE_RANKS['deezer']:
                found.setdefault(UPGRADE_PENDING, []).append(path)
        for verdict, paths in found.items():
            result.add(verdict, paths)
    return result


def plan(grouped: dict[str, list[str]], store: StoreCache, read_nfo=None) -> Plan:
    """Judge every release directory."""
    result = Plan()
    for directory in sorted(grouped):
        result.add(judge(directory, store, read_nfo), grouped[directory])
    return result


def fill_cache(directories: Iterable[str], store: StoreCache, limit: int, read_nfo=None) -> dict[str, int]:
    """Ask Deezer about up to `limit` albums no answer is stored for yet. Writes only the cache table."""
    budget = Budget(limit)
    asked = 0
    for directory in directories:
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


def dated_candidates(cursor, eps_root: str, queue) -> dict[str, list[tuple[str, str]]]:
    """The label-tree tracks with a full date, `(path, release_date)` per release directory."""
    cursor.execute(DATED_SQL, (eps_root.rstrip('/') + '/%',))
    grouped: dict[str, list[tuple[str, str]]] = {}
    for path, release_date in cursor.fetchall():
        if not queue.contains(str(path)):
            grouped.setdefault(os.path.dirname(str(path)), []).append((str(path), str(release_date)))
    return grouped


def queue_paths(cursor, paths: list[str]) -> int:
    """Put `paths` on the tagger queue with REASON."""
    for start in range(0, len(paths), BATCH_SIZE):
        cursor.executemany(QUEUE_SQL, [(path, REASON) for path in paths[start : start + BATCH_SIZE]])
    return len(paths)


def run(
    connection,
    eps_root: str,
    queue,
    store: StoreCache,
    *,
    lookup: int = 0,
    apply: bool = False,
    read_nfo=None,
    read_tags: Callable[[str], DateTags] = read_date_tags,
) -> dict:
    """The dry run, the optional cache fill and the optional queueing. Returns the report."""
    with connection.cursor() as cursor:
        grouped = group_by_directory(candidates(cursor, eps_root, queue))
        dated = dated_candidates(cursor, eps_root, queue)
    read: dict[str, DateTags] = {}

    def cached_tags(path: str) -> DateTags:
        """Each file's tags are read once, even when the plan is made twice."""
        if path not in read:
            read[path] = read_tags(path)
        return read[path]

    filled = None
    if lookup > 0:
        pending = plan_upgrades(dated, store, read_nfo, cached_tags).tracks.get(UPGRADE_PENDING, [])
        pending_dirs = sorted({os.path.dirname(path) for path in pending})
        filled = fill_cache(pending_dirs + sorted(grouped), store, lookup, read_nfo)
    result = plan(grouped, store, read_nfo)
    upgrades = plan_upgrades(dated, store, read_nfo, cached_tags)
    result.merge(upgrades)
    queued = 0
    if apply:
        with connection.cursor() as cursor:
            queued = queue_paths(cursor, result.liftable())
        connection.commit()
    return {
        'eps_root': eps_root,
        'directories': len(grouped),
        'tracks': sum(len(paths) for paths in grouped.values()),
        'dated_tracks': sum(len(rows) for rows in dated.values()),
        'upgrade_tracks': sum(len(paths) for paths in upgrades.tracks.values()),
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
