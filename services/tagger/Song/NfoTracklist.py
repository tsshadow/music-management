"""Reads the tracklist a scene NFO states, to recover artist wording the tagger has already split.

`CleanTagsRule` turns "Eternate & Prosphere" into two values and drops the "&" doing it. That is the
right shape to store, but the wording is gone the moment it has run once -- a re-tag cannot bring it
back, because there is nothing left to split. Measured over 400 files under the EPs root: 120 carry
a split artist, none still carry the original wording. The NFO shipped inside the release directory
is written before any of that and still says it.

Parsing lives here rather than in the script that uses it, so every layout can be tested without a
file, and it deliberately reuses `Tag` for the splitting: the guard that decides whether an NFO line
describes the track in hand compares the NFO's own split against the tag's values, and reimplementing
the split here would let the two drift apart.
"""

import re

from services.tagger.constants import ARTIST
from services.tagger.Song.Tag import Tag

# A duration the line may end with: "[04:33]", "(4:33)", "04:33".
_DURATION = re.compile(r'[\[\(]?\d{1,3}:\d{2}[\]\)]?\s*$')

# "01. Artist - Title", "01 Artist - Title", "[01] Artist - Title", "01) Artist - Title".
# The number has to lead the line: a bare "Artist - Title" is just as often the release header, and
# without a number there is nothing to match a file against anyway.
_TRACK_LINE = re.compile(r'^\W{0,4}(?P<number>\d{1,3})\s*[\.\)\]]?\s+(?P<body>\S.*\s+-\s+\S.*)$')

# The release header a single's NFO carries instead of a tracklist: "RLS NAME : A & B - Title".
_RELEASE_NAME = re.compile(r'^\W*(?:rls\s*name|release\s*name|title)\W*[:\[]\s*(?P<body>\S.*\s+-\s+\S.*)$', re.I)

# Scene art lines are mostly block characters; a real tracklist line is mostly ASCII letters.
_ASCII_LETTER = re.compile(r'[A-Za-z]')


def _looks_like_text(line):
    """Whether a line is words rather than CP437 block art."""
    stripped = line.strip()
    if len(stripped) < 8:
        return False
    letters = len(_ASCII_LETTER.findall(stripped))
    return letters >= max(6, len(stripped) * 0.35)


def _clean(value):
    """Trim the duration and the decoration scene NFOs pad their columns with."""
    value = _DURATION.sub('', value)
    value = value.replace('\t', ' ')
    value = re.sub(r'\.{2,}', ' ', value)
    value = re.sub(r'\s{2,}', ' ', value)
    return value.strip().strip('|').strip()


def split_artist_and_title(body):
    """`(artist, title)` for one "Artist - Title" body, or None.

    The first " - " separates them. A title may contain further dashes and routinely does
    ("Wake_Up - Extended Mix"), so only the first one can be the separator.
    """
    cleaned = _clean(body)
    parts = cleaned.split(' - ', 1)
    if len(parts) != 2:
        return None
    artist, title = (part.strip() for part in parts)
    if not artist or not title:
        return None
    return (artist, title)


def entries(text):
    """Every `(number, artist, title)` the NFO's tracklist states, in source order.

    `number` is None for a release-header line, which is what a single's NFO carries instead of a
    numbered list.
    """
    found = []
    for line in (text or '').splitlines():
        if not _looks_like_text(line):
            continue
        header = _RELEASE_NAME.match(line)
        if header:
            split = split_artist_and_title(header.group('body'))
            if split:
                found.append((None, *split))
            continue
        match = _TRACK_LINE.match(line)
        if not match:
            continue
        split = split_artist_and_title(match.group('body'))
        if split:
            found.append((int(match.group('number')), *split))
    return found


def split_like_the_tagger(artist_text):
    """The values `CleanTagsRule` would store for this artist string.

    Reuses `Tag` rather than the regex directly, so this cannot drift from what the tagger does.
    """
    tag = Tag(ARTIST, artist_text)
    tag.regex()
    tag.strip()
    tag.deduplicate()
    return tag.to_array()


def _key(values):
    """Order- and case-insensitive identity for a set of artist names."""
    return sorted(value.strip().lower() for value in values if value and value.strip())


def describes_same_artists(nfo_artist, tag_values):
    """Whether an NFO line names exactly the artists the tag already holds.

    This is the guard that makes a backfill safe. Splitting the NFO's wording with the tagger's own
    rule and requiring the same set means a write can only ever restore *wording* -- it can never
    introduce, drop or rename an artist. A line that disagrees is not evidence the tag is wrong; it
    is evidence the line describes some other track, so it is skipped.
    """
    if not nfo_artist or not tag_values:
        return False
    return _key(split_like_the_tagger(nfo_artist)) == _key(tag_values)


def restorable_wording(nfo_artist, tag_values):
    """The NFO's wording when it is worth restoring, else None.

    Worth restoring means: it names the same artists, and it actually says something the stored
    values do not. Re-stating "Eternate;Prosphere" as "Eternate;Prosphere" is not worth a file write.
    """
    if not describes_same_artists(nfo_artist, tag_values):
        return None
    if _clean(nfo_artist) == ';'.join(tag_values):
        return None
    return _clean(nfo_artist)
