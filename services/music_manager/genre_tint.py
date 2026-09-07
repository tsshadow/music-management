"""The colour a genre is drawn in, decided once so every client agrees.

The web UI and the mobile app both draw a genre as a coloured tile. If each carried its own table,
Hardstyle would eventually be orange in one and magenta in the other -- a difference nobody notices
until both are open next to each other, and one nobody can test for. The colour therefore travels
with the genre in the API response, and neither client owns a table.

The genres this collection is actually built on get a chosen colour, because a hash lands wherever
it lands and Hardstyle deserves the orange of the festivals it comes from. Everything else is
derived from the name, so a genre added tomorrow needs no code change.
"""

import colorsys
import hashlib

# Chosen rather than derived. Keep this short: it is the genres that carry the collection, not a
# catalogue. Anything absent falls through to the derivation below and looks fine.
NAMED_TINTS = {
    'hardstyle': '#ff4d00',
    'rawstyle': '#ff2e00',
    'hardcore': '#e5002b',
    'uptempo': '#ff0059',
    'techno': '#00e0c7',
    'trance': '#7b2dff',
    'house': '#ffb400',
    'drum and bass': '#00ff85',
    'dubstep': '#00b3ff',
}

# What a blank name gets. A tile without a colour reads as broken; a tile in the neutral one does
# not.
FALLBACK_TINT = '#8a8a8a'

# The derived colours vary in hue only. Saturation and value are pinned high so the genre name,
# which is printed in near-black over the tint, stays readable whatever hue comes out.
_DERIVED_SATURATION = 0.82
_DERIVED_VALUE = 0.95


def genre_tint(name: str | None) -> str:
    """The hex colour for a genre name, as ``#rrggbb``."""
    key = (name or '').strip().lower()
    if not key:
        return FALLBACK_TINT

    named = NAMED_TINTS.get(key)
    if named:
        return named

    return _derive(key)


def _derive(key: str) -> str:
    # blake2b rather than hash(): CPython salts str hashing per process, so the same genre would
    # get a different colour after every restart and the clients' caches would disagree.
    digest = hashlib.blake2b(key.encode('utf-8'), digest_size=8).digest()
    hue = int.from_bytes(digest, 'big') % 360 / 360
    red, green, blue = colorsys.hsv_to_rgb(hue, _DERIVED_SATURATION, _DERIVED_VALUE)
    return f'#{round(red * 255):02x}{round(green * 255):02x}{round(blue * 255):02x}'
