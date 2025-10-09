from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID

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
        musicbrainz_base_url: str = "https://musicbrainz.org/ws/2",
        musicbrainz_user_agent: str = "scrobbler/1.0 (https://github.com/)",
        client_factory: Callable[..., httpx.AsyncClient] | None = None,
    ) -> None:
        """Store dependencies and prepare the async client factory."""

        self.ingest_service = ingest_service
        self.base_url = base_url.rstrip("/")
        self.musicbrainz_base_url = (
            musicbrainz_base_url.rstrip("/") if musicbrainz_base_url else ""
        )
        self.musicbrainz_user_agent = musicbrainz_user_agent
        self._client_factory = client_factory or (lambda **kwargs: httpx.AsyncClient(**kwargs))
        self._genre_cache: dict[str, list[str]] = {}

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
                    scrobble = await self._to_payload(user, listen, client)
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

    async def _to_payload(
        self,
        user: str,
        listen: dict[str, Any],
        client: httpx.AsyncClient,
    ) -> ScrobblePayload | None:
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
        mbid = self._get_recording_mbid(listen)
        isrc = additional.get("isrc")
        source_track_id = listen.get("recording_msid") or additional.get("track_msid")

        artist_names: list[str] = []
        raw_artist = metadata.get("artist_name")
        if isinstance(raw_artist, list):
            artist_names = [name for name in raw_artist if isinstance(name, str)]
        elif isinstance(raw_artist, str) and raw_artist.strip():
            artist_names = [raw_artist.strip()]

        artists = [ArtistInput(name=name) for name in artist_names]

        genres = self._extract_genres(listen)
        if not genres:
            genres = await self._fetch_remote_genres(listen, client)

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

    async def _fetch_remote_genres(
        self,
        listen: dict[str, Any],
        client: httpx.AsyncClient,
    ) -> list[str]:
        """Retrieve genres from ListenBrainz or MusicBrainz when missing locally."""

        recording_mbid = self._get_recording_mbid(listen)
        if recording_mbid is None:
            return []

        if recording_mbid in self._genre_cache:
            return self._genre_cache[recording_mbid]

        genres: list[str] = []

        genres = await self._fetch_listenbrainz_metadata(recording_mbid, client)
        if not genres:
            genres = await self._fetch_musicbrainz_tags(recording_mbid)

        self._genre_cache[recording_mbid] = genres
        return genres

    async def _fetch_listenbrainz_metadata(
        self,
        recording_mbid: str,
        client: httpx.AsyncClient,
    ) -> list[str]:
        """Request ListenBrainz cached metadata for a specific recording."""

        try:
            response = await client.get(f"/metadata/recording/{recording_mbid}")
        except httpx.HTTPError:
            return []

        if response.status_code >= 400:
            return []

        payload = response.json() or {}
        metadata = payload.get("track_metadata") or {}
        if not metadata:
            return []

        remote_listen = {"track_metadata": metadata}
        return self._extract_genres(remote_listen)

    async def _fetch_musicbrainz_tags(self, recording_mbid: str) -> list[str]:
        """Fetch genre tags directly from MusicBrainz when ListenBrainz lacks them."""

        if not self.musicbrainz_base_url:
            return []

        try:
            async with self._client_factory(
                base_url=self.musicbrainz_base_url,
                headers={
                    "User-Agent": self.musicbrainz_user_agent,
                    "Accept": "application/json",
                },
                timeout=30.0,
            ) as client:
                response = await client.get(
                    f"/recording/{recording_mbid}",
                    params={"inc": "tags", "fmt": "json"},
                )
        except httpx.HTTPError:
            return []

        if response.status_code >= 400:
            return []

        data = response.json() or {}
        tags = data.get("tags") or []
        remote_listen = {"track_metadata": {"additional_info": {"tags": tags}}}
        return self._extract_genres(remote_listen)

    @staticmethod
    def _get_recording_mbid(listen: dict[str, Any]) -> str | None:
        """Return the best available recording MBID for the listen."""

        metadata = listen.get("track_metadata") or {}
        additional = metadata.get("additional_info") or {}

        for value in (
            additional.get("recording_mbid"),
            metadata.get("recording_mbid"),
            listen.get("recording_mbid"),
        ):
            mbid = ListenBrainzImportService._validate_uuid(value)
            if mbid:
                return mbid

        mapping = metadata.get("mbid_mapping") or {}
        mbid = ListenBrainzImportService._validate_uuid(mapping.get("recording_mbid"))
        if mbid:
            return mbid

        return None

    @staticmethod
    def _validate_uuid(value: Any) -> str | None:
        """Return the value if it is a valid UUID string."""

        if not isinstance(value, str):
            return None
        try:
            UUID(value)
        except (TypeError, ValueError):
            return None
        return value

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

    @staticmethod
    def _extract_genres(listen: dict[str, Any]) -> list[str]:
        """Return unique, normalized genre names from ListenBrainz metadata."""

        metadata = listen.get("track_metadata") or {}
        additional = metadata.get("additional_info") or {}

        candidates = [
            metadata.get("genres"),
            metadata.get("tags"),
            additional.get("genres"),
            additional.get("genre"),
            additional.get("tags"),
            additional.get("musicbrainz_tags"),
            additional.get("artist_tags"),
            additional.get("artist_genres"),
            additional.get("track_tags"),
            additional.get("release_tags"),
            additional.get("release_group_tags"),
            additional.get("recording_tags"),
            additional.get("work_tags"),
            listen.get("tags"),
        ]

        normalized: list[str] = []
        seen: set[str] = set()

        def add(value: Any) -> None:
            if isinstance(value, str):
                name = value.strip()
                if not name:
                    return
                key = name.casefold()
                if key not in seen:
                    seen.add(key)
                    normalized.append(name)
                return

            if isinstance(value, (list, tuple, set)):
                for item in value:
                    add(item)
                return

            if isinstance(value, dict):
                matched = False
                for key in ("name", "value", "tag", "genre"):
                    if key in value:
                        matched = True
                        add(value[key])
                if not matched:
                    for item in value.values():
                        add(item)

        for candidate in candidates:
            add(candidate)

        return normalized
