from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

from scrobbler.app.services.listenbrainz_export_service import ListenBrainzExportService


class DummyAdapter:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows
        self.calls: list[dict[str, Any]] = []

    async def fetch_listens_for_export(
        self,
        *,
        user: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        self.calls.append({"user": user, "since": since, "limit": limit, "offset": offset})
        start = offset
        end = offset + limit
        return self.rows[start:end]


@pytest.mark.asyncio
async def test_listenbrainz_export_service_submits_payload():
    rows = [
        {
            "listen_id": 1,
            "username": "alice",
            "listened_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "listen_duration": 185,
            "source": "test",
            "source_track_id": "track-1",
            "track": {
                "id": 1,
                "title": "Track A",
                "album": "Album A",
                "duration": 190,
                "track_no": 1,
                "disc_no": 1,
                "mbid": "11111111-1111-1111-1111-111111111111",
                "isrc": "US-AAA-99-00001",
            },
            "artists": [{"name": "Artist A", "role": "primary"}],
            "listen_artists": ["Artist A"],
            "genres": ["Rock"],
        },
        {
            "listen_id": 2,
            "username": "alice",
            "listened_at": datetime(2024, 1, 2, tzinfo=timezone.utc),
            "listen_duration": 200,
            "source": "test",
            "source_track_id": None,
            "track": {
                "id": 2,
                "title": None,
                "album": None,
                "duration": None,
                "track_no": None,
                "disc_no": None,
                "mbid": None,
                "isrc": None,
            },
            "artists": [],
            "listen_artists": [],
            "genres": [],
        },
    ]
    adapter = DummyAdapter(rows)
    captured: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/submit-listens")
        payload = json.loads(request.content.decode())
        captured.append(payload)
        assert payload["listen_type"] == "import"
        assert len(payload["payload"]) == 1
        listen = payload["payload"][0]
        assert listen["listened_at"] == int(rows[0]["listened_at"].timestamp())
        metadata = listen["track_metadata"]
        assert metadata["track_name"] == "Track A"
        assert metadata["artist_name"] == "Artist A"
        assert metadata["additional_info"]["recording_mbid"] == "11111111-1111-1111-1111-111111111111"
        assert metadata["additional_info"]["tags"] == ["Rock"]
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(handler)
    service = ListenBrainzExportService(
        adapter,
        client_factory=lambda **kwargs: httpx.AsyncClient(transport=transport, **kwargs),
    )

    result = await service.export_user(user="alice", token="token", batch_size=2)

    assert result == {"exported": 1, "skipped": 1, "batches": 1}
    assert len(captured) == 1
    assert adapter.calls[0]["user"] == "alice"
    assert adapter.calls[0]["limit"] == 2
    assert adapter.calls[0]["offset"] == 0
    assert adapter.calls[-1]["offset"] == 2
