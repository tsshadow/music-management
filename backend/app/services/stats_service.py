from __future__ import annotations

from datetime import date, datetime

from ..db.adapter import DatabaseAdapter


class StatsService:
    """Expose analytics queries backed by the database adapter."""

    def __init__(self, adapter: DatabaseAdapter):
        """Initialize the service with a database adapter implementation."""

        self.adapter = adapter

    async def artists(self, period: str, value: str | None):
        """Return artist play counts for the selected period."""

        normalized_period, normalized_value = self._normalize_period(period, value)
        return await self.adapter.stats_artists(normalized_period, normalized_value)

    async def albums(self, period: str, value: str | None):
        """Return album play counts for the selected period."""

        normalized_period, normalized_value = self._normalize_period(period, value)
        return await self.adapter.stats_albums(normalized_period, normalized_value)

    async def tracks(self, period: str, value: str | None):
        """Return track play counts for the selected period."""

        normalized_period, normalized_value = self._normalize_period(period, value)
        return await self.adapter.stats_tracks(normalized_period, normalized_value)

    async def genres(self, period: str, value: str | None):
        """Return genre play counts for the selected period."""

        normalized_period, normalized_value = self._normalize_period(period, value)
        return await self.adapter.stats_genres(normalized_period, normalized_value)

    async def top_artist_by_genre(self, year: int):
        """Return the most played artist per genre for the given year."""

        return await self.adapter.stats_top_artist_by_genre(year)

    async def time_of_day(self, year: int, period: str):
        """Return top tracks within the selected time-of-day segment."""

        return await self.adapter.stats_time_of_day(year, period)

    def _normalize_period(self, period: str, value: str | None) -> tuple[str, str | None]:
        """Validate and coerce the requested stats period."""

        if period not in {"day", "month", "year", "all"}:
            raise ValueError("Unsupported period")

        today = date.today()

        if period == "all":
            return "all", None

        if period == "year":
            if value is None:
                return "year", f"{today.year:04d}"
            try:
                year = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError("Invalid year format") from exc
            if year < 1900 or year > 9999:
                raise ValueError("Year out of range")
            return "year", f"{year:04d}"

        if period == "month":
            if value is None:
                return "month", today.strftime("%Y-%m")
            try:
                dt = datetime.strptime(value, "%Y-%m")
            except (TypeError, ValueError) as exc:
                raise ValueError("Invalid month format") from exc
            return "month", dt.strftime("%Y-%m")

        # day period
        if value is None:
            return "day", today.strftime("%Y-%m-%d")
        try:
            dt = datetime.strptime(value, "%Y-%m-%d")
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid day format") from exc
        return "day", dt.strftime("%Y-%m-%d")
