from __future__ import annotations

"""Helper utilities for populating test data."""

from datetime import datetime, timezone

from httpx import AsyncClient

from analyzer.db.repo import AnalyzerRepository
from analyzer.matching.normalizer import normalize_text
from analyzer.matching.uid import make_track_uid

from scrobbler.app.main import app


def iso(dt: datetime) -> str:
    """Return an ISO formatted timestamp in UTC."""

    return dt.astimezone(timezone.utc).isoformat()


async def seed_dataset(client: AsyncClient) -> None:
    """Seed a small dataset of listens used by multiple tests."""

    repo = AnalyzerRepository(app.state.db_adapter.engine)
    payloads = [
        {
            "user": "alice",
            "source": "lms",
            "listened_at": iso(datetime(2023, 5, 20, 8, 30, tzinfo=timezone.utc)),
            "track": {
                "title": "Morning Track",
                "album": "Sunrise",
                "album_year": 2023,
                "duration_secs": 240,
            },
            "artists": [{"name": "Artist A", "role": "primary"}],
            "genres": ["Uplifting"],
        },
        {
            "user": "alice",
            "source": "lms",
            "listened_at": iso(datetime(2023, 11, 20, 20, 0, tzinfo=timezone.utc)),
            "track": {
                "title": "Evening Track",
                "album": "Sunset",
                "album_year": 2023,
                "duration_secs": 720,
            },
            "artists": [{"name": "Artist B", "role": "primary"}],
            "genres": ["Chill"],
        },
        {
            "user": "bob",
            "source": "lms",
            "listened_at": iso(datetime(2024, 2, 14, 14, 15, tzinfo=timezone.utc)),
            "track": {
                "title": "Afternoon Groove",
                "album": "Groove",
                "album_year": 2024,
                "duration_secs": 330,
            },
            "artists": [{"name": "Artist A", "role": "primary"}],
            "genres": ["Chill"],
        },
    ]
    for payload in payloads:
        track = payload["track"]
        artists = payload.get("artists", [])
        primary_artist_name = artists[0]["name"] if artists else None
        artist_id = None
        if primary_artist_name:
            normalized = normalize_text(primary_artist_name)
            artist_id = await repo.upsert_artist(
                display_name=primary_artist_name,
                name_normalized=normalized,
                sort_name=normalized,
                mbid=None,
            )

        album_id = None
        if track.get("album") and artist_id is not None:
            album_id = await repo.upsert_album(
                title=track["album"],
                title_normalized=normalize_text(track["album"]),
                artist_id=artist_id,
                year=track.get("album_year"),
                mbid=None,
            )

        track_uid = make_track_uid(
            artist=primary_artist_name,
            title=track["title"],
            album=track.get("album"),
            duration=track.get("duration_secs"),
        )

        track_id = await repo.upsert_track(
            title=track["title"],
            title_normalized=normalize_text(track["title"]),
            album_id=album_id,
            primary_artist_id=artist_id,
            duration=track.get("duration_secs"),
            mbid=None,
            isrc=None,
            acoustid=None,
            track_uid=track_uid,
        )

        if artist_id is not None:
            await repo.link_track_artists(track_id, [(artist_id, "primary")])

        genre_ids = []
        for genre_name in payload.get("genres", []):
            genre_id = await repo.upsert_genre(
                name=genre_name,
                name_normalized=normalize_text(genre_name),
            )
            genre_ids.append(genre_id)
        if genre_ids:
            await repo.link_track_genres(track_id, genre_ids)

        await client.post("/api/v1/scrobble", json=payload)
