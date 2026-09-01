#!/usr/bin/env python3
"""Dry-run report: what would happen to every artist name in the library.

Changes nothing. Reads the artist list, asks `ArtistNameAnalyzer` what it would
propose for each name, and prints the funnel plus a sample of every category, so
the thresholds can be judged against the real data before any of this is wired
into the tagger.

Two inputs, because the production database is usually not reachable from where
this is run:

    tools/artist_curation_report.py --db
    tools/artist_curation_report.py --csv artists.csv

The CSV wants a header and three columns: name, tracks, sources — where
`sources` is the number of distinct folders the name occurs in. Export it with:

    SELECT a.name,
           COUNT(DISTINCT ta.track_id)                      AS tracks,
           COUNT(DISTINCT SUBSTRING_INDEX(mf.file_path, '/', -2)) AS sources
    FROM library_artists a
    LEFT JOIN library_track_artists ta ON ta.artist_id = a.id
    LEFT JOIN library_media_files mf   ON mf.track_id  = ta.track_id
    GROUP BY a.id, a.name;
"""

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from services.common.Helpers.ArtistNameAnalyzer import (  # noqa: E402
    KEEP,
    REJECT,
    REWRITE,
    SPLIT,
    UNKNOWN,
    AnalyzerConfig,
    ArtistNameAnalyzer,
)

KINDS = (KEEP, REWRITE, SPLIT, REJECT, UNKNOWN)
KIND_LABELS = {
    KEEP: 'keep as is',
    REWRITE: 'rewrite to an approved name',
    SPLIT: 'split into approved names',
    REJECT: 'remove from the tag',
    UNKNOWN: 'no mechanical answer - human or external lookup',
}


