"""Learn where the curator files releases whose .nfo label names another folder (#164).

The importer places a release by the label its .nfo names, but the curator's own filing outranks
the name: releases whose .nfo says `Cloud 9 Music` sit in `Cloud 9 Dance`. This walks the label
tree, reads each release folder's .nfo, and for every .nfo label that maps by name to one folder
while releases carrying it sit in another, records the pair in `rules_label_name_choices`: the
folder by name, the folder the curator used most, how many releases sit in each, two examples.
The importer then proposes such a release with both folders instead of moving it, and the
curator's answer -- given once, in Management > Label proposals -- places every later one.

A re-learn refreshes the counts and examples and adds new pairs; it never touches a choice the
curator already made. Seeded from production on 2026-10-02 by migrate_v56 (104 labels).

    python -m services.importer.label_history            # dry run: the pairs, nothing written
    python -m services.importer.label_history --apply    # upsert them

Run inside the music-manager container (database and /mnt/music). It reads one .nfo per release
folder over the share -- about 43.000 -- so it takes a while.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from services.common import release_nfo
from services.common.import_queue import ImportQueue
from services.importer.label_match import LabelIndex, fold

UPSERT_SQL = (
    'INSERT INTO rules_label_name_choices '
    '(nfo_label_key, nfo_label, name_folder, history_folder, history_count, name_count, examples) '
    'VALUES (%s, %s, %s, %s, %s, %s, %s) '
    'ON DUPLICATE KEY UPDATE nfo_label = VALUES(nfo_label), name_folder = VALUES(name_folder), '
    'history_folder = VALUES(history_folder), history_count = VALUES(history_count), '
    'name_count = VALUES(name_count), examples = VALUES(examples), learned_at = CURRENT_TIMESTAMP'
)


@dataclass
class Pair:
    """One .nfo label whose name and filing disagree."""

    key: str
    nfo_label: str
    name_folder: str
    history_folder: str
    history_count: int
    name_count: int
    examples: list[str] = field(default_factory=list)


def learn(releases: Iterable[tuple[str, str, str | None]], index: LabelIndex) -> list[Pair]:
    """The pairs in `(label folder, release folder, .nfo label)` triples, most-filed first."""
    elsewhere: dict[str, Counter] = defaultdict(Counter)
    examples: dict[tuple[str, str], list[str]] = defaultdict(list)
    agreeing: Counter = Counter()
    spelling: dict[str, str] = {}
    by_name: dict[str, str] = {}
    for folder, release, label in releases:
        if not label:
            continue
        name_folder = index.match(label)
        if name_folder is None:
            continue
        key = fold(label)
        spelling.setdefault(key, label.strip())
        by_name[key] = name_folder
        if name_folder == folder:
            agreeing[key] += 1
            continue
        elsewhere[key][folder] += 1
        if len(examples[(key, folder)]) < 2:
            examples[(key, folder)].append(release)
    pairs = []
    for key, folders in elsewhere.items():
        history_folder, count = folders.most_common(1)[0]
        pairs.append(
            Pair(
                key, spelling[key], by_name[key], history_folder, count, agreeing[key], examples[(key, history_folder)]
            )
        )
    return sorted(pairs, key=lambda pair: (-pair.history_count, pair.key))


def walk_label_tree(
    eps_root: str, queue: ImportQueue, read: Callable[[str], release_nfo.NfoInfo | None] = release_nfo.read
):
    """`(label folder, release folder, .nfo label)` for every release folder under the label tree."""
    for folder in sorted(os.listdir(eps_root)):
        path = os.path.join(eps_root, folder)
        if not os.path.isdir(path) or not queue.is_label_folder(path):
            continue
        try:
            releases = sorted(os.listdir(path))
        except OSError as exc:
            logging.warning('Could not list %s: %s', path, exc)
            continue
        for release in releases:
            release_path = os.path.join(path, release)
            if os.path.isdir(release_path):
                facts = read(release_path)
                yield folder, release, facts.label if facts else None


def store(connection, pairs: list[Pair]) -> int:
    """Upsert every pair; a choice already made stays."""
    with connection.cursor() as cursor:
        for pair in pairs:
            cursor.execute(
                UPSERT_SQL,
                (
                    pair.key,
                    pair.nfo_label[:255],
                    pair.name_folder,
                    pair.history_folder,
                    pair.history_count,
                    pair.name_count,
                    ' | '.join(pair.examples),
                ),
            )
    connection.commit()
    return len(pairs)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; prints the pairs as JSON."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n', maxsplit=1)[0])
    parser.add_argument('--apply', action='store_true', help='write the pairs; without it nothing is written')
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s', stream=sys.stderr)

    from services.common.config_store import ConfigStore
    from services.common.Helpers.DatabaseConnector import DatabaseConnector

    settings = ConfigStore()
    queue = ImportQueue.from_settings(settings)
    connector = DatabaseConnector()
    index = LabelIndex.from_library(settings.eps_folder_path, queue, connector.connection)
    pairs = learn(walk_label_tree(settings.eps_folder_path, queue), index)
    written = 0
    if args.apply:
        with connector.connection() as connection:
            written = store(connection, pairs)
    json.dump(
        {'pairs': [pair.__dict__ for pair in pairs], 'applied': bool(args.apply), 'written': written},
        sys.stdout,
        ensure_ascii=False,
        indent=1,
    )
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
