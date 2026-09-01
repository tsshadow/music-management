"""Reads the release date a scene NFO states, at day precision where the evidence allows.

Label rips arrive tagged with a year and nothing more, but the NFO that ships inside the release
directory usually states an exact date. The parsing lives here rather than in the rule that uses it,
so every branch of the order resolution can be tested without a song, a file or a database.
"""

import logging
import os
import re
from datetime import date

# The two non-year components, in written order. A group's override says which of them is the day.
DAY_MONTH = 'dm'
MONTH_DAY = 'md'

_TOKEN = r'(\d{1,4}[-./]\d{1,2}[-./]\d{1,4})'

# Label spellings seen across the library, most authoritative first. A street date is the official
# release; a rip date is when the group encoded it, usually the same week and occasionally weeks off.
_LABEL_PATTERNS = (
    ('street', re.compile(r'(?:str\.?\s*date|street\s*date)\W{0,10}' + _TOKEN, re.I)),
    ('release', re.compile(r'rel(?:ease)?\.?\s*date\W{0,10}' + _TOKEN, re.I)),
    ('rip', re.compile(r'(?:rip\.?\s*date|ripped|encoded|\bdate\b)\W{0,10}' + _TOKEN, re.I)),
)

# A four-digit year that is not part of a longer run of digits, so a catalogue number like
# AVR2026006BP does not read as a year.
_YEAR = re.compile(r'(?<!\d)(19[7-9]\d|20[0-3]\d)(?!\d)')
_SCENE_GROUP = re.compile(r'-(19[7-9]\d|20[0-3]\d)-([A-Za-z0-9_]+)$')


def read_nfo(directory):
    """The text of the NFO in `directory`, or None.

    Scene NFOs are CP437 block art with embedded NUL bytes, so they are neither valid UTF-8 nor
    clean text. Both problems are handled here so no caller has to know.
    """
    try:
        names = sorted(name for name in os.listdir(directory) if name.lower().endswith('.nfo'))
    except OSError as exc:
        logging.debug('No NFO listing for %s: %s', directory, exc)
        return None
    for name in names:
        try:
            with open(os.path.join(directory, name), 'rb') as handle:
                return handle.read().replace(b'\x00', b'').decode('latin-1')
        except OSError as exc:
            logging.debug('Could not read NFO %s: %s', name, exc)
    return None


def dirname_year(dirname):
    """The release year stated in a release directory name, or None.

    The last year wins: a catalogue number or an event name can carry an earlier one, while the
    release year sits at the end of the scene naming convention.
    """
    years = _YEAR.findall(dirname or '')
    return int(years[-1]) if years else None


def scene_group(dirname):
    """The scene group that released it, taken from the token after the year, or None."""
    match = _SCENE_GROUP.search(dirname or '')
    return match.group(2) if match else None


def date_tokens(text):
    """Every labelled date token as `(kind, token)`, in source-precedence order."""
    tokens = []
    for kind, pattern in _LABEL_PATTERNS:
        tokens.extend((kind, match.group(1)) for match in pattern.finditer(text or ''))
    return tokens


def _candidate_orders(first, second, year_first, order):
    """`(day, month)` pairs to try, best first.

    A component above 12 can only be the day, whatever any table says, so that case answers on its
    own. Otherwise the group's override wins, and the positional default is the fallback: a
    year-first token is month-then-day, a year-last token is day-then-month. The rejected order is
    still offered as a second candidate, so an impossible calendar date falls back rather than
    discarding a date that is really there.
    """
    if first > 12 and second <= 12:
        return [(first, second)]
    if second > 12 and first <= 12:
        return [(second, first)]
    if first > 12 and second > 12:
        return []
    if order == MONTH_DAY:
        preferred = (second, first)
    elif order == DAY_MONTH:
        preferred = (first, second)
    else:
        preferred = (second, first) if year_first else (first, second)
    alternative = (second, first) if preferred == (first, second) else (first, second)
    return [preferred, alternative]


def resolve_token(token, order=None):
    """A `date` for one token, or None if no reading of it is a real calendar date."""
    parts = re.split(r'[-./]', token)
    if len(parts) != 3:
        return None
    year_first = len(parts[0]) == 4
    year_last = len(parts[2]) == 4
    if year_first == year_last:
        return None
    year = int(parts[0]) if year_first else int(parts[2])
    first, second = (int(parts[1]), int(parts[2])) if year_first else (int(parts[0]), int(parts[1]))
    for day, month in _candidate_orders(first, second, year_first, order):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    return None


def resolve(text, dirname, order=None):
    """`(kind, date)` for the best NFO date that agrees with the directory name's year.

    Without a year in the directory name there is nothing to check a candidate against, so nothing
    is returned: an unguarded rip date is how a 1995 vinyl rip becomes a 2024 release.
    """
    expected_year = dirname_year(dirname)
    if expected_year is None:
        return (None, None)
    for kind, token in date_tokens(text):
        resolved = resolve_token(token, order)
        if resolved is not None and resolved.year == expected_year:
            return (kind, resolved)
    return (None, None)
