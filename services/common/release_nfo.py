"""What a scene release's .nfo says about the release: label, catalogue number, store links.

Scene groups lay their .nfo out in one or two columns of dot-padded `Key: value` pairs, in
CP437 block art, and every group spells the keys its own way. Sampled on production on
2026-10-02 (6.546 .nfo files in the import queue, files containing the key):

    label 4.530, company 1.344        -> the record label (5.849 usable)
    catalognr 2.802, catalog 45       -> the catalogue number (2.736 pass the test below)
    url 5.607                         -> an album link: Deezer 4.514, Beatport 1.482, Qobuz 118,
                                         Tidal 81; no Spotify or iTunes
    ripdate 367, date 130, releasedate 78, rlsdate 36, streetdate 13, storedate 10, ...

The Minus Militia release reads, two pairs to a line:

    Rip.date: 01.10.2026                Year....: 2026
    Company.: B2S                       Length..: 03:24
    Url:https://deezer.com/album/1104265012

Reading is pure: `parse(text)` takes the decoded text, `read(directory)` finds and decodes the
file. The dates are left to `services.tagger.Song.NfoDate`, which already resolves the day/month
order per scene group.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field

from services.common.catalogue_number import is_catalogue_number

#: Normalised keys (lowercase letters only) that name the record label, most specific first.
LABEL_KEYS = ('label', 'recordlabel', 'labelname', 'company', 'publisher')
#: Normalised keys that name the catalogue number.
CATALOGUE_KEYS = ('catalognr', 'catalognumber', 'catalogno', 'catalog', 'catno', 'catnr', 'catalogue', 'catalogueno')

#: Values a key carries when the group had nothing to put there.
EMPTY_VALUES = frozenset({'', 'n/a', 'na', 'none', 'null', 'unknown', '-', '--', '?', 'tba', 'not available'})

# One `Key....: value` pair. A key is a few words; the value runs to the end of the line or to
# the next key in a second column, which is set off by three or more spaces.
_KEY = r'[A-Za-z][A-Za-z\- /#]{0,18}?[A-Za-z#]'
_PAIR = re.compile(r'(?:(?<=\s)|^)(' + _KEY + r')[ .]*:[ ]*(\S.*?)(?=\s{3,}' + _KEY + r'[ .]*:|[ \t]*$)', re.M)
_URL = re.compile(r'(?:https?://|www\.)[^\s"\'<>]+', re.I)
_DEEZER_ALBUM = re.compile(r'deezer\.com/(?:[a-z]{2}(?:-[a-z]{2})?/)?album/(\d+)', re.I)
_BEATPORT_RELEASE = re.compile(r'beatport\.com/(?:[a-z]{2}/)?release/[^/\s]+/(\d+)', re.I)
_QOBUZ_ALBUM = re.compile(r'qobuz\.com/(?:[a-z]{2}-[a-z]{2}/)?album/(?:[^/\s]+/)?([a-z0-9]+)\b', re.I)
_TIDAL_ALBUM = re.compile(r'tidal\.com/(?:browse/)?album/(\d+)', re.I)
#: Bytes block art is drawn with; a value made of them is decoration, not data.
_ART = re.compile('[\u2500-\u259f]')
# A catalogue line without the colon `_PAIR` needs: `CAT NR..[ BIR030`, `Catalognr....:: PR096`,
# after any box-drawing border. The same pattern as catalogue_tag_mismatch.py.
_CATALOGUE_LINE = re.compile(
    r'^[^A-Za-z]*(?:cat(?:alog(?:ue)?)?[ .]*(?:nr|no|number|num|#)?|catnumber|catalognr)\.?'
    r'[ .:\[\]]*[:.\[][ .:\[\]]*([A-Za-z0-9][A-Za-z0-9_.\-]*)',
    re.I,
)


@dataclass(frozen=True)
class StoreLink:
    """One album page at a store, as `(store, id)` plus the URL it was read from."""

    store: str
    album_id: str
    url: str


@dataclass(frozen=True)
class NfoInfo:
    """The release facts one .nfo states. Every field may be missing."""

    label: str | None = None
    label_key: str | None = None
    catalogue_number: str | None = None
    links: tuple[StoreLink, ...] = field(default_factory=tuple)
    text: str = ''

    def link(self, store: str) -> StoreLink | None:
        """The first link to `store`, or None."""
        return next((link for link in self.links if link.store == store), None)


def normalise_key(key: str) -> str:
    """A key as lowercase letters only: `Catalog Nr.` -> `catalognr`."""
    return re.sub(r'[^a-z]', '', key.lower())


def _clean(value: str) -> str | None:
    text = _ART.split(value)[0].strip().strip(' .:')
    text = re.sub(r'\s{2,}', ' ', text)
    return None if text.lower() in EMPTY_VALUES else text


def pairs(text: str) -> list[tuple[str, str]]:
    """Every `(normalised key, value)` pair in `text`, in reading order, values cleaned."""
    found = []
    for match in _PAIR.finditer(text or ''):
        value = _clean(match.group(2))
        if value:
            found.append((normalise_key(match.group(1)), value))
    return found


def links(text: str) -> tuple[StoreLink, ...]:
    """Every store album link in `text`, without repeats."""
    found: list[StoreLink] = []
    for url in _URL.findall(text or ''):
        for store, pattern in (
            ('deezer', _DEEZER_ALBUM),
            ('beatport', _BEATPORT_RELEASE),
            ('qobuz', _QOBUZ_ALBUM),
            ('tidal', _TIDAL_ALBUM),
        ):
            match = pattern.search(url)
            if match and all(link.album_id != match.group(1) or link.store != store for link in found):
                found.append(StoreLink(store, match.group(1), url.rstrip('.,)')))
    return tuple(found)


def nfo_catalogue_number(value: str | None) -> str | None:
    """A catalogue number as an .nfo states it, or None when it is not one.

    Stricter than the folder-name rule: it must hold a letter too. A purely numeric value in an
    .nfo is a UPC or a distributor id (`10368151`), never what a label prints on the sleeve.
    """
    text = re.sub(r'\s+', '', value or '')
    if not is_catalogue_number(text) or not re.search(r'[A-Za-z]', text):
        return None
    return text


def parse(text: str) -> NfoInfo:
    """The release facts in one decoded .nfo text."""
    found = pairs(text)
    label = label_key = catalogue = None
    for wanted in LABEL_KEYS:
        value = next((value for key, value in found if key == wanted), None)
        if value:
            label, label_key = value, wanted
            break
    for wanted in CATALOGUE_KEYS:
        value = next((value for key, value in found if key == wanted), None)
        catalogue = nfo_catalogue_number(value)
        if catalogue:
            break
    return NfoInfo(label, label_key, catalogue, links(text), text or '')


def stated_catalogue_number(text: str) -> str | None:
    """The catalogue number an .nfo states, in a `Key: value` pair or on a line of its own, or None.

    `parse` reads only the pairs with a colon. Some groups write `CAT NR..[ BIR030` instead,
    so a line that starts with a catalogue key is the fallback. Either value must pass
    `nfo_catalogue_number`.
    """
    found = parse(text).catalogue_number
    if found:
        return found
    for line in (text or '').splitlines():
        match = _CATALOGUE_LINE.match(line)
        if match:
            value = nfo_catalogue_number(match.group(1).strip(' .'))
            if value:
                return value
    return None


def decode(raw: bytes) -> str:
    """Scene .nfo bytes as text: CP437 block art with stray NUL bytes."""
    return raw.replace(b'\x00', b'').decode('cp437', errors='replace')


def read(directory: str) -> NfoInfo | None:
    """The facts of the first .nfo directly inside `directory`, or None when there is none."""
    try:
        names = sorted(name for name in os.listdir(directory) if name.lower().endswith('.nfo'))
    except OSError as exc:
        logging.debug('No .nfo listing for %s: %s', directory, exc)
        return None
    for name in names:
        try:
            with open(os.path.join(directory, name), 'rb') as handle:
                return parse(decode(handle.read(256 * 1024)))
        except OSError as exc:
            logging.debug('Could not read %s: %s', name, exc)
    return None
