from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..db.adapter import DatabaseAdapter
from ..schemas.listenbrainz import ListenBrainzExportRequest
from ..services.listenbrainz_export_service import ListenBrainzExportService
from .deps import (
    get_adapter,
    get_listenbrainz_export_service,
    verify_api_key,
)

router = APIRouter(prefix="/export", tags=["listenbrainz"], dependencies=[Depends(verify_api_key)])


@router.post("/listenbrainz")
async def export_listenbrainz(
    payload: ListenBrainzExportRequest,
    adapter: DatabaseAdapter = Depends(get_adapter),
    service: ListenBrainzExportService = Depends(get_listenbrainz_export_service),
):
    """Submit stored listens to ListenBrainz for the configured user."""

    config = await adapter.get_config()
    user = payload.user or config.get("listenbrainz_user") or config.get("default_user")
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ListenBrainz user is required")

    token = payload.token or config.get("listenbrainz_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ListenBrainz token is required")

    result = await service.export_user(
        user=user,
        token=token,
        since=payload.since,
        listen_type=payload.listen_type,
        batch_size=payload.batch_size,
    )
    return {"user": user, **result}
