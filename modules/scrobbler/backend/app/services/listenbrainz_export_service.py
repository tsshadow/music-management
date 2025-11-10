from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from ..db.adapter import DatabaseAdapter


class ListenBrainzExportService:
    """Push stored listens to the ListenBrainz submission endpoint."""

    def __init__(
        self,
        adapter: DatabaseAdapter,
        *,
        base_url: str = "https://api.listenbrainz.org/1",
        client_factory: Callable[..., httpx.AsyncClient] | None = None,
    ) -> None:
        self.adapter = adapter
        self.base_url = base_url.rstrip("/")
        self._client_factory = client_factory or (lambda **kwargs: httpx.AsyncClient(**kwargs))

    async def export_user(
        self,
        *,
        user: str,
        token: str,
        since: datetime | None = None,
        listen_type: str = "import",
        batch_size: int = 100,
    ) -> dict[str, int]:
        """Export listens for the given user to ListenBrainz."""

        if not token:
            raise ValueError("ListenBrainz token is required")

        exported = 0
        skipped = 0
        batches = 0
        offset = 0

        headers = {"Authorization": f"Token {token}"}

        async with self._client_factory(
            base_url=self.base_url,
            headers=headers,
            timeout=30.0,
        ) as client:
            while True:
                rows = await self.adapter.fetch_listens_for_export(
                    user=user,
                    since=since,
                    limit=batch_size,
                    offset=offset,
                )
                if not rows:
                    break

                payload = []
                for row in rows:
                    ts = self._to_timestamp(row.get("listened_at"))
                    metadata = self._to_track_metadata(row)
                    if ts is None or metadata is None:
                        skipped += 1
                        continue
                    payload.append({"listened_at": ts, "track_metadata": metadata})

                if payload:
                    response = await client.post(
                        "/submit-listens",
                        json={"listen_type": listen_type, "payload": payload},
                    )
                    response.raise_for_status()
                    exported += len(payload)
                    batches += 1
                else:
                    # Nothing to submit for this batch but still move the window forward.
                    skipped += len(rows)

                if len(rows) < batch_size:
                    break

                offset += batch_size

        return {"exported": exported, "skipped": skipped, "batches": batches}

    @staticmethod
    def _to_timestamp(value: Any) -> int | None:
        if not isinstance(value, datetime):
            return None
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())

    @staticmethod
    def _to_track_metadata(row: dict[str, Any]) -> dict[str, Any] | None:
        track = row.get("track") or {}
        title = track.get("title")
        if not title:
            return None

        artist_name = ListenBrainzExportService._artist_name(row)
        if not artist_name:
            return None

        metadata: dict[str, Any] = {
            "track_name": title,
            "artist_name": artist_name,
        }

        album = track.get("album")
        if album:
            metadata["release_name"] = album

        additional: dict[str, Any] = {}
        duration = track.get("duration") or row.get("listen_duration")
        if duration:
            additional["duration"] = duration

        track_no = track.get("track_no")
        if track_no:
            additional["tracknumber"] = track_no

        disc_no = track.get("disc_no")
        if disc_no:
            additional["discnumber"] = disc_no

        mbid = track.get("mbid")
        if mbid:
            additional["recording_mbid"] = mbid

        isrc = track.get("isrc")
        if isrc:
            additional["isrc"] = isrc

        origin_track_id = row.get("source_track_id")
        if origin_track_id:
            additional["origin_track_id"] = origin_track_id

        genres = row.get("genres") or []
        if genres:
            additional["tags"] = genres

        if additional:
            metadata["additional_info"] = additional

        return metadata

    @staticmethod
    def _artist_name(row: dict[str, Any]) -> str | None:
        artists = row.get("artists") or []
        primary = [artist["name"] for artist in artists if artist.get("role") == "primary" and artist.get("name")]
        if primary:
            return ", ".join(primary)

        listen_artists = row.get("listen_artists") or []
        names = [name for name in listen_artists if name]
        if names:
            return ", ".join(dict.fromkeys(names))

        fallback = [artist.get("name") for artist in artists if artist.get("name")]
        if fallback:
            return ", ".join(dict.fromkeys(fallback))

        return None
