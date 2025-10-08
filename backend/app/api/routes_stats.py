from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..services.stats_service import StatsService
from .deps import get_stats_service, verify_api_key

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/artists", dependencies=[Depends(verify_api_key)])
async def artists(
    period: str = Query("year", pattern="^(day|month|year)$"),
    value: str | None = Query(None),
    service: StatsService = Depends(get_stats_service),
):
    """Return listen counts grouped by artist for the requested period."""

    try:
        return await service.artists(period, value)
    except ValueError as exc:  # pragma: no cover - validated via tests
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/genres", dependencies=[Depends(verify_api_key)])
async def genres(
    period: str = Query("year", pattern="^(day|month|year)$"),
    value: str | None = Query(None),
    service: StatsService = Depends(get_stats_service),
):
    """Return listen counts grouped by genre for the requested period."""

    try:
        return await service.genres(period, value)
    except ValueError as exc:  # pragma: no cover - validated via tests
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/top-artist-by-genre", dependencies=[Depends(verify_api_key)])
async def top_artist_by_genre(
    year: int = Query(...),
    service: StatsService = Depends(get_stats_service),
):
    """Return the most played artist per genre for the requested year."""

    return await service.top_artist_by_genre(year)


@router.get("/time-of-day", dependencies=[Depends(verify_api_key)])
async def time_of_day(
    year: int = Query(...),
    period: str = Query("morning", pattern="^(morning|afternoon|evening|night)$"),
    service: StatsService = Depends(get_stats_service),
):
    """Return top tracks for the selected time-of-day segment in a year."""

    return await service.time_of_day(year, period)
