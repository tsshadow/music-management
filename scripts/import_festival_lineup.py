"""Writes one festival lineup from a bill you paste, and says up front what it will match.

`/music/metadata/festival-lineups` has been empty since it was created, so the Lineups page and the
phone's lineup browse both work and show nothing. A lineup is typed out by hand from the festival's
own bill -- Partyflock, named in the design as the preferred source, forbids scrapers in its terms
of use (article 5) and reuse of its data without permission (article 6).

The reason this is a script and not just a text editor is the match. `getSpotifyTracks` filters a
lineup with `LOWER(artist_display_name) IN (...)`, comparing the *whole* display name, so a line
this library spells differently silently contributes nothing. This reads the bill, checks every
line against the artist names LMS actually holds, and reports which lines match, which do not, and
what the closest names in the library are -- before writing anything.

    python3 scripts/import_festival_lineup.py --festival "Defqon.1" --year 2025 --file defqon-2025.txt
    python3 scripts/import_festival_lineup.py --festival "Defqon.1" --year 2025 --file ... --write
    python3 scripts/import_festival_lineup.py --festival "Defqon.1" --year 2014 --stage RED --file ... --write

A stage goes in its own file under the edition, and the reader treats a directory as the union of
everything below it, so the last line above also fills the lineups `Defqon.1/2014` and `Defqon.1`.
Split by stage for a festival whose stages differ in genre; for a single-genre festival, leave
`--stage` out and let the edition be one file.

Read `--file -` to take the bill on stdin. Nothing is written without `--write`.
"""

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pylint: disable=wrong-import-position
from services.common.Helpers.FestivalLineupBuilder import (  # noqa: E402
    lineup_filename,
    match_lineup,
    parse_lineup,
    render_lineup,
)

DEFAULT_DB = '/var/lms/lms.db'
DEFAULT_OUT = '/music/metadata/festival-lineups'

# The display name is the field the filter compares against, so it is the field to check against
# too -- not `artist.name`, which is the split-out artist and matches something else.
KNOWN_ARTISTS = 'SELECT DISTINCT artist_display_name FROM track WHERE artist_display_name IS NOT NULL'


def read_known_artists(database: str) -> list[str]:
    """Every artist display name the library holds. Read-only: this never writes to LMS."""
    connection = sqlite3.connect(f'file:{database}?mode=ro', uri=True)
    try:
        return [row[0] for row in connection.execute(KNOWN_ARTISTS)]
    finally:
        connection.close()


def read_bill(path: str) -> str:
    if path == '-':
        return sys.stdin.read()
    with open(path, encoding='utf-8') as handle:
        return handle.read()


def report(result) -> None:
    print(f"{len(result['matched'])} of {len(result['matched']) + len(result['unmatched'])} names match the library")

    for name in result['unmatched']:
        alternatives = result['suggestions'].get(name)
        if alternatives:
            print(f'  no match: {name}  ->  did you mean: {", ".join(alternatives)}')
        else:
            print(f'  no match: {name}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--festival', required=True, help='Festival name, as it should appear in the app.')
    parser.add_argument('--year', help='Edition year. Left out, the lineup is the festival itself.')
    parser.add_argument(
        '--stage',
        help='Stage name. Needs a year, and is only worth splitting on when the stages differ in genre.',
    )
    parser.add_argument('--file', required=True, help="The bill, one artist per line. '-' reads stdin.")
    parser.add_argument('--db', default=DEFAULT_DB, help='Path to lms.db (read-only).')
    parser.add_argument('--out', default=DEFAULT_OUT, help='Lineup directory to write into.')
    parser.add_argument(
        '--keep-unmatched',
        action='store_true',
        help='Write the names that match nothing as well. They filter nothing, but they do document the bill.',
    )
    parser.add_argument('--write', action='store_true', help='Actually write; without it nothing is created.')
    args = parser.parse_args(argv)

    names = parse_lineup(read_bill(args.file))
    result = match_lineup(names, read_known_artists(args.db))
    report(result)

    artists = result['matched'] + (result['unmatched'] if args.keep_unmatched else [])
    path = os.path.join(args.out, lineup_filename(args.festival, args.year, args.stage))

    if not args.write:
        print(f'Dry run. Add --write to create {path} with {len(artists)} names.')
        return 0

    if not artists:
        print('Nothing to write: not one name matched.')
        return 1

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(render_lineup(artists))
    print(f'wrote {path} with {len(artists)} names')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
