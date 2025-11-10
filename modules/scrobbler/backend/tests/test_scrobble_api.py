from __future__ import annotations

from datetime import datetime, timezone

import pytest


@pytest.mark.asyncio
async def test_scrobble_flow(client):
    payload = {
        "user": "teun",
        "source": "lms",
        "listened_at": datetime.now(timezone.utc).isoformat(),
        "position_secs": 120,
        "duration_secs": 300,
        "track": {
            "title": "My Track",
            "album": "My Album",
            "album_year": 2024,
            "track_no": 1,
        },
        "artists": [{"name": "Main Artist", "role": "primary"}],
        "genres": ["Hardcore"],
    }

    response = await client.post("/api/v1/scrobble", json=payload)
    assert response.status_code == 201
    data = response.json()
    listen_id = data["listen_id"]
    assert listen_id > 0
    assert data["enrich_job_id"] == "job-1"

    calls = client.enrichment_queue.calls  # type: ignore[attr-defined]
    assert len(calls) == 1
    queued = calls[0]
    assert queued["limit"] == 500
    assert queued["since"] == datetime.fromisoformat(payload["listened_at"])

    recent = await client.get("/api/v1/listens/recent")
    assert recent.status_code == 200
    data = recent.json()
    assert len(data) == 1
    assert data[0]["track_title"] == "My Track"

    count = await client.get("/api/v1/listens/count")
    assert count.status_code == 200
    assert count.json()["count"] == 1

    delete = await client.delete("/api/v1/listens")
    assert delete.status_code == 204

    count_after = await client.get("/api/v1/listens/count")
    assert count_after.status_code == 200
    assert count_after.json()["count"] == 0
