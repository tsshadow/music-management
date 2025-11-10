"""Routes for triggering listen enrichment jobs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from ..schemas.enrichment import EnrichmentRequest, EnrichmentResponse
from ..services.enrichment_queue_service import EnrichmentQueueService
from .deps import get_enrichment_queue_service, verify_api_key

router = APIRouter(
    prefix="/enrichment",
    tags=["enrichment"],
    dependencies=[Depends(verify_api_key)],
)


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=EnrichmentResponse)
async def queue_enrichment_job(
    payload: EnrichmentRequest | None = None,
    service: EnrichmentQueueService = Depends(get_enrichment_queue_service),
) -> EnrichmentResponse:
    """Queue a job that reconciles listens with the media library."""

    payload = payload or EnrichmentRequest()
    job_id = service.queue_enrich(since=payload.since, limit=payload.limit)
    return EnrichmentResponse(enrich_job_id=job_id)
