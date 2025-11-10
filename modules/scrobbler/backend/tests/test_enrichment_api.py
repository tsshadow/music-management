from __future__ import annotations

from datetime import datetime, timezone

import pytest


@pytest.mark.asyncio
async def test_queue_enrichment_with_defaults(client):
    response = await client.post("/api/v1/enrichment", json={})
    assert response.status_code == 202
    data = response.json()
    assert data["enrich_job_id"] == "job-1"

    calls = client.enrichment_queue.calls  # type: ignore[attr-defined]
    assert len(calls) == 1
    queued = calls[0]
    assert queued["limit"] == 500
    assert queued["since"] is None


@pytest.mark.asyncio
async def test_queue_enrichment_with_since(client):
    since = datetime(2024, 3, 1, 12, tzinfo=timezone.utc)
    response = await client.post(
        "/api/v1/enrichment",
        json={"since": since.isoformat(), "limit": 750},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["enrich_job_id"] == "job-1"

    calls = client.enrichment_queue.calls  # type: ignore[attr-defined]
    assert len(calls) == 1
    queued = calls[0]
    assert queued["limit"] == 750
    assert queued["since"] == since
