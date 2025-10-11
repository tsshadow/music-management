from __future__ import annotations

import pytest

from scrobbler.app.main import app


class DummyExportService:
    def __init__(self, response):
        self.response = response
        self.calls: list[dict] = []

    async def export_user(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


@pytest.mark.asyncio
async def test_listenbrainz_export_endpoint(client):
    adapter = app.state.db_adapter
    await adapter.update_config({
        "listenbrainz_user": "exporter",
        "listenbrainz_token": "secret",
    })

    dummy_service = DummyExportService({"exported": 3, "skipped": 1, "batches": 1})
    original = app.state.listenbrainz_export_service
    app.state.listenbrainz_export_service = dummy_service

    try:
        response = await client.post("/api/v1/export/listenbrainz", json={})
        assert response.status_code == 200
        data = response.json()
        assert data == {"user": "exporter", "exported": 3, "skipped": 1, "batches": 1}
        assert dummy_service.calls == [
            {
                "user": "exporter",
                "token": "secret",
                "since": None,
                "listen_type": "import",
                "batch_size": 100,
            }
        ]
    finally:
        app.state.listenbrainz_export_service = original


@pytest.mark.asyncio
async def test_listenbrainz_export_requires_token(client):
    adapter = app.state.db_adapter
    await adapter.update_config({"listenbrainz_user": "exporter"})

    response = await client.post("/api/v1/export/listenbrainz", json={})
    assert response.status_code == 400
    assert response.json()["detail"] == "ListenBrainz token is required"
