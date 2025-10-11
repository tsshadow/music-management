from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..services.stats_service import StatsService
from .deps import get_stats_service, verify_api_key

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/artists", dependencies=[Depends(verify_api_key)])
async def artists(
    period: str = Query("year", pattern="^(day|month|year|all)$"),
    value: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    service: StatsService = Depends(get_stats_service),
):
    """Return listen counts grouped by artist for the requested period."""

    try:
        data = await service.artists(
            period, value, page_size, (page - 1) * page_size
        )
    except ValueError as exc:  # pragma: no cover - validated via tests
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {**data, "page": page, "page_size": page_size}


@router.get("/albums", dependencies=[Depends(verify_api_key)])
async def albums(
    period: str = Query("year", pattern="^(day|month|year|all)$"),
    value: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    service: StatsService = Depends(get_stats_service),
):
    """Return listen counts grouped by album for the requested period."""

    try:
        data = await service.albums(
            period, value, page_size, (page - 1) * page_size
        )
    except ValueError as exc:  # pragma: no cover - validated via tests
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {**data, "page": page, "page_size": page_size}


@router.get("/tracks", dependencies=[Depends(verify_api_key)])
async def tracks(
    period: str = Query("year", pattern="^(day|month|year|all)$"),
    value: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    service: StatsService = Depends(get_stats_service),
):
    """Return listen counts grouped by track for the requested period."""

    try:
        data = await service.tracks(
            period, value, page_size, (page - 1) * page_size
        )
    except ValueError as exc:  # pragma: no cover - validated via tests
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {**data, "page": page, "page_size": page_size}


@router.get("/genres", dependencies=[Depends(verify_api_key)])
async def genres(
    period: str = Query("year", pattern="^(day|month|year|all)$"),
    value: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    service: StatsService = Depends(get_stats_service),
):
    """Return listen counts grouped by genre for the requested period."""

    try:
        data = await service.genres(
            period, value, page_size, (page - 1) * page_size
        )
    except ValueError as exc:  # pragma: no cover - validated via tests
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {**data, "page": page, "page_size": page_size}


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
