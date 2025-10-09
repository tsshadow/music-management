from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from ..db.adapter import DatabaseAdapter
from .deps import get_adapter, verify_api_key

router = APIRouter(prefix="/listens", tags=["listens"])


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


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(verify_api_key)])
async def delete_all_listens(adapter: DatabaseAdapter = Depends(get_adapter)) -> Response:
    """Delete every stored listen."""

    await adapter.delete_all_listens()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
