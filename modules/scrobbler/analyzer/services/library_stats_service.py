"""Aggregated statistics for the normalized analyzer library."""

from __future__ import annotations

from analyzer.db.repo import AnalyzerRepository

__all__ = ["AnalyzerLibraryStatsService"]


class AnalyzerLibraryStatsService:
    """Expose paginated aggregations over the analyzer library tables."""

    def __init__(self, repo: AnalyzerRepository) -> None:
        """Store the repository used to run aggregation queries."""

        self.repo = repo

    async def artists(self, limit: int, offset: int) -> dict:
        """Return artists ranked by the number of songs in the library."""

        items, total = await self.repo.fetch_library_artists(limit=limit, offset=offset)
        return {"items": items, "total": total}

    async def albums(self, limit: int, offset: int) -> dict:
        """Return albums ranked by the number of songs in the library."""

        items, total = await self.repo.fetch_library_albums(limit=limit, offset=offset)
        return {"items": items, "total": total}

    async def genres(self, limit: int, offset: int) -> dict:
        """Return genres ranked by the number of songs in the library."""

        items, total = await self.repo.fetch_library_genres(limit=limit, offset=offset)
        return {"items": items, "total": total}

    async def tracks(self, limit: int, offset: int) -> dict:
        """Return tracks ordered by artist and title from the library."""

        items, total = await self.repo.fetch_library_tracks(limit=limit, offset=offset)
        return {"items": items, "total": total}
