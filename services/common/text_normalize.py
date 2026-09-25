"""Name keys shared by the tagger, the curation pages and the detectors.

Several modules need "the same name, spelled differently" to compare equal. They do not
all mean the same thing by it, so this module offers named variants rather than one
`normalize()`, and each call site picks the one whose behaviour it had before
(docs/bug-reports/084-unused-endpoints-and-duplicate-normalizers.md). The characterisation
table in `text_normalizeTest.py` pins every variant, and every normalizer that stayed
separate, on the same tricky inputs.

| Variant / implementation                | Case    | Accents | Non-Latin | Punctuation, `&`, `_` | "feat."  |
|-----------------------------------------|---------|---------|-----------|-----------------------|----------|
| `ascii_name_key` (genres, shows)        | lower   | folded  | dropped   | separator             | kept     |
| `padded_ascii_name_key` (festivals, ...) | as above, wrapped in single spaces for word-bounded `in` tests                          |
| `unicode_name_key` (artists)            | lower   | folded  | kept      | separator             | kept     |
| `scrobble_matching.normalize`           | casefold| folded  | kept      | separator, `_` kept, intra-word `'`/`.` deleted | folded to `&` |
| `ArtistNameNormalizer.normalize`        | lower   | kept    | kept      | only `_`/`-` spaced   | kept     |

No variant strips a leading "The" -- `ArtistNameNormalizer.get_sort_name` is the only
place that treats it specially, for sorting. Letters NFKD cannot decompose (`Ø`, `ß`,
`Đ`) are not folded to ASCII by any variant: the ASCII key drops them, the Unicode key
keeps them.

Deliberately free of imports beyond the standard library, so a module that must not pull in
a database driver (`GenreNameAnalyzer`) can use it.
"""

import re
import unicodedata

_NON_ASCII_ALNUM = re.compile('[^a-z0-9]+')
_WHITESPACE = re.compile(r'\s+')


def _strip_accents(text: str | None) -> str:
    """NFKD-decomposed text with the combining marks removed."""
    decomposed = unicodedata.normalize('NFKD', text or '')
    return ''.join(c for c in decomposed if not unicodedata.combining(c))


def ascii_name_key(text: str | None) -> str:
    """Casing-, accent- and punctuation-insensitive key over `a-z0-9`.

    The genre key: the tagger (`GenreRulesHelper`), the curation page, the genre analyzer,
    the podcast detector and `normalizeGenre` in the frontend all group names by it, and the
    podcast rules store it in `normalized_name`. Every other character -- including letters
    outside ASCII after accent folding -- becomes a single space.
    """
    return _NON_ASCII_ALNUM.sub(' ', _strip_accents(text).lower()).strip()


def padded_ascii_name_key(text: str | None) -> str:
    """`ascii_name_key` wrapped in single spaces, so a substring test only matches whole words."""
    return f' {ascii_name_key(text)} '


def unicode_name_key(text: str | None) -> str:
    """Like `ascii_name_key`, but alphanumeric is decided per character, in any script.

    The artist key. The library holds Cyrillic artists, and an ASCII-only key would collapse
    every one of them to the empty string -- indistinguishable from a name of pure
    punctuation. Genres keep the ASCII key because that is what their stored rows and the
    frontend were built on.
    """
    kept = ''.join(c if c.isalnum() else ' ' for c in _strip_accents(text).lower())
    return _WHITESPACE.sub(' ', kept).strip()
