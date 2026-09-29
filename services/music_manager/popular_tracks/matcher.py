"""Tie an external top-list title to a library track of the same artist. Pure, no database.

The keys are the scrobble matcher's own (`scrobble_matching.normalize` and `base_title`),
the same ones `library_tracks.normalized_title` / `normalized_base_title` are filled with, so
"Pennywise (Radio Edit)" on Last.fm finds "Pennywise" in the library the way a listen would.
One more, looser key is tried last: the title with *every* bracketed group removed, because
the external catalogues decorate hits with the context they became hits in -- "Scrap Attack
(Defqon.1 2009 anthem)" -- which is not a version marker and which `base_title` keeps on
purpose.

Only tracks already credited to the crawled artist are candidates, so a loose key can at
worst pick the wrong *version* of that artist's song, never somebody else's song. Which
version is stored does not matter much: the feed reads the song (work) through it and
plays the work's canonical. The one stored is that canonical when it matched, else the
lowest track id, so the choice is stable between runs.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from services.music_manager.scrobble_matching import base_title, normalize

_BRACKETS = re.compile(r'\s*[\(\[][^\(\)\[\]]*[\)\]]')


def strip_brackets(title: str | None) -> str:
    """`title` with every parenthesised or bracketed group removed."""
    if not title:
        return ''
    previous = None
    stripped = title
    # Nested groups ("(Defqon.1 (2009) anthem)") collapse from the inside out.
    while previous != stripped:
        previous = stripped
        stripped = _BRACKETS.sub('', stripped)
    return stripped.strip()


def title_keys(title: str | None) -> list[str]:
    """The keys a title is looked up by, strictest first, without empties or repeats."""
    keys: list[str] = []
    for key in (normalize(title), normalize(base_title(title)), normalize(strip_brackets(title))):
        key = key[:191]
        if key and key not in keys:
            keys.append(key)
    return keys


@dataclass(frozen=True)
class LibraryTrack:
    """The few fields of a library track the matcher needs."""

    id: int
    track_uid: str
    title: str | None
    work_id: int | None = None
    canonical_track_id: int | None = None


@dataclass(frozen=True)
class Match:
    """The library track an external title matched, and the key strictness it matched at (0 = exact)."""

    track: LibraryTrack
    strictness: int


class ArtistIndex:
    """One artist's library tracks, indexed by every key of their titles."""

    def __init__(self, tracks: Iterable[LibraryTrack]):
        # key -> tracks, per strictness level of the *library* side too: a library title
        # matched on its exact key beats one matched only once its brackets are gone.
        self._by_key: dict[str, list[LibraryTrack]] = {}
        for track in tracks:
            for key in title_keys(track.title):
                self._by_key.setdefault(key, []).append(track)

    def match(self, external_title: str) -> Match | None:
        """The best library track for `external_title`, or None when no key hits."""
        for strictness, key in enumerate(title_keys(external_title)):
            candidates = self._by_key.get(key)
            if candidates:
                return Match(_preferred(candidates), strictness)
        return None


def _preferred(candidates: list[LibraryTrack]) -> LibraryTrack:
    """The work's canonical when it is among the candidates, else the lowest id."""
    for track in candidates:
        if track.canonical_track_id is not None and track.id == track.canonical_track_id:
            return track
    return min(candidates, key=lambda track: track.id)
