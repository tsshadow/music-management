#!/usr/bin/env python3
"""Finds radio shows and podcast series in the library and files them for curation.

Groups every file that carries an episode marker ("#150", "Episode 73", "week 023")
by what is left of its name once the marker, the guest and the month are cut off, and
reports each group that reaches `--min-episodes`. With `--apply` the groups are written
to `rules_podcasts` as `unknown`, with every observed spelling recorded in
`rules_podcast_aliases`; a decision that is already there is never overwritten.

Only shows a human then approves (`white`) are ever written to a file, so this tool is
safe to re-run: it proposes, it does not tag.

    tools/detect_podcasts.py                     # scan the music folder, print only
    tools/detect_podcasts.py --min-episodes 10
    tools/detect_podcasts.py --from-list files.txt
    tools/detect_podcasts.py --apply

Requiring an episode marker here while `InferPodcastFromTitleRule` does not is
deliberate: detection has to be conservative because it proposes new rows, and the rule
is already fenced in by a human decision.
"""
import argparse
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from services.common.Helpers.PodcastHelper import (  # noqa: E402
    find_episode,
    normalize,
    series_cut,
    strip_episode_and_guest,
)

AUDIO_EXTENSIONS = {'.mp3', '.flac', '.wav', '.m4a', '.aac', '.opus'}

# Label releases live in EPs and are the one place where a show name and a label name
# collide -- "Hard With Style" and "Hardcore Blasters" are labels there. The rest are
# not music the tagger owns.
EXCLUDED_ROOTS = {'EPs', 'archives', 'dump', 'download', 'private', 'Lidarr', 'images', 'metadata', 'scripts', '#recycle', '@eaDir'}

# Folders that say where a file came from rather than what series it is, so climbing out
# of a year folder does not stop on one of them.
SOURCE_ROOTS = {'mnt', 'music', 'Podcasts', 'Soundcloud', 'Youtube', 'Telegram', 'Livesets', 'Warm Up Mixes', 'Top 100', 'Spotify', 'Mashups', 'Hitzone', 'artists', 'EPs'}

# A stripped name that says "this is an episode of something" without saying of what.
# `Podcasts/The Magic Show/2011/Podcast week 023.mp3` leaves exactly this behind, and the
# folder is the only place its show is named.
GENERIC_KEYS = {'podcast', 'podcasts', 'episode', 'episodes', 'ep', 'afl', 'week', 'aflevering', 'mix', 'podcast mix'}

YEAR_FOLDER = re.compile('^(19|20)\\d{2}$')


@dataclass
class Series:
    """One candidate show: how it is spelled, how often, and where it lives."""
    key: str
    name: str
    count: int = 0
    aliases: list[str] = field(default_factory=list)
    sources: Counter = field(default_factory=Counter)
    episodes: list[str] = field(default_factory=list)

    def episode_span(self) -> str:
        numbers = sorted({int(e) for e in self.episodes if e.isdigit()})
        return f'{numbers[0]}-{numbers[-1]}' if numbers else '?'


