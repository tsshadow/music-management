"""Service responsible for maintaining the normalized music library."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from analyzer.db.repo import AnalyzerRepository
from analyzer.matching.normalizer import normalize_text
from analyzer.matching.uid import make_track_uid

__all__ = ["LibraryService"]


class LibraryService:
    """High level library operations wrapping the repository."""

    def __init__(self, repo: AnalyzerRepository) -> None:
        self.repo = repo

    async def upsert_artist(
        self,
        name: str,
        *,
        sort_name: str | None = None,
        mbid: str | None = None,
    ) -> int:
        normalized = normalize_text(name)
        return await self.repo.upsert_artist(
            display_name=name,
            name_normalized=normalized,
            sort_name=sort_name or normalized,
            mbid=mbid,
        )

    async def upsert_album(
        self,
        title: str,
        *,
        artist_id: int,
        year: int | None = None,
        mbid: str | None = None,
    ) -> int:
        return await self.repo.upsert_album(
            title=title,
            title_normalized=normalize_text(title),
            artist_id=artist_id,
            year=year,
            mbid=mbid,
        )

    async def upsert_track(
        self,
        title: str,
        *,
        primary_artist_id: int,
        duration: int | None = None,
        album_id: int | None = None,
        mbid: str | None = None,
        isrc: str | None = None,
        acoustid: str | None = None,
        track_uid: str | None = None,
    ) -> int:
        uid = track_uid or make_track_uid(
            artist=await self.repo.get_artist_name(primary_artist_id),
            title=title,
            album=await self.repo.get_album_title(album_id) if album_id else None,
            duration=duration,
        )
        return await self.repo.upsert_track(
            title=title,
            title_normalized=normalize_text(title),
            album_id=album_id,
            primary_artist_id=primary_artist_id,
            duration=duration,
            mbid=mbid,
            isrc=isrc,
            acoustid=acoustid,
            track_uid=uid,
        )

    async def link_track_artists(
        self,
        track_id: int,
        artists: Iterable[tuple[int, str]],
    ) -> None:
        await self.repo.link_track_artists(track_id, artists)

    async def link_track_genres(self, track_id: int, genre_ids: Iterable[int]) -> None:
        await self.repo.link_track_genres(track_id, genre_ids)

    async def link_track_labels(self, track_id: int, label_ids: Iterable[int]) -> None:
        await self.repo.link_track_labels(track_id, label_ids)

    async def upsert_genre(self, name: str) -> int:
        return await self.repo.upsert_genre(name=name, name_normalized=normalize_text(name))

    async def upsert_label(self, name: str) -> int:
        return await self.repo.upsert_label(name=name, name_normalized=normalize_text(name))

    async def register_media_file(
        self,
        *,
        file_path: str,
        file_size: int | None,
        file_mtime: datetime | None,
        audio_hash: str | None,
        duration: int | None,
        metadata: dict,
    ) -> int:
        return await self.repo.upsert_media_file(
            file_path=file_path,
            file_size=file_size,
            file_mtime=file_mtime,
            audio_hash=audio_hash,
            duration=duration,
            metadata=metadata,
        )
