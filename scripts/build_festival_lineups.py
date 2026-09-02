"""Writes one lineup file per festival edition, from the festival tags the library already carries.

`/music/metadata/festival-lineups` has been empty since it was created, so the Lineups page in the
web UI and the phone's lineup browse both work and show nothing. This fills it: LMS knows which
tracks carry which FESTIVAL tag, and every one of those tracks also has a year and an artist, so
the artists of `FESTIVAL=Defqon` dated 2025 are Defqon 2025 as far as this collection goes.

That is not the festival's real bill -- an artist you own no set of cannot appear -- and the design
(`docs/superpowers/specs/2026-08-24-browse-and-management-overhaul-design.md`) named Partyflock as
the preferred source for the real thing. Partyflock's terms of use forbid scrapers (article 5,
Gedragscode) and reuse of their data without permission (article 6), so that half needs their
consent, not a crawler. Until then this is the source that needs nobody's permission -- and it has
one advantage the external one cannot have: the names are read from the very field the filter
matches on, so every line matches its own tracks exactly.

Reads the LMS database read-only and writes nothing but the lineup files. Dry run by default.

    python3 scripts/build_festival_lineups.py --db /docker/lms/var/lms/lms.db
    python3 scripts/build_festival_lineups.py --db ... --out /mnt/music/metadata/festival-lineups --write
"""

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pylint: disable=wrong-import-position
from services.common.Helpers.FestivalLineupBuilder import (  # noqa: E402
    DEFAULT_MIN_ARTISTS,
    build_editions,
    lineup_filename,
    render_lineup,
)

DEFAULT_DB = '/var/lms/lms.db'
DEFAULT_OUT = '/music/metadata/festival-lineups'

# The tag is a cluster like GENRE and YEAR beside it; `date` is the track's own, which is the
# edition it was recorded at. A track whose date the scanner could not read is skipped by the
# builder rather than guessed at.
QUERY = """
    SELECT cl.name, substr(t.date, 1, 4), t.artist_display_name
    FROM cluster cl
    JOIN cluster_type ct ON ct.id = cl.cluster_type_id
    JOIN track_cluster tc ON tc.cluster_id = cl.id
    JOIN track t ON t.id = tc.track_id
    WHERE ct.name = 'FESTIVAL'
"""


def read_rows(database: str):
    """Every (festival, year, artist) the library knows. Read-only: this script never writes to LMS."""
    connection = sqlite3.connect(f'file:{database}?mode=ro', uri=True)
    try:
        return list(connection.execute(QUERY))
    finally:
        connection.close()


def write_editions(editions, out_dir: str, overwrite: bool) -> tuple[int, int]:
    """Writes one file per edition. Returns (written, skipped).

    A file that is already there is left alone unless `--overwrite` says otherwise: the directory is
    also where a hand-made lineup would live, and this script has no way to tell one of those from
    an older run of itself.
    """
    written = skipped = 0
    os.makedirs(out_dir, exist_ok=True)

    for (festival, year), artists in sorted(editions.items()):
        path = os.path.join(out_dir, lineup_filename(festival, year))
        if os.path.exists(path) and not overwrite:
            skipped += 1
            continue
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(render_lineup(artists))
        written += 1

    return written, skipped


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default=DEFAULT_DB, help='Path to lms.db (read-only).')
    parser.add_argument('--out', default=DEFAULT_OUT, help='Lineup directory to write into.')
    parser.add_argument(
        '--min-artists',
        type=int,
        default=DEFAULT_MIN_ARTISTS,
        help='How many artists an edition needs before it gets a file.',
    )
    parser.add_argument('--write', action='store_true', help='Actually write; without it nothing is created.')
    parser.add_argument('--overwrite', action='store_true', help='Replace lineup files that already exist.')
    args = parser.parse_args(argv)

    editions = build_editions(read_rows(args.db), min_artists=args.min_artists)
    print(f'{len(editions)} editions with at least {args.min_artists} artists')

    for (festival, year), artists in sorted(editions.items(), key=lambda item: -len(item[1]))[:10]:
        print(f'  {festival} {year}: {len(artists)} artists')

    if not args.write:
        print(f'Dry run. Add --write to create the files in {args.out}.')
        return 0

    written, skipped = write_editions(editions, args.out, args.overwrite)
    print(f'wrote {written} files, left {skipped} existing ones alone')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