def load_csv(path):
    """Read (name, tracks, sources) rows from a CSV export."""
    rows = []
    with open(path, newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            rows.append(
                {
                    'name': row['name'],
                    'tracks': int(row.get('tracks') or 0),
                    'sources': int(row.get('sources') or 0),
                }
            )
    return rows


def load_db():
    """Read the same rows straight from the configured database."""
    from services.common.Helpers.DatabaseConnector import DatabaseConnector

    query = """
        SELECT a.name,
               COUNT(DISTINCT ta.track_id) AS tracks,
               COUNT(DISTINCT SUBSTRING_INDEX(mf.file_path, '/', -2)) AS sources
        FROM library_artists a
        LEFT JOIN library_track_artists ta ON ta.artist_id = a.id
        LEFT JOIN library_media_files mf ON mf.track_id = ta.track_id
        GROUP BY a.id, a.name
    """
    connection = DatabaseConnector().connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(query)
            return [{'name': r[0], 'tracks': int(r[1] or 0), 'sources': int(r[2] or 0)} for r in cursor.fetchall()]
    finally:
        connection.close()


def build_seed(rows, config):
    """The artists the dictionary starts from.

    Bootstrapping has to happen without external lookups, so it leans on the two
    signals that are already in the data: a name that carries no detectable noise
    and is not sentence-like, and that occurs across several folders. Spread is
    what separates a real artist from junk one bad tagger rule sprayed over a
    single folder, which is why a high track count alone is not enough.
    """
    empty = ArtistNameAnalyzer([], config)
    seed = []
    for row in rows:
        if row['tracks'] < config.bootstrap_min_tracks or row['sources'] < 2:
            continue
        stripped, removed = empty.strip_affixes(row['name'])
        if removed or stripped != row['name'].strip():
            continue
        score, _ = empty.junk_score(row['name'])
        if score >= config.junk_score_threshold:
            continue
        seed.append(row['name'])
    return seed


def analyse(rows, analyzer):
    """Attach a proposal to every row."""
    return [dict(row, proposal=analyzer.propose(row['name'])) for row in rows]


def print_report(results, seed_size, total_rows, out=sys.stdout):
    """The funnel, then a sample of each category ordered by impact."""
    by_kind = defaultdict(list)
    for result in results:
        by_kind[result['proposal'].kind].append(result)

    tracks_total = sum(r['tracks'] for r in results) or 1

    print('=' * 78, file=out)
    print(f'Artist curation dry run: {total_rows} names, dictionary seeded with {seed_size}', file=out)
    print('=' * 78, file=out)
    print(f"{'proposal':<46} {'names':>7} {'share':>7} {'tracks':>8}", file=out)
    for kind in KINDS:
        group = by_kind.get(kind, [])
        tracks = sum(r['tracks'] for r in group)
        share = 100.0 * len(group) / (total_rows or 1)
        print(f'{KIND_LABELS[kind]:<46} {len(group):>7} {share:>6.1f}% {tracks:>8}', file=out)

    rewrites = by_kind.get(REWRITE, [])
    if rewrites:
        targets = Counter(r['proposal'].values[0] for r in rewrites)
        print(
            f'\n{len(rewrites)} rewrites collapse onto {len(targets)} distinct artists '
            f'- one decision each closes {len(rewrites) / len(targets):.1f} names on average.',
            file=out,
        )

    queue = by_kind.get(UNKNOWN, [])
    queue_tracks = sum(r['tracks'] for r in queue)
    print(
        f'{len(queue)} names ({100.0 * queue_tracks / tracks_total:.1f}% of tracks) '
        f'need a human or an external lookup.',
        file=out,
    )

    suspect = [r for r in queue if r['proposal'].junk_score >= AnalyzerConfig().junk_score_threshold]
    if suspect:
        print(
            f'{len(suspect)} of those look like sentences rather than names, and are flagged '
            f'rather than removed - real artists score the same way.',
            file=out,
        )

    for kind in KINDS:
        group = sorted(by_kind.get(kind, []), key=lambda r: -r['tracks'])
        if not group:
            continue
        print(f'\n--- {KIND_LABELS[kind]} (top 15 by track count) ' + '-' * 20, file=out)
        for result in group[:15]:
            proposal = result['proposal']
            arrow = ' ; '.join(proposal.values) if proposal.values else '(removed)'
            print(
                f"  {result['tracks']:>6} tracks / {result['sources']:>3} folders  {result['name']!r} -> {arrow}",
                file=out,
            )
            print(f"{'':>26}  because: {'; '.join(proposal.evidence)}", file=out)


def write_proposals(results, path):
    """Full machine-readable output, so a decision run can reuse it later."""
    with open(path, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(['name', 'tracks', 'sources', 'proposal', 'values', 'confidence', 'evidence'])
        for result in results:
            proposal = result['proposal']
            writer.writerow(
                [
                    result['name'],
                    result['tracks'],
                    result['sources'],
                    proposal.kind,
                    ';'.join(proposal.values),
                    proposal.confidence,
                    ' | '.join(proposal.evidence),
                ]
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--csv', help='CSV export with name, tracks, sources')
    source.add_argument('--db', action='store_true', help='read from the configured database')
    parser.add_argument('--config', help='JSON file overriding any AnalyzerConfig threshold')
    parser.add_argument('--out', help='write every proposal to this CSV')
    parser.add_argument('--approved', help='file with already approved artist names, one per line')
    args = parser.parse_args()

    config = AnalyzerConfig()
    if args.config:
        with open(args.config, encoding='utf-8') as handle:
            config = AnalyzerConfig.from_dict(json.load(handle))

    rows = load_db() if args.db else load_csv(args.csv)
    if not rows:
        print('No artists found.', file=sys.stderr)
        return 1

    seed = build_seed(rows, config)
    if args.approved:
        with open(args.approved, encoding='utf-8') as handle:
            seed += [line.strip() for line in handle if line.strip()]

    analyzer = ArtistNameAnalyzer(seed, config)
    results = analyse(rows, analyzer)
    print_report(results, len(set(seed)), len(rows))

    if args.out:
        write_proposals(results, args.out)
        print(f'\nAll {len(results)} proposals written to {args.out}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
