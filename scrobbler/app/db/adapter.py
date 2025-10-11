from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping, Tuple, Protocol


class DatabaseAdapter(Protocol):
    async def connect(self) -> None: ...
    async def close(self) -> None: ...

    async def get_config(self) -> Mapping[str, str]: ...
    async def update_config(self, kv: Mapping[str, str]) -> None: ...

    async def upsert_user(self, username: str) -> int: ...
    async def upsert_artist(self, name: str, mbid: str | None = None) -> int: ...
    async def upsert_genre(self, name: str) -> int: ...
    async def upsert_album(
        self,
        title: str,
        *,
        artist_id: int,
        release_year: int | None = None,
        mbid: str | None = None,
    ) -> int: ...

    async def upsert_track(
        self,
        *,
        title: str,
        album_id: int | None,
        primary_artist_id: int | None,
        duration_secs: int | None,
        disc_no: int | None,
        track_no: int | None,
        mbid: str | None,
        isrc: str | None,
        acoustid: str | None,
        track_uid: str | None,
    ) -> int: ...

    async def link_track_artists(self, track_id: int, artists: list[tuple[int, str]]) -> None: ...
    async def link_track_genres(self, track_id: int, genre_ids: Iterable[int]) -> None: ...

    async def insert_listen(
        self,
        *,
        user_id: int,
        track_id: int,
        listened_at: datetime,
        source: str,
        source_track_id: str | None,
        position_secs: int | None,
        duration_secs: int | None,
        artist_name_raw: str | None,
        track_title_raw: str | None,
        album_title_raw: str | None,
        artist_ids: Iterable[int],
        genre_ids: Iterable[int],
    ) -> Tuple[int, bool]: ...

    async def fetch_recent_listens(self, limit: int = 10) -> list[dict[str, Any]]: ...
    async def count_listens(self) -> int: ...
    async def delete_all_listens(self) -> None: ...
    async def fetch_listens_for_export(
        self,
        *,
        user: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]: ...

    async def stats_artists(self, period: str, value: str | None) -> list[dict[str, Any]]: ...
    async def stats_genres(self, period: str, value: str | None) -> list[dict[str, Any]]: ...
    async def stats_albums(self, period: str, value: str | None) -> list[dict[str, Any]]: ...
    async def stats_tracks(self, period: str, value: str | None) -> list[dict[str, Any]]: ...
    async def stats_top_artist_by_genre(self, year: int) -> list[dict[str, Any]]: ...
    async def stats_time_of_day(self, year: int, period: str) -> list[dict[str, Any]]: ...
