from __future__ import annotations

from ..db.adapter import DatabaseAdapter


class StatsService:
    """Expose analytics queries backed by the database adapter."""

    def __init__(self, adapter: DatabaseAdapter):
        """Initialize the service with a database adapter implementation."""

        self.adapter = adapter

    async def artists(self, year: int):
        """Return artist play counts for the given year."""

        return await self.adapter.stats_artists_by_year(year)

    async def genres(self, year: int):
        """Return genre play counts for the given year."""

        return await self.adapter.stats_genres_by_year(year)

    async def top_artist_by_genre(self, year: int):
        """Return the most played artist per genre for the given year."""

        return await self.adapter.stats_top_artist_by_genre(year)

    async def time_of_day(self, year: int, period: str):
        """Return top tracks within the selected time-of-day segment."""

        return await self.adapter.stats_time_of_day(year, period)
