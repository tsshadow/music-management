from __future__ import annotations

from typing import Any

import httpx
import pytest

from analyzer.db.repo import AnalyzerRepository
from analyzer.matching.normalizer import normalize_text
from analyzer.matching.uid import make_track_uid

from backend.app.main import app
from backend.app.services.listenbrainz_service import ListenBrainzImportService


def build_listen(ts: int, title: str, artist: str) -> dict[str, Any]:
    return {
        "listened_at": ts,
        "recording_msid": f"msid-{title}",
        "track_metadata": {
            "track_name": title,
            "artist_name": artist,
            "release_name": f"Album {title}",
            "additional_info": {
                "duration": 180,
                "tracknumber": "1",
                "discnumber": "1",
            },
        },
    }


@pytest.mark.asyncio
async def test_listenbrainz_import_endpoint(client):
    listens = [
        build_listen(1_700_000_000, "Track A", "Artist A"),
        build_listen(1_699_000_000, "Track B", "Artist B"),
    ]

    repo = AnalyzerRepository(app.state.db_adapter.engine)
    for listen in listens:
        metadata = listen["track_metadata"]
        artist_name = metadata["artist_name"]
        normalized_artist = normalize_text(artist_name)
        artist_id = await repo.upsert_artist(
            display_name=artist_name,
            name_normalized=normalized_artist,
            sort_name=normalized_artist,
            mbid=None,
        )

        album_name = metadata.get("release_name")
        album_id = None
        if album_name:
            album_id = await repo.upsert_album(
                title=album_name,
                title_normalized=normalize_text(album_name),
                artist_id=artist_id,
                year=None,
                mbid=None,
            )

        duration = metadata.get("additional_info", {}).get("duration")
        track_uid = make_track_uid(
            artist=artist_name,
            title=metadata["track_name"],
            album=album_name,
            duration=duration,
        )
        track_id = await repo.upsert_track(
            title=metadata["track_name"],
            title_normalized=normalize_text(metadata["track_name"]),
            album_id=album_id,
            primary_artist_id=artist_id,
            duration=duration,
            mbid=None,
            isrc=None,
            acoustid=None,
            track_uid=track_uid,
        )
        await repo.link_track_artists(track_id, [(artist_id, "primary")])

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/user/importer/listens")
        params = dict(request.url.params)
        if "max_ts" in params:
            return httpx.Response(200, json={"payload": {"listens": []}})
        return httpx.Response(200, json={"payload": {"listens": listens}})

    transport = httpx.MockTransport(handler)

    original_service = app.state.listenbrainz_service
    app.state.listenbrainz_service = ListenBrainzImportService(
        app.state.ingest_service,
        client_factory=lambda **kwargs: httpx.AsyncClient(transport=transport, **kwargs),
    )

    try:
        payload = {"user": "importer", "page_size": 100}
        first = await client.post("/api/v1/import/listenbrainz", json=payload)
        assert first.status_code == 200
        first_data = first.json()
        assert first_data["user"] == "importer"
        assert first_data["imported"] == 2
        assert first_data["processed"] == 2
        assert first_data["skipped"] == 0

        second = await client.post("/api/v1/import/listenbrainz", json=payload)
        assert second.status_code == 200
        second_data = second.json()
        assert second_data["imported"] == 0
        assert second_data["processed"] == 2
    finally:
        app.state.listenbrainz_service = original_service
