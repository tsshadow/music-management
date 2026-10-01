"""Release, series and channel markers in a download's title, read before the artist split.

SoundCloud and YouTube uploads carry more than "Artist - Title". A label's release series
("｜ Q-dance presents SPEQTRUM", "(Gearbox Presents Lockdown 3.0)", "[DRS Presents: TSR
Album 8.0 - TSR042]"), the channel's own name as a last pipe segment ("｜ 101Barz"), and
non-song uploads ("｜ Interview with Rejecta", "｜ Cover by Gabocarina96") all used to reach
InferArtistFromTitleRule's sub-rules whole. Those read the marker as the artist/title split,
so every upload of a series shared one artist and one title -- and song_versions grouped the
whole series as one song (bug report 142, docs/designs/release-series-markers/).

`parse_title_markers` is a pure function: it takes the original title and the channel's
stand-in names and returns what is left to split plus what the markers said. The rule
applies the result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

PIPE_SPLIT = re.compile(r'\s*[｜|]\s*')
EVENT_YEAR = re.compile(r'\b(19[89]\d|20[0-4]\d)\s*$')

# "(Gearbox Presents Lockdown 3.0)", "[DRS Presents： TSR Album 8.0 - TSR042]" at the end.
_BRACKET_PRESENTS = re.compile(
    r'\s*[\(\[]\s*(?P<label>[^()\[\]]+?)\s+presents\b\s*[:：]?\s*(?P<release>[^()\[\]]+?)\s*[\)\]]\s*$',
    re.IGNORECASE,
)
# "(Dungeon： The Mini Album)" at the end: only with a release word after the colon, so
# "(Intro: Part 2)" and the like stay part of the title.
_BRACKET_COLON_RELEASE = re.compile(
    r'\s*[\(\[]\s*(?P<head>[^()\[\]:：]+?)\s*[:：]\s*'
    r'(?P<tail>[^()\[\]]*\b(?:album|ep|lp|compilation|sampler)\b[^()\[\]]*?)\s*[\)\]]\s*$',
    re.IGNORECASE,
)
# "｜ Q-dance presents SPEQTRUM" as the last pipe segment.
_PIPE_PRESENTS = re.compile(
    r'\s*[｜|]\s*(?P<label>[^｜|]+?)\s+presents\b\s*[:：]?\s*(?P<release>[^｜|]+?)\s*$',
    re.IGNORECASE,
)
# "TSR Album 8.0 - TSR042": a catalogue number after the release name.
_RELEASE_CATALOG = re.compile(r'^(?P<name>.+?)\s+-\s+(?P<catalog>[A-Z]{2,}[A-Z0-9]*\d{2,})$')

_INTERVIEW = re.compile(r'^(?P<event>.+?)\s*[｜|]\s*interview with\s+(?P<who>[^｜|]+?)\s*$', re.IGNORECASE)
_COVER = re.compile(r'^(?P<song>.+?)\s*[｜|]\s*cover by\s+(?P<who>[^｜|]+?)\s*$', re.IGNORECASE)
_PREVIEW_WORDS = re.compile(r'\b(preview|trailer|teaser|aftermovie)\b', re.IGNORECASE)

CHANNEL_MATCH_CUTOFF = 0.85


@dataclass(frozen=True)
class TitleMarkers:
    """What the markers in one title said.

    `title` is what the artist sub-rules should split. `album` and `catalog` come from a
    release marker. `artist` and `final_title` are set together for an upload whose
    artist the shape itself names (interview, cover, preview); the sub-rules are then
    skipped.
    """

    title: str
    album: str | None = None
    catalog: str | None = None
    artist: str | None = None
    final_title: str | None = None


def _comparable(name: str) -> str:
    """A name lower-cased with everything but letters and digits removed."""
    return re.sub(r'[\W_]+', '', name.lower())


def is_channel_name(segment: str, channel_names) -> bool:
    """Whether a title segment is the channel's own name, allowing for spelling noise."""
    wanted = _comparable(segment)
    if not wanted:
        return False
    for name in channel_names:
        known = _comparable(name)
        if not known:
            continue
        if wanted == known or SequenceMatcher(None, wanted, known).ratio() >= CHANNEL_MATCH_CUTOFF:
            return True
    return False


def _release(name: str) -> tuple[str, str | None]:
    """The release name and, when one trails it, its catalogue number."""
    name = name.strip()
    match = _RELEASE_CATALOG.match(name)
    if match:
        return match.group('name').strip(), match.group('catalog')
    return name, None


def strip_release_marker(title: str) -> tuple[str, str | None, str | None]:
    """The title without a trailing release marker, plus the release and its catalogue number.

    Unchanged (with None, None) when the title has no such marker, or when stripping it
    would leave nothing.
    """
    for pattern in (_BRACKET_PRESENTS, _PIPE_PRESENTS):
        match = pattern.search(title)
        if match and title[: match.start()].strip():
            album, catalog = _release(match.group('release'))
            return title[: match.start()].strip(), album, catalog
    match = _BRACKET_COLON_RELEASE.search(title)
    if match and title[: match.start()].strip():
        album = f'{match.group("head").strip()}: {match.group("tail").strip()}'
        return title[: match.start()].strip(), album, None
    return title, None, None


def _special_shape(title: str) -> TitleMarkers | None:
    """An interview, cover or preview upload, whose shape says who the artist is."""
    match = _INTERVIEW.match(title)
    if match:
        return TitleMarkers(
            title=title, artist=match.group('who').strip(), final_title=f'{match.group("event").strip()} Interview'
        )
    match = _COVER.match(title)
    if match:
        return TitleMarkers(
            title=title, artist=match.group('who').strip(), final_title=f'{match.group("song").strip()} (Cover)'
        )
    segments = [s for s in PIPE_SPLIT.split(title) if s.strip()]
    if (
        len(segments) >= 3
        and EVENT_YEAR.search(segments[0])
        and all(_PREVIEW_WORDS.search(s) for s in segments[1:-1])
        and not _PREVIEW_WORDS.search(segments[-1])
    ):
        return TitleMarkers(title=title, artist=segments[-1].strip(), final_title=' - '.join(segments[:-1]))
    return None


def strip_channel_segments(title: str, channel_names) -> str:
    """The title without trailing pipe segments that only repeat the channel's name.

    "KAASCOUSE ｜ The Next MC - Optreden ｜ 101Barz" loses "101Barz". When a segment went
    and the first one is already "Artist - Title", what sits between is the channel's
    series name ("Jimmy Huru - #BPMJIMMYHURU ｜ BPM ｜ 101BARZ") and goes too.
    """
    segments = [s for s in PIPE_SPLIT.split(title) if s.strip()]
    dropped = False
    while len(segments) > 1 and is_channel_name(segments[-1], channel_names):
        segments.pop()
        dropped = True
    if not dropped:
        return title
    if len(segments) > 1 and ' - ' in segments[0]:
        return segments[0].strip()
    return ' ｜ '.join(s.strip() for s in segments)


def parse_title_markers(title: str, channel_names=()) -> TitleMarkers:
    """Read every marker out of `title`; see the module docstring."""
    if not title:
        return TitleMarkers(title=title or '')
    names = [name for name in channel_names if isinstance(name, str) and name.strip()]
    special = _special_shape(title)
    if special:
        return special
    stripped, album, catalog = strip_release_marker(title)
    stripped = strip_channel_segments(stripped, names)
    return TitleMarkers(title=stripped, album=album, catalog=catalog)
