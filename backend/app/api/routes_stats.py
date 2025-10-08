from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..services.stats_service import StatsService
from .deps import get_stats_service, verify_api_key

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/artists", dependencies=[Depends(verify_api_key)])
async def artists(year: int = Query(...), service: StatsService = Depends(get_stats_service)):
    return await service.artists(year)


@router.get("/genres", dependencies=[Depends(verify_api_key)])
async def genres(year: int = Query(...), service: StatsService = Depends(get_stats_service)):
    return await service.genres(year)


@router.get("/top-artist-by-genre", dependencies=[Depends(verify_api_key)])
async def top_artist_by_genre(
    year: int = Query(...),
    service: StatsService = Depends(get_stats_service),
):
    return await service.top_artist_by_genre(year)


@router.get("/time-of-day", dependencies=[Depends(verify_api_key)])
async def time_of_day(
    year: int = Query(...),
    period: str = Query("morning", pattern="^(morning|afternoon|evening|night)$"),
    service: StatsService = Depends(get_stats_service),
):
    return await service.time_of_day(year, period)
