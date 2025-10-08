from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from ..schemas.common import ArtistInput, ScrobblePayload, TrackInput
from .ingest_service import IngestService


class ListenBrainzImportService:
    """Handle ListenBrainz history imports through the public API."""

    def __init__(
        self,
        ingest_service: IngestService,
        *,
        base_url: str = "https://api.listenbrainz.org/1",
        client_factory: Callable[..., httpx.AsyncClient] | None = None,
    ) -> None:
        """Store dependencies and prepare the async client factory."""

        self.ingest_service = ingest_service
        self.base_url = base_url.rstrip("/")
        self._client_factory = client_factory or (lambda **kwargs: httpx.AsyncClient(**kwargs))

    async def import_user(
        self,
        *,
        user: str,
        token: str | None = None,
        since: datetime | None = None,
        page_size: int = 100,
        max_pages: int | None = None,
    ) -> dict[str, int]:
        """Fetch ListenBrainz listens for a user and ingest them locally."""

        headers = {"Authorization": f"Token {token}"} if token else None
        processed = 0
        imported = 0
        skipped = 0
        pages = 0
        min_ts = int(since.timestamp()) if since else None
        max_ts: int | None = None

        async with self._client_factory(
            base_url=self.base_url,
            headers=headers,
            timeout=30.0,
        ) as client:
            while True:
                params: dict[str, Any] = {"count": page_size}
                if min_ts is not None:
                    params["min_ts"] = min_ts
                if max_ts is not None:
                    params["max_ts"] = max_ts
                response = await client.get(f"/user/{user}/listens", params=params)
                response.raise_for_status()
                payload = response.json().get("payload", {})
                listens = payload.get("listens") or []
                if not listens:
                    break
                earliest: int | None = None
                for listen in listens:
                    scrobble = self._to_payload(user, listen)
                    if scrobble is None:
                        skipped += 1
                        continue
                    processed += 1
                    _, created = await self.ingest_service.ingest_with_status(scrobble)
                    if created:
                        imported += 1
                    ts = listen.get("listened_at")
                    if isinstance(ts, int):
                        earliest = ts if earliest is None else min(earliest, ts)
                pages += 1
                if max_pages is not None and pages >= max_pages:
                    break
                if earliest is None:
                    break
                max_ts = earliest - 1
        return {
            "processed": processed,
            "imported": imported,
            "skipped": skipped,
            "pages": pages,
        }

    def _to_payload(self, user: str, listen: dict[str, Any]) -> ScrobblePayload | None:
        """Convert a ListenBrainz listen into the local scrobble schema."""

        metadata = listen.get("track_metadata") or {}
        track_title = metadata.get("track_name")
        listened_at = listen.get("listened_at")
        if not track_title or not isinstance(listened_at, int):
            return None
        listened_dt = datetime.fromtimestamp(listened_at, tz=timezone.utc)
        additional = metadata.get("additional_info") or {}
        duration = self._coerce_int(additional.get("duration"))
        track_no = self._coerce_int(
            additional.get("tracknumber") or additional.get("track_number")
        )
        disc_no = self._coerce_int(
            additional.get("discnumber") or additional.get("disc_number")
        )
        mbid = (
            additional.get("recording_mbid")
            or listen.get("recording_mbid")
            or listen.get("recording_msid")
        )
        isrc = additional.get("isrc")
        source_track_id = listen.get("recording_msid") or additional.get("track_msid")

        artist_names: list[str] = []
        raw_artist = metadata.get("artist_name")
        if isinstance(raw_artist, list):
            artist_names = [name for name in raw_artist if isinstance(name, str)]
        elif isinstance(raw_artist, str) and raw_artist.strip():
            artist_names = [raw_artist.strip()]

        artists = [ArtistInput(name=name) for name in artist_names]

        raw_tags = additional.get("tags")
        if isinstance(raw_tags, list):
            genres = [str(tag) for tag in raw_tags if str(tag).strip()]
        else:
            genres = []

        track = TrackInput(
            title=track_title,
            album=metadata.get("release_name"),
            album_year=None,
            track_no=track_no,
            disc_no=disc_no,
            duration_secs=duration,
            mbid=mbid,
            isrc=isrc,
        )
        return ScrobblePayload(
            user=user,
            source="listenbrainz",
            listened_at=listened_dt,
            duration_secs=duration,
            track=track,
            source_track_id=source_track_id,
            artists=artists,
            genres=genres,
        )

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        """Convert ListenBrainz numeric values to integers when possible."""

        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.strip():
            try:
                return int(float(value))
            except ValueError:
                return None
        return None
