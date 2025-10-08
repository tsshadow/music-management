from __future__ import annotations

from ..db.adapter import DatabaseAdapter


class StatsService:
    def __init__(self, adapter: DatabaseAdapter):
        self.adapter = adapter

    async def artists(self, year: int):
        return await self.adapter.stats_artists_by_year(year)

    async def genres(self, year: int):
        return await self.adapter.stats_genres_by_year(year)

    async def top_artist_by_genre(self, year: int):
        return await self.adapter.stats_top_artist_by_genre(year)

    async def time_of_day(self, year: int, period: str):
        return await self.adapter.stats_time_of_day(year, period)
