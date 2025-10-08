from __future__ import annotations

from datetime import datetime, timezone

import pytest


@pytest.mark.asyncio
async def test_scrobble_flow(client):
    payload = {
        "user": "user",
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
    listen_id = response.json()["listen_id"]
    assert listen_id > 0

    recent = await client.get("/api/v1/listens/recent")
    assert recent.status_code == 200
    data = recent.json()
    assert len(data) == 1
    assert data[0]["track_title"] == "My Track"

    count = await client.get("/api/v1/listens/count")
    assert count.status_code == 200
    assert count.json()["count"] == 1
