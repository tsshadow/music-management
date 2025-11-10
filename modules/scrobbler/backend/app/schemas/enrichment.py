"""Pydantic models for enrichment queue endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class EnrichmentRequest(BaseModel):
    """Describe optional parameters when queueing listen enrichment."""

    since: datetime | None = None
    limit: int = Field(default=500, ge=1)

    @field_validator("limit")
    def validate_limit(cls, value: int) -> int:
        """Ensure the enrichment batch size stays within a sensible range."""

        if value > 10000:
            raise ValueError("limit must be less than or equal to 10000")
        return value


class EnrichmentResponse(BaseModel):
    """Return the queued enrichment job identifier."""

    enrich_job_id: str
