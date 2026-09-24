"""Which day a feed belongs to.

The daily mixes are a new draw every day, and "day" has to mean the listener's day, not the
container's. The music-manager container runs on UTC unless its compose file says otherwise, so
`datetime.now().date()` rolled every mix over at 01:00 (winter) or 02:00 (summer) Amsterdam time:
a listener opening Home just after midnight still got yesterday's mix, and the one built then was
cached as today's for the rest of the day.

`feed_date` is the single answer to "which day is it" for everything in `feeds/`: the snapshot's
`feed_date` column, the daily sample order (`scoring.daily_sample_key`) and the artist/label
rotation (`scoring.pick_daily_entity`). The instant itself (`now`) stays whatever the caller had;
only the calendar day is read in the configured zone.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

#: The environment variable naming the zone a feed day is counted in.
TIMEZONE_ENV = 'MUMA_TIMEZONE'

#: Where the listeners of this installation live. An unset or empty `MUMA_TIMEZONE` means this.
DEFAULT_TIMEZONE = 'Europe/Amsterdam'


@lru_cache(maxsize=8)
def _zone(name: str) -> ZoneInfo | None:
    """The `ZoneInfo` for `name`, or None (logged once per name) when it does not exist."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning('%s=%r is not a known timezone; feed days fall back to the system clock', TIMEZONE_ENV, name)
        return None


def feed_zone_name() -> str:
    """The configured zone name: `MUMA_TIMEZONE`, or `DEFAULT_TIMEZONE` when it is unset or empty."""
    return (os.getenv(TIMEZONE_ENV) or '').strip() or DEFAULT_TIMEZONE


def feed_date(now: datetime) -> date:
    """The calendar day `now` falls on in the configured zone.

    A naive `now` (what `datetime.now()` returns) is read as the system's local time, which is
    what it is; an aware one is converted directly. An unknown zone name degrades to the date
    the system clock would have given, rather than failing the request.
    """
    zone = _zone(feed_zone_name())
    if zone is None:
        return now.date()
    return now.astimezone(zone).date()
