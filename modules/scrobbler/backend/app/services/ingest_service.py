from __future__ import annotations

from datetime import datetime

from analyzer.matching.uid import make_track_uid

from ..db.adapter import DatabaseAdapter
from ..schemas.common import ScrobblePayload


class IngestService:
    """Handle normalization and persistence of incoming scrobble payloads."""

    def __init__(self, adapter: DatabaseAdapter):
        """Initialize the service with a database adapter implementation."""

        self.adapter = adapter

    async def ingest(self, payload: ScrobblePayload) -> int:
        """Persist a scrobble payload and return the resulting listen id."""

        listen_id, _ = await self.ingest_with_status(payload)
        return listen_id

    async def ingest_with_status(self, payload: ScrobblePayload) -> tuple[int, bool]:
        """Persist a scrobble payload and report whether it was newly created."""

        user_id = await self.adapter.upsert_user(payload.user)

        artist_ids: list[int] = []
        primary_artist_id: int | None = None
        primary_artist_name: str | None = None
        for artist in payload.artists:
            artist_id = await self.adapter.lookup_artist_id(artist.name)
            if artist_id is not None:
                artist_ids.append(artist_id)
            if primary_artist_id is None or artist.role == "primary":
                primary_artist_id = artist_id
                primary_artist_name = artist.name
        if primary_artist_id is None and payload.artists:
            primary_artist_name = payload.artists[0].name

        album_id = None
        if payload.track.album:
            album_id = await self.adapter.lookup_album_id(
                title=payload.track.album,
                artist_id=primary_artist_id,
                release_year=payload.track.album_year,
            )

        track_uid = make_track_uid(
            artist=primary_artist_name,
            title=payload.track.title,
            album=payload.track.album,
            duration=payload.track.duration_secs,
        )

        track_id = await self.adapter.lookup_track_id_by_uid(track_uid)
        if track_id is None:
            track_id = await self.adapter.lookup_track_details(
                title=payload.track.title,
                artist_id=primary_artist_id,
                album_id=album_id,
            )

        if track_id is not None and not artist_ids:
            artist_ids = await self.adapter.lookup_track_artist_ids(track_id)

        genre_ids: list[int] = []
        for genre_name in payload.genres:
            genre_id = await self.adapter.lookup_genre_id(genre_name)
            if genre_id is not None:
                genre_ids.append(genre_id)
        if track_id is not None and not genre_ids:
            genre_ids = await self.adapter.lookup_track_genre_ids(track_id)

        listen_id, created = await self.adapter.insert_listen(
            user_id=user_id,
            track_id=track_id,
            listened_at=payload.listened_at,
            source=payload.source,
            source_track_id=payload.source_track_id,
            position_secs=payload.position_secs,
            duration_secs=payload.duration_secs,
            artist_name_raw=primary_artist_name or (payload.artists[0].name if payload.artists else None),
            track_title_raw=payload.track.title,
            album_title_raw=payload.track.album,
            raw_payload=payload.model_dump(mode="json"),
            artist_ids=artist_ids,
            genre_ids=genre_ids,
        )
        return listen_id, created
