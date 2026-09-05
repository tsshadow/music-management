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
