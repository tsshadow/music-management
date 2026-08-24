"""Which recordings are the same song, and which of them plays.

Separate from scrobble_matching.py on purpose. That module answers "is this listen
about this track", and its base_title() strips `remix` and `bootleg` along with
`edit` -- correct there, ruinous here, because it would merge a remix into the
original and remove it from the library.

Pure functions, no database. The worker owns the SQL.

Design: docs/superpowers/specs/2026-08-23-song-versions-and-canonical-design.md
"""
from __future__ import annotations

import re

from services.music_manager.scrobble_matching import normalize

# Words that describe a length or a packaging of the same recording. A bracketed
# group made only of these is a version marker; one containing anything else
# contains a name, and a name means a different recording.
#
# remix, bootleg, vip, rework, mashup and flip are deliberately absent: those are
# songs of their own and must never group.
_MODIFIER_TOKENS = frozenset({
    'radio', 'extended', 'original', 'album', 'club', 'short', 'full', 'long',
    'edit', 'mix', 'version', 'cut',
    'official', 'video', 'videoclip', 'clip', 'visualizer', 'visualiser', 'lyric', 'lyrics',
    'free', 'download', 'hq', 'hd', 'out', 'now', 'preview',
    'remaster', 'remastered', 'master',
    'instrumental', 'acapella', 'accapella', 'dub',
})

_TRAILING_BRACKET = re.compile(r'\s*[\(\[]([^\(\)\[\]]*)[\)\]]\s*$')
_TOKEN_SPLIT = re.compile(r'[^\w]+', re.UNICODE)

# Ranking order for tier two, best first. `none` sits between original and extended:
# an unmarked official single is usually the radio cut, an unmarked album track is
# the album version, and either beats an extended mix.
KIND_ORDER = ('radio', 'edit', 'original', 'none', 'extended', 'instrumental')

# Checked in this order, so "Radio Instrumental" is instrumental (never canonical)
# and "Radio Edit" is radio rather than edit.
_KIND_MARKERS = (
    ('instrumental', ('instrumental', 'acapella', 'accapella', 'dub')),
    ('radio', ('radio',)),
    ('extended', ('extended',)),
    ('original', ('original',)),
    ('edit', ('edit',)),
)

WORK_KEY_MAX = 191


def _tokens(text: str) -> list[str]:
    return [token for token in _TOKEN_SPLIT.split(text.lower()) if token]


def _strip_version_brackets(title: str) -> tuple[str, list[str]]:
    """The title without its version markers, plus the tokens that were removed."""
    stripped: list[str] = []
    result = title
    while True:
        match = _TRAILING_BRACKET.search(result)
        if not match:
            break
        tokens = _tokens(match.group(1))
        if not tokens or not all(token in _MODIFIER_TOKENS for token in tokens):
            break
        stripped.extend(tokens)
        result = result[:match.start()].strip()
    return result, stripped


def version_free_title(title: str | None) -> str:
    """The normalized title with every version marker removed.

    A bracketed group goes only when all of its tokens are known modifiers, so
    "(Radio Edit)" goes and "(Wildstylez Edit)" stays even though both say "edit".
    """
    if not title:
        return ''
    result, _ = _strip_version_brackets(title)
    return normalize(result)


def version_kind(title: str | None) -> str:
    """Which length of the recording this is: one of KIND_ORDER."""
    if not title:
        return 'none'
    _, stripped = _strip_version_brackets(title)
    for kind, markers in _KIND_MARKERS:
        if any(marker in stripped for marker in markers):
            return kind
    return 'none'


def work_key(artist: str | None, title: str | None) -> str:
    """The grouping key: one song by one artist, however its versions are spelled."""
    return f'{normalize(artist)}:::{version_free_title(title)}'[:WORK_KEY_MAX]
