from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..db.adapter import DatabaseAdapter
from ..schemas.listenbrainz import ListenBrainzImportRequest
from ..services.enrichment_queue_service import EnrichmentQueueService
from ..services.listenbrainz_service import ListenBrainzImportService
from .deps import (
    get_adapter,
    get_enrichment_queue_service,
    get_listenbrainz_service,
    verify_api_key,
)

router = APIRouter(prefix="/import", tags=["listenbrainz"], dependencies=[Depends(verify_api_key)])


@router.post("/listenbrainz")
async def import_listenbrainz(
    payload: ListenBrainzImportRequest,
    adapter: DatabaseAdapter = Depends(get_adapter),
    service: ListenBrainzImportService = Depends(get_listenbrainz_service),
    enrichment_queue: EnrichmentQueueService = Depends(get_enrichment_queue_service),
):
    """Trigger a ListenBrainz import and return summary statistics."""

    config = await adapter.get_config()
    user = payload.user or config.get("listenbrainz_user") or config.get("default_user")
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ListenBrainz user is required")
    token = payload.token or config.get("listenbrainz_token")
    result = await service.import_user(
        user=user,
        token=token,
        since=payload.since,
        page_size=payload.page_size,
        max_pages=payload.max_pages,
    )
    earliest_created = result.pop("earliest_created_at", None)
    since_for_queue = payload.since
    if earliest_created is not None:
        result["earliest_created_at"] = earliest_created.isoformat()
        if since_for_queue is None or earliest_created < since_for_queue:
            since_for_queue = earliest_created
    else:
        result["earliest_created_at"] = None
    enrich_job_id: str | None = None
    if result.get("imported", 0) > 0:
        enrich_job_id = enrichment_queue.queue_enrich(since=since_for_queue)
    result["enrich_job_id"] = enrich_job_id
    return {"user": user, **result}
