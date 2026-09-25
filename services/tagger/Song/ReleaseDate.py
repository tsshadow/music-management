"""The one release date a song gets shown as.

The tagger keeps two: DATE is what the file arrived with -- for a download that is
yt-dlp's `upload_date`, an undelimited `20260903` -- while ORIGINALDATE is the release
date the tagger resolved, from the scene NFO for a label rip. Which of the two is the
real one differs per source, so the choice is made by precision rather than by rank.

The rule is the web UI's and the app's, deliberately: services/frontend/src/lib/trackDate.js
and services/muma-mobile/.../util/TrackDateFormatter.kt already decide it this way, and
three clients disagreeing about the date of one track is worse than any single choice.
"""

import re

_ISO_LIKE = re.compile(r'\D')
_UNDELIMITED = re.compile(r'(\d{4})(\d{2})(\d{2})')
_YEAR_ONLY = re.compile(r'\d{4}')


def precision(value) -> int:
    """Digits in a date string, as a stand-in for how precise it is."""
    return len(_ISO_LIKE.sub('', str(value or '')))


def preferred_release_date(date, original_date):
    """The more meaningful of the two dates -- but only when it is at least as precise.

    A bare `2024` in ORIGINALDATE must not throw away a full date DATE does carry.
    """
    preferred = original_date if precision(original_date) >= precision(date) else date
    return preferred or date


def format_release_date(value) -> str | None:
    """A date as `DD-MM-YYYY`, the bare year when that is all the precision there is.

    Accepts every shape the tagger stores: `2026-09-03`, an ISO timestamp, and the
    undelimited `20260903` that yt-dlp's `upload_date` arrives as. None when there is no
    usable year, so a caller can leave the line out entirely.
    """
    digits = _ISO_LIKE.sub('', str(value or '').split('T')[0])
    if len(digits) < 4:
        return None
    year, month, day = (digits[0:4], digits[4:6], digits[6:8])
    # A scene tag of `2026-00-00` is eight digits of nothing but a year, and printing it
    # back as "00-00-2026" is worse than admitting the month and day were never there.
    if len(digits) >= 8 and month != '00' and day != '00':
        return f'{day}-{month}-{year}'
    return year


def iso_date(value) -> str | None:
    """yt-dlp's `20260831` as `2026-08-31`; None for anything that is not a full date.

    A zero month or day is not a date, so a partial one stays None and the caller keeps
    whatever it had.
    """
    match = _UNDELIMITED.fullmatch(str(value or '').strip())
    if not match:
        return None
    year, month, day = match.groups()
    if month == '00' or day == '00':
        return None
    return f'{year}-{month}-{day}'


def completed_date(current, upload_date) -> str | None:
    """The full upload date to replace a year-only `current` with, or None to keep it.

    Only when `current` is a bare year and the upload date falls in that same year: that
    is exactly what an ID3v2.3 rewrite leaves of the date the downloader wrote (bug report
    088). A year that disagrees came from somewhere else -- a tag the uploader set, a rule
    -- and is left alone, as is any `current` that already carries more than a year.
    """
    current = str(current or '').strip()
    if not _YEAR_ONLY.fullmatch(current):
        return None
    full = iso_date(upload_date)
    if full and full[:4] == current:
        return full
    return None
