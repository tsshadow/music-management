from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.services.listenbrainz_service import ListenBrainzImportService


def build_listen(**extra):
    listen = {
        "track_metadata": {
            "track_name": "Example",
            "artist_name": "Artist",
            "additional_info": {},
        },
        "listened_at": 1_700_000_000,
    }
    listen.update(extra)
    return listen


def test_extract_genres_collects_from_multiple_sources():
    listen = build_listen(
        track_metadata={
            "track_name": "Example",
            "artist_name": "Artist",
            "genres": ["Indie", "Lo-Fi"],
            "additional_info": {
                "tags": ["Rock", {"name": "synthpop "}],
                "musicbrainz_tags": [{"name": "Electronic"}],
                "artist_tags": [{"value": "indie"}],
                "release_group_tags": ["Alternative"],
            },
        },
        tags=["Rock", "Dream Pop"],
    )

    genres = ListenBrainzImportService._extract_genres(listen)

    assert genres == [
        "Indie",
        "Lo-Fi",
        "Rock",
        "synthpop",
        "Electronic",
        "Alternative",
        "Dream Pop",
    ]


def test_extract_genres_deduplicates_case_insensitive():
    listen = build_listen(
        track_metadata={
            "track_name": "Example",
            "artist_name": "Artist",
            "additional_info": {
                "tags": ["Pop", "pop", " POP "],
            },
        }
    )

    genres = ListenBrainzImportService._extract_genres(listen)

    assert genres == ["Pop"]


def test_extract_genres_handles_tag_dict_keys():
    listen = build_listen(
        track_metadata={
            "track_name": "Example",
            "artist_name": "Artist",
            "additional_info": {
                "artist_genres": [{"genre": "Hip-Hop"}, {"tag": "Rap"}],
            },
        }
    )

    genres = ListenBrainzImportService._extract_genres(listen)

    assert genres == ["Hip-Hop", "Rap"]


class DummyResponse:
    def __init__(self, data: dict | None = None, status_code: int = 200):
        self._data = data or {}
        self.status_code = status_code

    def json(self) -> dict:
        return self._data


class DummyListenBrainzClient:
    def __init__(self, responses: list[DummyResponse]):
        self._responses = responses
        self.calls: list[tuple[str, dict | None]] = []

    async def get(self, url: str, params: dict | None = None) -> DummyResponse:
        self.calls.append((url, params))
        return self._responses.pop(0)


class DummyMusicBrainzClient:
    def __init__(self, responses: list[DummyResponse]):
        self._responses = responses
        self.calls: list[tuple[str, dict | None]] = []

    async def __aenter__(self) -> "DummyMusicBrainzClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, url: str, params: dict | None = None) -> DummyResponse:
        self.calls.append((url, params))
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_fetch_remote_genres_uses_listenbrainz_metadata():
    service = ListenBrainzImportService(SimpleNamespace())
    listen = build_listen(
        track_metadata={
            "track_name": "Example",
            "artist_name": "Artist",
            "additional_info": {"recording_mbid": "11111111-1111-1111-1111-111111111111"},
        }
    )
    client = DummyListenBrainzClient(
        [
            DummyResponse(
                {
                    "track_metadata": {
                        "additional_info": {"tags": ["Hardcore", "Industrial"]}
                    }
                }
            )
        ]
    )

    genres = await service._fetch_remote_genres(listen, client)

    assert genres == ["Hardcore", "Industrial"]
    assert client.calls == [
        ("/metadata/recording/11111111-1111-1111-1111-111111111111", None)
    ]


@pytest.mark.asyncio
async def test_fetch_remote_genres_falls_back_to_musicbrainz_tags():
    service = ListenBrainzImportService(SimpleNamespace())
    listen = build_listen(
        track_metadata={
            "track_name": "Example",
            "artist_name": "Artist",
            "additional_info": {"recording_mbid": "22222222-2222-2222-2222-222222222222"},
        }
    )
    lb_client = DummyListenBrainzClient([DummyResponse({})])
    mb_client = DummyMusicBrainzClient(
        [
            DummyResponse(
                {
                    "tags": [
                        {"name": "Hardcore"},
                        {"name": "Industrial"},
                    ]
                }
            )
        ]
    )
    service._client_factory = lambda **_: mb_client

    genres = await service._fetch_remote_genres(listen, lb_client)

    assert genres == ["Hardcore", "Industrial"]
    assert lb_client.calls == [
        ("/metadata/recording/22222222-2222-2222-2222-222222222222", None)
    ]
    assert mb_client.calls == [
        ("/recording/22222222-2222-2222-2222-222222222222", {"inc": "tags", "fmt": "json"})
    ]
