from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_config_roundtrip(client):
    update = {
        "default_user": "alice",
        "lms_source_name": "lms",
        "listenbrainz_user": "alice-lb",
        "analyzer_scan_job_timeout": "1800",
    }
    response = await client.put("/api/v1/config", json=update)
    assert response.status_code == 200
    assert response.json()["values"]["default_user"] == "alice"

    fetched = await client.get("/api/v1/config")
    assert fetched.status_code == 200
    data = fetched.json()["values"]
    assert data["default_user"] == "alice"
    assert data["listenbrainz_user"] == "alice-lb"
    assert data["analyzer_scan_job_timeout"] == "1800"
