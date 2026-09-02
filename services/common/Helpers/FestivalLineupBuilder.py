"""Turns the library's festival tags into one lineup per edition.

`FestivalLineupRepository` (music-management-server) reads
`/music/metadata/festival-lineups/<name>.txt`, one artist per line, and `getSpotifyTracks` filters
on it with `LOWER(artist_display_name) IN (...)`. The directory has been empty since it was
created, so the Lineups page ships working and blank.

This fills it from what the library already knows: every track that carries a FESTIVAL tag also
carries a year and an artist, so the artists of `FESTIVAL=Defqon` in 2025 are the bill of Defqon
2025 *as far as this collection goes*. That is deliberately not the same thing as the real bill --
an artist you have no set of is not in the file -- and it is the honest half that needs no third
party. Partyflock, named in the design as the preferred source, forbids scrapers in its terms of
use (article 5), so filling the rest needs their permission rather than a crawler.

The names come from the same `artist_display_name` the filter matches on, so an entry written here
always matches its own tracks. That is the one thing an external source cannot promise: it would
have to spell every artist exactly the way this library does.
"""

import re

DEFAULT_MIN_ARTISTS = 3

# A four-digit year is what the query hands over; anything else is a date the scanner could not read.
YEAR = re.compile(r'^\d{4}$')

# The artist field collects debris: a stray date, a track number, a whole tracklist. None of those
# are a name, and each one becomes a line nobody can match against.
DATE_IN_NAME = re.compile(r'\d{4}-\d{2}-\d{2}')
DIGITS_ONLY = re.compile(r'^[\d\s.:-]+$')
MAX_NAME_LENGTH = 120


def looks_like_an_artist(name) -> bool:
    """Whether a display name is worth writing as a lineup line."""
    if not name or not name.strip():
        return False

    stripped = name.strip()
    return (
        len(stripped) <= MAX_NAME_LENGTH
        and not DATE_IN_NAME.search(stripped)
        and not DIGITS_ONLY.match(stripped)
    )


def build_editions(rows, min_artists: int = DEFAULT_MIN_ARTISTS) -> dict[tuple[str, str], list[str]]:
    """Groups `(festival, year, artist)` rows into `{(festival, year): [artist, ...]}`.

    Editions holding fewer than `min_artists` names are left out: two names is a coincidence rather
    than a lineup, and a page with one line on it reads as broken.
    """
    editions: dict[tuple[str, str], set[str]] = {}

    for festival, year, artist in rows:
        if not festival or not year or not YEAR.match(str(year)):
            continue
        if not looks_like_an_artist(artist):
            continue
        editions.setdefault((festival.strip(), str(year)), set()).add(artist.strip())

    return {key: sorted(names) for key, names in editions.items() if len(names) >= min_artists}


def lineup_filename(festival: str, year: str) -> str:
    """The file name for one edition. The stem is what `getLineups` reports and the app shows."""
    safe = festival.strip().replace('/', '-').replace('\\', '-')
    return f'{safe} {year}.txt'


def render_lineup(artists) -> str:
    """The file's contents. Names only: the reader treats every non-empty line as an artist, so
    there is nowhere to put a header saying where the file came from."""
    return ''.join(f'{name}\n' for name in artists)
