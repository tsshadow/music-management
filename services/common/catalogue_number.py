"""Whether a piece of a release folder's name is a catalogue number (bug report 145).

The Renamer used to take the last parenthesised group holding a digit, so a scene name like
`Minus_Militia_And_Nolz_-_Recover_The_Archive_(Official_Hardbass_2026_Anthem)_(Edit)-...`
gave `Official_Hardbass_2026_Anthem` as its catalogue number, and the release could never
reach a label folder. This module is the one place that decides what a catalogue number
looks like, so the Renamer, the repair of the folders it misnamed and the importer's
release-info lookup all apply the same test.

The rule is derived from production on 2026-10-02, not from guesses: of the 21.408 label
folders whose prefix is the group the old Renamer picked, it rejects none. In `__TODO` it
rejects 96 prefixes, every one of them a festival anthem, an edit or remix marker, a
`Volume_1`, or prose (`I_Made_This_Song_In_1_Hour_While_I_Was_Pooping`). A catalogue
number:

* is 2 to 24 characters long (the longest in the label tree is 21);
* is ASCII letters and digits, optionally in parts joined by `.`, `_` or `-`
  (`CR.109`, `ISRD_233`, `BF_-_189`, `GH-GOLD041`) -- no spaces, no other characters;
* holds at least one digit, and is not a bare year (`2026`);
* has no part that is a word a title uses (`Official`, `Anthem`, `Edit`, `Remix`, `Mix`,
  `Extended`, `Volume`, ... -- `WORDS` below), also not with digits glued on (`Anthem26`);
* when it has several parts, writes every word in them in capitals: `GGM_RAW_001` and
  `DSB_REC_028` are catalogue numbers, `Cenobite_Digital_52` and `Equal2_Remix` are
  words. A single part may mix case (`NOxEVO004`, `TOFF087d`, `Fusion250`);
* has at most four parts.
"""

from __future__ import annotations

import re

#: Words a release title uses next to a number; never part of a catalogue number. Compared
#: case-insensitively against each part, and against a part's leading letters when digits
#: are glued on (`Anthem26`), the latter only for words of three letters or more.
WORDS = frozenset(
    {
        'acapella',
        'and',
        'anniversary',
        'anthem',
        'bootleg',
        'clip',
        'cut',
        'dub',
        'edit',
        'edition',
        'edits',
        'extended',
        'feat',
        'festival',
        'flip',
        'ft',
        'instrumental',
        'intro',
        'live',
        'mix',
        'of',
        'official',
        'original',
        'ost',
        'outro',
        'part',
        'pt',
        'radio',
        'refix',
        'remake',
        'remaster',
        'remastered',
        'remix',
        'remixes',
        'rework',
        'sampler',
        'soundtrack',
        'the',
        'theme',
        'version',
        'vinyl',
        'vip',
        'vol',
        'volume',
        'year',
        'years',
    }
)

MIN_LENGTH = 2
MAX_LENGTH = 24
MAX_PARTS = 4

_SHAPE = re.compile(r'[A-Za-z0-9]+(?:[._\-]+[A-Za-z0-9]+)*')
_PART_SPLIT = re.compile(r'[._\-]+')
_YEAR = re.compile(r'(?:19|20)\d\d')
_LEADING_LETTERS = re.compile(r'[A-Za-z]*')
_PAREN_GROUP = re.compile(r'\((.*?)\)')


def rejection(value: str | None) -> str | None:
    """Why `value` is not a catalogue number, or None when it is one.

    The reason is a short tag (`length`, `chars`, `no-digit`, `year`, `word:<part>`,
    `cased-words`, `parts`) so a dry run can count the rejections by kind.
    """
    text = (value or '').strip()
    if len(text) < MIN_LENGTH:
        return 'length'
    if not _SHAPE.fullmatch(text):
        return 'chars'
    if not any(char.isdigit() for char in text):
        return 'no-digit'
    if _YEAR.fullmatch(text):
        return 'year'
    parts = [part for part in _PART_SPLIT.split(text) if part]
    for part in parts:
        letters = _LEADING_LETTERS.match(part).group(0).lower()
        if part.lower() in WORDS or (len(letters) >= 3 and letters in WORDS):
            return f'word:{part}'
    if len(parts) > 1 and any(re.search(r'[a-z]', part) and re.search(r'[A-Za-z]{2,}', part) for part in parts):
        return 'cased-words'
    if len(parts) > MAX_PARTS:
        return 'parts'
    if len(text) > MAX_LENGTH:
        return 'length'
    return None


def is_catalogue_number(value: str | None) -> bool:
    """Whether `value` looks like a real catalogue number; see the module docstring."""
    return rejection(value) is None


def from_folder_name(folder: str) -> str | None:
    """The catalogue number a release folder's name carries, or None.

    The last parenthesised group that passes `is_catalogue_number`, searched from the back
    because scene names put the catalogue number after the title and its version markers:
    `Artist_-_Title_(Extended_Mix)-(BRUT016D)-WEB-2026`.
    """
    for group in reversed(_PAREN_GROUP.findall(folder)):
        if is_catalogue_number(group):
            return group.strip()
    return None


def old_rule_prefix(folder: str) -> str | None:
    """What the Renamer before bug report 145 took as the catalogue number of `folder`.

    The last parenthesised group with a digit in it. Kept so the repair can tell a prefix
    that Renamer produced -- and may undo -- from one a person typed.
    """
    for group in reversed(_PAREN_GROUP.findall(folder)):
        if any(char.isdigit() for char in group):
            return group
    return None
