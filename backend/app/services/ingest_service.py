from __future__ import annotations

from datetime import datetime

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

        album_id = None
        if payload.track.album:
            album_id = await self.adapter.upsert_album(
                payload.track.album,
                release_year=payload.track.album_year,
            )

        track_id = await self.adapter.upsert_track(
            title=payload.track.title,
            album_id=album_id,
            duration_secs=payload.track.duration_secs,
            disc_no=payload.track.disc_no,
            track_no=payload.track.track_no,
            mbid=payload.track.mbid,
            isrc=payload.track.isrc,
        )

        artist_ids: list[int] = []
        for artist in payload.artists:
            artist_id = await self.adapter.upsert_artist(artist.name)
            artist_ids.append(artist_id)
        if artist_ids:
            await self.adapter.link_track_artists(
                track_id, [(artist_id, artist.role) for artist_id, artist in zip(artist_ids, payload.artists)]
            )

        genre_ids: list[int] = []
        for genre_name in payload.genres:
            genre_id = await self.adapter.upsert_genre(genre_name)
            genre_ids.append(genre_id)
        if genre_ids:
            await self.adapter.link_track_genres(track_id, genre_ids)

        listen_id, created = await self.adapter.insert_listen(
            user_id=user_id,
            track_id=track_id,
            listened_at=payload.listened_at,
            source=payload.source,
            source_track_id=payload.source_track_id,
            position_secs=payload.position_secs,
            duration_secs=payload.duration_secs,
            artist_ids=artist_ids,
            genre_ids=genre_ids,
        )
        return listen_id, created
