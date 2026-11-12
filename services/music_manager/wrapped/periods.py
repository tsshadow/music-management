"""Which period a Wrapped request is about, and the key it is stored under.

A year `2026` is 1 January to 31 December; a custom range is two dates, stored as
`2026-03-01_2026-06-30`. Both are dates in the tab's time zone (decision 8).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MAX_RANGE_DAYS = 3 * 366


class PeriodError(ValueError):
    """A period the API answers with 400."""


@dataclass(frozen=True)
class Period:
    """A closed range of local dates."""

    date_from: date
    date_to: date
    year: int | None = None

    @property
    def key(self) -> str:
        """The snapshot key: the year, or both dates."""
        if self.year is not None:
            return str(self.year)
        return f'{self.date_from.isoformat()}_{self.date_to.isoformat()}'

    def end_utc(self, zone: ZoneInfo) -> datetime:
        """The UTC instant the period ends: the next local midnight after its last day, naive."""
        local = datetime.combine(self.date_to + timedelta(days=1), time.min, tzinfo=zone)
        return local.astimezone(UTC).replace(tzinfo=None)


def parse_period(year: int | None, date_from: date | None, date_to: date | None) -> Period:
    """A year, or a from-to range of at most three years. Both or neither is an error."""
    has_range = date_from is not None or date_to is not None
    if year is not None and has_range:
        raise PeriodError("Give either 'year' or 'from' and 'to', not both")
    if year is not None:
        if not 1900 <= year <= 2100:
            raise PeriodError(f'Year out of range: {year}')
        return Period(date(year, 1, 1), date(year, 12, 31), year)
    if date_from is None or date_to is None:
        raise PeriodError("Give 'year', or both 'from' and 'to'")
    if date_to < date_from:
        raise PeriodError("'to' is before 'from'")
    if (date_to - date_from).days > MAX_RANGE_DAYS:
        raise PeriodError('A range covers three years at most')
    return Period(date_from, date_to)


def parse_key(key: str) -> Period:
    """The Period a stored key names."""
    if '_' in key:
        first, last = key.split('_', 1)
        return parse_period(None, date.fromisoformat(first), date.fromisoformat(last))
    return parse_period(int(key), None, None)


def parse_zone(name: str) -> ZoneInfo:
    """An IANA zone, or PeriodError."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise PeriodError(f'Unknown timezone: {name}') from None
