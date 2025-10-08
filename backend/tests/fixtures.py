from __future__ import annotations

from datetime import datetime, timezone

from httpx import AsyncClient


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


async def seed_dataset(client: AsyncClient) -> None:
    payloads = [
        {
            "user": "alice",
            "source": "lms",
            "listened_at": iso(datetime(2023, 5, 20, 8, 30, tzinfo=timezone.utc)),
            "track": {"title": "Morning Track", "album": "Sunrise", "album_year": 2023},
            "artists": [{"name": "Artist A", "role": "primary"}],
            "genres": ["Uplifting"],
        },
        {
            "user": "alice",
            "source": "lms",
            "listened_at": iso(datetime(2023, 11, 20, 20, 0, tzinfo=timezone.utc)),
            "track": {"title": "Evening Track", "album": "Sunset", "album_year": 2023},
            "artists": [{"name": "Artist B", "role": "primary"}],
            "genres": ["Chill"],
        },
        {
            "user": "bob",
            "source": "lms",
            "listened_at": iso(datetime(2024, 2, 14, 14, 15, tzinfo=timezone.utc)),
            "track": {"title": "Afternoon Groove", "album": "Groove", "album_year": 2024},
            "artists": [{"name": "Artist A", "role": "primary"}],
            "genres": ["Chill"],
        },
    ]
    for payload in payloads:
        await client.post("/api/v1/scrobble", json=payload)
