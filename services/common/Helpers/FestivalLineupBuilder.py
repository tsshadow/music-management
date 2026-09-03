"""Helpers for writing a festival lineup by hand, and for seeing what it will actually match.

`FestivalLineupRepository` (music-management-server) reads
`/music/metadata/festival-lineups/<name>.txt`, one artist per line, and `getSpotifyTracks` filters
on it with `LOWER(artist_display_name) IN (...)`. That match is the whole point and the whole trap:
it compares the *entire* display name, lowercased, so `Angerfist` matches a track by `Angerfist`
and never one by `Angerfist & Outsiders`, and a spelling the library stores differently
(`D-Block & S-te-Fan` vs `D-Block and S-te-fan`) matches nothing at all.

A lineup is therefore typed out by hand from the festival's own bill, and the only question worth
answering before writing the file is which of those lines this library can actually match. That is
what [match_lineup] reports: the lines that match as they are, the ones that do not, and for each
of those the closest display names the library does have -- so the correction is a copy rather than
a search.

Deriving the bill from the library's own FESTIVAL tags was tried and rejected: warm-up mixes,
livesets and podcast episodes all carry the tag, so the "lineup" filled up with names that were
never on the bill.
"""

import difflib
import re

# The artist field collects debris: a stray date, a track number, a whole tracklist. A hand-typed
# lineup should not carry any of it either, so the same filter guards the import.
DATE_IN_NAME = re.compile(r'\d{4}-\d{2}-\d{2}')
DIGITS_ONLY = re.compile(r'^[\d\s.:-]+$')
MAX_NAME_LENGTH = 120

# How many alternatives to offer for a line that matches nothing, and how close they have to be.
SUGGESTION_COUNT = 3
SUGGESTION_CUTOFF = 0.72


def looks_like_an_artist(name) -> bool:
    """Whether a line is worth writing as a lineup entry."""
    if not name or not name.strip():
        return False

    stripped = name.strip()
    return len(stripped) <= MAX_NAME_LENGTH and not DATE_IN_NAME.search(stripped) and not DIGITS_ONLY.match(stripped)


def parse_lineup(text: str) -> list[str]:
    """The names out of a pasted bill: one per line, blanks and debris dropped, order kept.

    Order is kept rather than sorted because a pasted bill is read back against its source, and
    duplicates are dropped because the file is a set as far as the filter is concerned.
    """
    seen: set[str] = set()
    names = []

    for line in text.splitlines():
        name = line.strip()
        if not looks_like_an_artist(name) or name.lower() in seen:
            continue
        seen.add(name.lower())
        names.append(name)

    return names


def match_lineup(names, known_artists) -> dict:
    """Which of `names` the library can match, and what the others were probably meant to be.

    `known_artists` are display names exactly as the library stores them -- the same field the
    filter compares against, so a name reported as matched here will match there.
    """
    by_lower = {artist.lower(): artist for artist in known_artists if artist}

    matched, unmatched, suggestions = [], [], {}
    for name in names:
        if name.lower() in by_lower:
            # The library's own spelling, not the typed one: the filter is case-insensitive, but
            # writing what the library holds keeps the file readable next to the browse page.
            matched.append(by_lower[name.lower()])
            continue

        unmatched.append(name)
        close = difflib.get_close_matches(name.lower(), by_lower.keys(), n=SUGGESTION_COUNT, cutoff=SUGGESTION_CUTOFF)
        if close:
            suggestions[name] = [by_lower[key] for key in close]

    return {'matched': matched, 'unmatched': unmatched, 'suggestions': suggestions}


def lineup_segment(name) -> str:
    """One path segment: a separator in a festival or stage name must not become a directory."""
    return str(name).strip().replace('/', '-').replace('\\', '-')


def lineup_filename(festival: str, year=None, stage=None) -> str:
    """The file for one edition, relative to the lineup directory.

    An edition goes in a directory named after the festival, and a stage in a directory named
    after the edition, because `FestivalLineupRepository` reads a directory as the union of
    everything below it. Writing `Defqon.1/2014/RED.txt` therefore also creates the lineup
    `Defqon.1/2014` (the edition across its stages) and `Defqon.1` (the festival across its
    editions), without one artist name being written down twice.

    Per stage is only worth it for a festival whose stages differ in genre. For a single-genre
    festival, leave the stage out: one file for the edition says the same thing.
    """
    parts = [lineup_segment(festival)]
    if year:
        parts.append(lineup_segment(year))
    if stage:
        if not year:
            raise ValueError('a stage belongs to an edition: pass a year as well')
        parts.append(lineup_segment(stage))

    return '/'.join(parts) + '.txt'


def render_lineup(artists) -> str:
    """The file's contents. Names only: the reader treats every non-empty line as an artist, so
    there is nowhere to put a header saying where the file came from."""
    return ''.join(f'{name}\n' for name in artists)
