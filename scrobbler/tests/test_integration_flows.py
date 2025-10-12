from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from analyzer.db.repo import AnalyzerRepository
from analyzer.matching.normalizer import normalize_text
from analyzer.matching.uid import make_track_uid

from scrobbler.app.core.startup import init_database
from scrobbler.app.db.sqlite_test import create_sqlite_memory_adapter
from scrobbler.app.models import (
    artists,
    genres,
    listen_artists,
    listen_genres,
    listens,
    metadata,
    track_artists,
    track_genres,
    tracks,
)
from scrobbler.app.schemas.common import ArtistInput, ScrobblePayload, TrackInput
from scrobbler.app.services.ingest_service import IngestService


pytestmark = pytest.mark.integration


@pytest.fixture
async def isolated_database():
    """Create a fresh in-memory database for each integration scenario."""

    adapter = create_sqlite_memory_adapter()
    await init_database(adapter.engine, metadata)
    repository = AnalyzerRepository(adapter.engine)
    ingest = IngestService(adapter)
    try:
        yield adapter, repository, ingest
    finally:
        await adapter.close()


async def _analyze_track(
    repository: AnalyzerRepository,
    *,
    title: str,
    artist: str | None = None,
    genre: str | None = None,
    duration: int | None = None,
) -> dict[str, int | str | None]:
    """Helper that stores media library data similar to the analyzer."""

    artist_id: int | None = None
    if artist:
        normalized_artist = normalize_text(artist)
        artist_id = await repository.upsert_artist(
            display_name=artist,
            name_normalized=normalized_artist,
            sort_name=normalized_artist,
            mbid=None,
        )

    track_uid = make_track_uid(artist, title, None, duration)
    track_id = await repository.upsert_track(
        title=title,
        title_normalized=normalize_text(title),
        album_id=None,
        primary_artist_id=artist_id,
        duration=duration,
        mbid=None,
        isrc=None,
        acoustid=None,
        track_uid=track_uid,
    )

    if artist_id is not None:
        await repository.link_track_artists(track_id, [(artist_id, "primary")])

    genre_id: int | None = None
    if genre:
        genre_id = await repository.upsert_genre(
            name=genre,
            name_normalized=normalize_text(genre),
        )
        await repository.link_track_genres(track_id, [genre_id])

    return {
        "track_id": track_id,
        "artist_id": artist_id,
        "genre_id": genre_id,
        "track_uid": track_uid,
    }


@pytest.mark.asyncio
async def test_analyze_track_with_title_only(isolated_database):
    """Given a fresh media library
    When the analyzer records a track using only its title
    Then the track appears in the media library without any linked artists or genres."""

    adapter, repository, _ = isolated_database

    result = await _analyze_track(repository, title="Lonely Signal")

    async with adapter.session_factory() as session:
        track_row = (
            await session.execute(select(tracks).where(tracks.c.id == result["track_id"]))
        ).mappings().one()
        assert track_row["title"] == "Lonely Signal"
        assert track_row["primary_artist_id"] is None

        artist_links = (
            await session.execute(
                select(track_artists).where(track_artists.c.track_id == result["track_id"])
            )
        ).fetchall()
        assert artist_links == []

        genre_links = (
            await session.execute(
                select(track_genres).where(track_genres.c.track_id == result["track_id"])
            )
        ).fetchall()
        assert genre_links == []

        listen_count = (
            await session.execute(select(func.count()).select_from(listens))
        ).scalar_one()
        assert listen_count == 0


@pytest.mark.asyncio
async def test_analyze_track_with_artist(isolated_database):
    """Given a fresh media library
    When the analyzer records a track with both artist and title metadata
    Then the artist and track are stored together without creating listens."""

    adapter, repository, _ = isolated_database

    result = await _analyze_track(repository, title="Signal Fire", artist="The Metrics")

    async with adapter.session_factory() as session:
        track_row = (
            await session.execute(select(tracks).where(tracks.c.id == result["track_id"]))
        ).mappings().one()
        assert track_row["title"] == "Signal Fire"
        assert track_row["primary_artist_id"] == result["artist_id"]

        artist_row = (
            await session.execute(select(artists).where(artists.c.id == result["artist_id"]))
        ).mappings().one()
        assert artist_row["name"] == "The Metrics"

        listen_count = (
            await session.execute(select(func.count()).select_from(listens))
        ).scalar_one()
        assert listen_count == 0


