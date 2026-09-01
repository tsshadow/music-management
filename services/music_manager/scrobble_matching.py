"""Deciding whether two spellings of a listen mean the same track.

Pure functions, no database. Everything that touches SQL lives in
scrobble_rematch.py, so the rules here can be pinned down by ordinary unit tests
rather than against a fixture -- which matters, because the bug this exists to
fix was invisible to a mocked cursor.

Design and measurements: docs/superpowers/specs/2026-08-21-scrobble-rematching-design.md
"""

from __future__ import annotations

import difflib
import enum
import re
import unicodedata

# Any of these, standing alone between two names, means the same thing.
_FEATURING = re.compile(
    r'\s+(?:feat\.?|ft\.?|featuring|&|x|vs\.?|with)\s+',
    re.IGNORECASE,
)

# A trailing parenthesised or bracketed group whose contents name a version of
# the same recording rather than part of the title.
_VERSION_SUFFIX = re.compile(
    r'\s*[\(\[][^\(\)\[\]]*\b(?:remix|mix|edit|extended|radio|version|vip|bootleg|rework|'
    r'dub|instrumental|acapella|remaster(?:ed)?)\b[^\(\)\[\]]*[\)\]]\s*$',
    re.IGNORECASE,
)

# Marks that sit *inside* a word are deleted rather than spaced, so "Don't"
# matches "Dont"; everything else becomes a separator.
_INTRA_WORD = re.compile(r"(?<=\w)['\u2019\u02bc.](?=\w)", re.UNICODE)
_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r'\s+')


class MatchTier(enum.Enum):
    """The ladder, in the order it is tried. Order here is the order of attempt."""

    EXACT = 'exact'
    NORMALIZED = 'normalized'
    BASE_TITLE = 'base_title'
    FUZZY = 'fuzzy'


_LADDER = [MatchTier.EXACT, MatchTier.NORMALIZED, MatchTier.BASE_TITLE, MatchTier.FUZZY]


def normalize(text: str | None) -> str:
    """Fold away everything that is spelling rather than identity.

    Case, accents, punctuation and the many ways of writing "featuring" all go.
    What survives is still the same track by the same artist -- this tier cannot
    invent a wrong answer, only find a right one that was written differently.
    """
    if not text:
        return ''

    folded = unicodedata.normalize('NFKD', text)
    folded = ''.join(char for char in folded if not unicodedata.combining(char))

    # Before punctuation is stripped, or "feat." and "ft." stop being findable.
    folded = _FEATURING.sub(' & ', folded)

    folded = _INTRA_WORD.sub('', folded)
    folded = _PUNCTUATION.sub(' ', folded)
    folded = _WHITESPACE.sub(' ', folded)
    return folded.strip().casefold()


def base_title(title: str | None) -> str:
    """The title with a trailing version marker removed.

    Deliberately conservative: only a bracketed group that actually names a
    version counts, so "Track (Part 1)" keeps its brackets. Even so this tier
    changes what a listen means -- a remix is a different recording, with a
    different tempo and often a different genre -- which is why it is a tier of
    its own, recorded separately and switchable off.
    """
    if not title:
        return ''
    return _VERSION_SUFFIX.sub('', title).strip()


def similarity(left: str, right: str) -> int:
    """How alike two already-normalized strings are, 0-100.

    difflib rather than a dependency: it is in the standard library and carries
    the cheap pre-filters this needs. It is only ever called inside a candidate
    set narrowed by an exact key -- see the spec -- because comparing every
    listen against every track is ten billion comparisons.
    """
    if not left or not right:
        return 0

    matcher = difflib.SequenceMatcher(None, left, right)
    # Both are upper bounds on ratio() and cost almost nothing, so a candidate
    # that cannot reach the threshold is rejected before the real comparison.
    if matcher.real_quick_ratio() < 0.5 or matcher.quick_ratio() < 0.5:
        return int(round(matcher.quick_ratio() * 100))
    return int(round(matcher.ratio() * 100))


def enabled_tiers(setting: str | None) -> list[MatchTier]:
    """The tiers to try, in ladder order.

    Ladder order, not the order they were listed in: the tiers are ranked by how
    much they can get wrong, and letting a setting reorder them would let fuzzy
    answer before exact had its turn. An unknown name is ignored rather than
    raised -- this is read by a background worker, and a typo in a setting should
    not stop it linking anything at all.
    """
    if setting is None:
        return list(_LADDER)

    wanted = {part.strip().lower() for part in setting.split(',') if part.strip()}
    return [tier for tier in _LADDER if tier.value in wanted]