def is_audio(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in AUDIO_EXTENSIONS


def is_excluded(path: str) -> bool:
    return any(part in EXCLUDED_ROOTS for part in path.split('/'))


def series_name_for(path: str) -> str | None:
    """
    The raw show name a path suggests, or None when it names no episode.

    Normally that is the filename up to the episode marker. When only a marker is left
    ("Podcast week 023"), the nearest folder that is neither a year nor a source folder
    is used instead.
    """
    parts = path.split('/')
    stem = os.path.splitext(parts[-1])[0]
    cut = series_cut(stem)
    if cut is None:
        return None
    raw = stem[:cut].strip(' -–—|_:·.')
    if normalize(raw) in GENERIC_KEYS or len(normalize(raw)) < 4:
        for folder in reversed(parts[:-1]):
            if folder and not YEAR_FOLDER.match(folder) and folder not in SOURCE_ROOTS:
                return folder
        return None
    return raw


def group_series(paths, min_episodes: int=5) -> list[Series]:
    """
    Groups paths into candidate shows, largest first.

    @param paths: iterable of file paths, absolute or relative
    @param min_episodes: how many episodes a group needs before it is reported
    """
    grouped: dict[str, Series] = {}
    spellings: dict[str, Counter] = {}
    for path in paths:
        path = path.rstrip('\n')
        if not is_audio(path) or is_excluded(path):
            continue
        raw = series_name_for(path)
        if not raw:
            continue
        key = strip_episode_and_guest(raw) or normalize(raw)
        if not key:
            continue
        series = grouped.setdefault(key, Series(key=key, name=raw))
        series.count += 1
        parts = path.split('/')
        series.sources[parts[1] if len(parts) > 2 else parts[0]] += 1
        episode = find_episode(os.path.splitext(parts[-1])[0])
        if episode:
            series.episodes.append(episode)
        spellings.setdefault(key, Counter())[raw] += 1
    result = []
    for key, series in grouped.items():
        if series.count < min_episodes:
            continue
        counted = spellings[key].most_common()
        # The spelling that occurs most often is the one a curator will recognise; the
        # rest become aliases so the tagger matches them too.
        series.name = counted[0][0]
        series.aliases = [spelling for spelling, _ in counted]
        result.append(series)
    result.sort(key=lambda s: (-s.count, s.key))
    return result


def walk(root: str):
    """Yields every file under root, skipping the excluded folders early."""
    for current, folders, files in os.walk(root):
        folders[:] = [f for f in folders if f not in EXCLUDED_ROOTS]
        for name in files:
            yield os.path.join(current, name)


def apply_to_database(series_list, connector=None) -> dict:
    """
    Upserts the detected series as undecided rows, leaving decisions alone.

    @param series_list: the Series objects to write
    @param connector: a DatabaseConnector, injected by the tests
    @return: counts of what was inserted or refreshed
    """
    from services.common.Helpers.DatabaseConnector import DatabaseConnector
    connection = (connector or DatabaseConnector()).connect()
    stats = {'shows': 0, 'aliases': 0}
    try:
        with connection.cursor() as cursor:
            for series in series_list:
                cursor.execute(
                    'INSERT INTO rules_podcasts (name, normalized_name, occurrences) VALUES (%s, %s, %s) '
                    'ON DUPLICATE KEY UPDATE occurrences = VALUES(occurrences)',
                    (series.name, series.key, series.count))
                stats['shows'] += 1
                cursor.execute('SELECT id FROM rules_podcasts WHERE normalized_name = %s', (series.key,))
                row = cursor.fetchone()
                podcast_id = row['id'] if isinstance(row, dict) else row[0]
                for alias in series.aliases:
                    cursor.execute(
                        'INSERT INTO rules_podcast_aliases (podcast_id, alias, normalized_alias, occurrences) '
                        'VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE occurrences = VALUES(occurrences)',
                        (podcast_id, alias, normalize(alias), series.count))
                    stats['aliases'] += 1
        connection.commit()
    finally:
        connection.close()
    return stats


def main(argv=None):
    parser = argparse.ArgumentParser(description='Detect radio shows and podcast series in the library.')
    parser.add_argument('--path', help='folder to scan; defaults to the configured music folder')
    parser.add_argument('--from-list', dest='from_list', help='read paths from a file instead of walking a folder')
    parser.add_argument('--min-episodes', dest='min_episodes', type=int, default=5)
    parser.add_argument('--apply', action='store_true', help='write the results to rules_podcasts as undecided')
    args = parser.parse_args(argv)

    if args.from_list:
        with open(args.from_list, encoding='utf-8', errors='replace') as handle:
            paths = list(handle)
    else:
        root = args.path
        if not root:
            from services.common.config_store import ConfigStore
            root = ConfigStore().music_folder_path
        paths = walk(root)

    series_list = group_series(paths, args.min_episodes)
    print(f'{len(series_list)} candidate series with at least {args.min_episodes} episodes\n')
    for series in series_list:
        sources = ', '.join(f'{name}:{count}' for name, count in series.sources.most_common(3))
        print(f'{series.count:5d}  {series.name[:52]:52s} ep {series.episode_span():>9s}  [{sources}]')
        if len(series.aliases) > 1:
            print(f'{"":7s}aliases: {" | ".join(series.aliases[1:])}')

    if args.apply:
        stats = apply_to_database(series_list)
        print(f"\nwrote {stats['shows']} shows and {stats['aliases']} aliases; every new row is 'unknown'")
    else:
        print('\nnothing written -- pass --apply to file these for curation')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