@pytest.mark.asyncio
async def test_analyze_track_with_artist_and_genre(isolated_database):
    """Given a fresh media library
    When the analyzer records a track with artist, title, and genre metadata
    Then the track is linked to both its artist and genre without producing listens."""

    adapter, repository, _ = isolated_database

    result = await _analyze_track(
        repository,
        title="Chromatic Dreams",
        artist="Spectrum",
        genre="Synthwave",
    )

    async with adapter.session_factory() as session:
        track_row = (
            await session.execute(select(tracks).where(tracks.c.id == result["track_id"]))
        ).mappings().one()
        assert track_row["title"] == "Chromatic Dreams"
        assert track_row["primary_artist_id"] == result["artist_id"]

        artist_links = (
            await session.execute(
                select(track_artists).where(track_artists.c.track_id == result["track_id"])
            )
        ).fetchall()
        assert len(artist_links) == 1

        genre_links = (
            await session.execute(
                select(track_genres).where(track_genres.c.track_id == result["track_id"])
            )
        ).fetchall()
        assert len(genre_links) == 1

        stored_genre = (
            await session.execute(select(genres).where(genres.c.id == result["genre_id"]))
        ).mappings().one()
        assert stored_genre["name"] == "Synthwave"

        listen_count = (
            await session.execute(select(func.count()).select_from(listens))
        ).scalar_one()
        assert listen_count == 0


@pytest.mark.asyncio
async def test_scrobble_links_to_existing_track(isolated_database):
    """Given a track already analyzed in the media library
    When the scrobbler ingests a listen for that track
    Then the listen references the existing track and stores artist and genre links."""

    adapter, repository, ingest = isolated_database

    analyzed = await _analyze_track(
        repository,
        title="Northern Lights",
        artist="Aurora Atlas",
        genre="Ambient",
        duration=320,
    )

    payload = ScrobblePayload(
        user="listener",
        source="lms",
        listened_at=datetime(2024, 3, 3, 12, 0, tzinfo=timezone.utc),
        track=TrackInput(title="Northern Lights", duration_secs=320),
        artists=[ArtistInput(name="Aurora Atlas")],
        genres=["Ambient"],
    )

    listen_id = await ingest.ingest(payload)

    async with adapter.session_factory() as session:
        listen_row = (
            await session.execute(select(listens).where(listens.c.id == listen_id))
        ).mappings().one()
        assert listen_row["track_id"] == analyzed["track_id"]
        assert listen_row["artist_name_raw"] == "Aurora Atlas"
        assert listen_row["track_title_raw"] == "Northern Lights"

        linked_artists = (
            await session.execute(
                select(listen_artists).where(listen_artists.c.listen_id == listen_id)
            )
        ).fetchall()
        assert len(linked_artists) == 1

        linked_genres = (
            await session.execute(
                select(listen_genres).where(listen_genres.c.listen_id == listen_id)
            )
        ).fetchall()
        assert len(linked_genres) == 1

        track_total = (
            await session.execute(select(func.count()).select_from(tracks))
        ).scalar_one()
        assert track_total == 1


@pytest.mark.asyncio
async def test_scrobble_without_existing_track(isolated_database):
    """Given an empty media library
    When the scrobbler ingests a listen for an unknown track
    Then the listen is stored with raw metadata while the media library remains untouched."""

    adapter, _, ingest = isolated_database

    payload = ScrobblePayload(
        user="listener",
        source="lms",
        listened_at=datetime(2024, 4, 4, 18, 30, tzinfo=timezone.utc),
        track=TrackInput(title="Uncharted Echo"),
        artists=[ArtistInput(name="Mystery Artist")],
        genres=["Unknown"],
    )

    listen_id = await ingest.ingest(payload)

    async with adapter.session_factory() as session:
        listen_row = (
            await session.execute(select(listens).where(listens.c.id == listen_id))
        ).mappings().one()
        assert listen_row["track_id"] is None
        assert listen_row["artist_name_raw"] == "Mystery Artist"
        assert listen_row["track_title_raw"] == "Uncharted Echo"

        linked_artists = (
            await session.execute(
                select(listen_artists).where(listen_artists.c.listen_id == listen_id)
            )
        ).fetchall()
        assert linked_artists == []

        linked_genres = (
            await session.execute(
                select(listen_genres).where(listen_genres.c.listen_id == listen_id)
            )
        ).fetchall()
        assert linked_genres == []

        track_total = (
            await session.execute(select(func.count()).select_from(tracks))
        ).scalar_one()
        assert track_total == 0
