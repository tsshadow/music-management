from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..db.adapter import DatabaseAdapter
from .deps import get_adapter, verify_api_key

router = APIRouter(prefix="/listens", tags=["listens"])


def _default_period_value(period: str) -> str | None:
    today = date.today()
    if period == "day":
        return today.strftime("%Y-%m-%d")
    if period == "month":
        return today.strftime("%Y-%m")
    if period == "week":
        iso = today.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return None


@router.get("", dependencies=[Depends(verify_api_key)])
async def list_listens(
    period: str = Query("day", pattern="^(day|week|month|all)$"),
    value: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    adapter: DatabaseAdapter = Depends(get_adapter),
):
    """Return listens filtered by the requested period with pagination metadata."""

    if period != "all" and not value:
        value = _default_period_value(period)

    try:
        rows, total = await adapter.fetch_listens(
            period=period,
            value=value,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "items": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/recent", dependencies=[Depends(verify_api_key)])
async def recent_listens(
    limit: int = Query(10, ge=1, le=100),
    adapter: DatabaseAdapter = Depends(get_adapter),
):
    """Return the most recent listens capped by the requested limit."""

    return await adapter.fetch_recent_listens(limit=limit)


@router.get("/count", dependencies=[Depends(verify_api_key)])
async def listen_count(adapter: DatabaseAdapter = Depends(get_adapter)):
    """Return the total number of stored listens."""

    count = await adapter.count_listens()
    return {"count": count}


@router.get("/{listen_id}", dependencies=[Depends(verify_api_key)])
async def get_listen(listen_id: int, adapter: DatabaseAdapter = Depends(get_adapter)):
    """Return the detailed metadata for a single listen."""

    listen = await adapter.fetch_listen_detail(listen_id)
    if listen is None:
        raise HTTPException(status_code=404, detail="Listen not found")
    return listen


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(verify_api_key)])
async def delete_all_listens(adapter: DatabaseAdapter = Depends(get_adapter)) -> Response:
    """Delete every stored listen."""

    await adapter.delete_all_listens()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
