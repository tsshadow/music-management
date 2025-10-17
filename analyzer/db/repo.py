"""Async repository for analyzer operations."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime
from typing import Iterable, Sequence

from sqlalchemy import and_, delete, func, insert, or_, select, update, case
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from backend.app.models import (
    artist_aliases,
    artists,
    genres,
    labels,
    listen_match_candidates,
    listens,
    media_files,
    release_items,
    release_groups,
    releases,
    tag_sources,
    title_aliases,
    track_artists,
    track_genres,
    track_labels,
    track_tag_attributes,
    tracks,
)

from analyzer.matching.normalizer import normalize_text
from analyzer.matching.uid import make_track_uid

__all__ = ["AnalyzerRepository"]


class AnalyzerRepository:
    """Provide low level DB helpers for analyzer services."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def upsert_artist(
        self,
        *,
        display_name: str,
        name_normalized: str,
        sort_name: str,
        mbid: str | None,
    ) -> int:
        async with self.session_factory() as session:
            stmt = select(artists.c.id).where(artists.c.name_normalized == name_normalized)
            result = await session.execute(stmt)
            row = result.first()
            if row:
                artist_id = int(row[0])
                await session.execute(
                    update(artists)
                    .where(artists.c.id == artist_id)
                    .values(
                        name=display_name,
                        sort_name=sort_name,
                        mbid=mbid,
                        updated_at=func.now(),
                    )
                )
            else:
                insert_stmt = insert(artists).values(
                    name=display_name,
                    name_normalized=name_normalized,
                    sort_name=sort_name,
                    mbid=mbid,
                )
                result = await session.execute(insert_stmt)
                artist_id = int(result.inserted_primary_key[0])
            await session.commit()
            return artist_id

    async def get_artist_name(self, artist_id: int) -> str | None:
        async with self.session_factory() as session:
            stmt = select(artists.c.name).where(artists.c.id == artist_id)
            row = await session.execute(stmt)
            record = row.first()
            return record[0] if record else None

    async def upsert_album(
        self,
        *,
        title: str,
        title_normalized: str,
        artist_id: int,
        year: int | None,
        mbid: str | None,
    ) -> int:
        async with self.session_factory() as session:
            stmt = select(release_groups.c.id).where(
                and_(
                    release_groups.c.primary_artist_id == artist_id,
                    release_groups.c.title_normalized == title_normalized,
                )
            )
            result = await session.execute(stmt)
            row = result.first()
            if row:
                album_id = int(row[0])
                await session.execute(
                    update(release_groups)
                    .where(release_groups.c.id == album_id)
                    .values(
                        title=title,
                        primary_artist_id=artist_id,
                        year=year,
                        mbid=mbid,
                        updated_at=func.now(),
                    )
                )
            else:
                insert_stmt = insert(release_groups).values(
                    primary_artist_id=artist_id,
                    title=title,
                    title_normalized=title_normalized,
                    year=year,
                    mbid=mbid,
                )
                result = await session.execute(insert_stmt)
                album_id = int(result.inserted_primary_key[0])

            release_date = None
            if year:
                release_date = datetime(year, 1, 1)

            release_stmt = select(releases.c.id).where(
                releases.c.release_group_id == album_id,
                releases.c.title_normalized == title_normalized,
            )
            if release_date:
                release_stmt = release_stmt.where(releases.c.release_date == release_date.date())
            release_row = await session.execute(release_stmt)
            if release_row.scalar_one_or_none() is None:
                await session.execute(
                    insert(releases).values(
                        release_group_id=album_id,
                        title=title,
                        title_normalized=title_normalized,
                        release_date=release_date.date() if release_date else None,
                    )
                )
            await session.commit()
            return album_id

    async def get_album_title(self, album_id: int | None) -> str | None:
        if not album_id:
            return None
        async with self.session_factory() as session:
            stmt = select(release_groups.c.title).where(release_groups.c.id == album_id)
            row = await session.execute(stmt)
            record = row.first()
            return record[0] if record else None

    async def upsert_track(
        self,
        *,
        title: str,
        title_normalized: str,
        album_id: int | None,
        primary_artist_id: int,
        duration: int | None,
        mbid: str | None,
        isrc: str | None,
        acoustid: str | None,
        track_uid: str,
    ) -> int:
        async with self.session_factory() as session:
            stmt = select(tracks.c.id).where(tracks.c.track_uid == track_uid)
            result = await session.execute(stmt)
            row = result.first()
            if row:
                track_id = int(row[0])
                await session.execute(
                    update(tracks)
                    .where(tracks.c.id == track_id)
                    .values(
                        title=title,
                        title_normalized=title_normalized,
                        album_id=album_id,
                        primary_artist_id=primary_artist_id,
                        duration_secs=duration,
                        mbid=mbid,
                        isrc=isrc,
                        acoustid=acoustid,
                        updated_at=func.now(),
                    )
                )
            else:
                insert_stmt = insert(tracks).values(
                    title=title,
                    title_normalized=title_normalized,
                    album_id=album_id,
                    primary_artist_id=primary_artist_id,
                    duration_secs=duration,
                    mbid=mbid,
                    isrc=isrc,
                    acoustid=acoustid,
                    track_uid=track_uid,
                )
                result = await session.execute(insert_stmt)
                track_id = int(result.inserted_primary_key[0])

            if album_id is not None:
                release_stmt = (
                    select(releases.c.id)
                    .where(releases.c.release_group_id == album_id)
                    .order_by(releases.c.release_date.is_(None), releases.c.release_date)
                )
                release_result = await session.execute(release_stmt)
                release_row = release_result.first()
                if release_row:
                    release_id = int(release_row[0])
                    exists_stmt = select(release_items.c.release_id).where(
                        release_items.c.release_id == release_id,
                        release_items.c.track_id == track_id,
                    )
                    release_item = await session.execute(exists_stmt)
                    if release_item.scalar_one_or_none() is None:
                        await session.execute(
                            insert(release_items).values(
                                release_id=release_id,
                                track_id=track_id,
                                disc_no=1,
                                track_no=1,
                            )
                        )
            await session.commit()
            return track_id

    async def link_track_artists(self, track_id: int, artists_payload: Iterable[tuple[int, str]]) -> None:
        async with self.session_factory() as session:
            for artist_id, role in artists_payload:
                exists_stmt = select(track_artists.c.track_id).where(
                    and_(
                        track_artists.c.track_id == track_id,
                        track_artists.c.artist_id == artist_id,
                        track_artists.c.role == role,
                    )
                )
                existing = await session.execute(exists_stmt)
                if existing.first() is None:
                    await session.execute(
                        insert(track_artists).values(
                            track_id=track_id,
                            artist_id=artist_id,
                            role=role,
                        )
                    )
            await session.commit()

    async def link_track_genres(self, track_id: int, genre_ids: Iterable[int]) -> None:
        async with self.session_factory() as session:
            for genre_id in genre_ids:
                exists_stmt = select(track_genres.c.track_id).where(
                    and_(
                        track_genres.c.track_id == track_id,
                        track_genres.c.genre_id == genre_id,
                    )
                )
                existing = await session.execute(exists_stmt)
                if existing.first() is None:
                    await session.execute(
                        insert(track_genres).values(track_id=track_id, genre_id=genre_id)
                    )
            await session.commit()

    async def link_track_labels(self, track_id: int, label_ids: Iterable[int]) -> None:
        async with self.session_factory() as session:
            for label_id in label_ids:
                exists_stmt = select(track_labels.c.track_id).where(
                    and_(
                        track_labels.c.track_id == track_id,
                        track_labels.c.label_id == label_id,
                    )
                )
                existing = await session.execute(exists_stmt)
                if existing.first() is None:
                    await session.execute(
                        insert(track_labels).values(track_id=track_id, label_id=label_id)
                    )
            await session.commit()

    async def _ensure_tag_source(self, session, name: str, priority: int) -> int:
        stmt = select(tag_sources.c.id).where(tag_sources.c.name == name)
        result = await session.execute(stmt)
        row = result.first()
        if row:
            source_id = int(row[0])
            await session.execute(
                update(tag_sources)
                .where(tag_sources.c.id == source_id)
                .values(priority=priority, updated_at=func.now())
            )
            return source_id
        insert_stmt = insert(tag_sources).values(name=name, priority=priority)
        result = await session.execute(insert_stmt)
        return int(result.inserted_primary_key[0])

    async def set_track_attribute(
        self,
        track_id: int,
        *,
        key: str,
        value: str,
        source: str,
        priority: int = 0,
    ) -> None:
        async with self.session_factory() as session:
            source_id = await self._ensure_tag_source(session, source, priority)
            exists_stmt = select(track_tag_attributes.c.track_id).where(
                and_(
                    track_tag_attributes.c.track_id == track_id,
                    track_tag_attributes.c.key == key,
                )
            )
            result = await session.execute(exists_stmt)
            if result.first():
                await session.execute(
                    update(track_tag_attributes)
                    .where(
                        and_(
                            track_tag_attributes.c.track_id == track_id,
                            track_tag_attributes.c.key == key,
                        )
                    )
                    .values(
                        value=value,
                        source_id=source_id,
                        updated_at=func.now(),
                    )
                )
            else:
                await session.execute(
                    insert(track_tag_attributes).values(
                        track_id=track_id,
                        key=key,
                        value=value,
                        source_id=source_id,
                    )
                )
            await session.commit()

    async def upsert_genre(self, *, name: str, name_normalized: str) -> int:
        async with self.session_factory() as session:
            stmt = select(genres.c.id).where(genres.c.name_normalized == name_normalized)
            result = await session.execute(stmt)
            row = result.first()
            if row:
                genre_id = int(row[0])
            else:
                insert_stmt = insert(genres).values(name=name, name_normalized=name_normalized)
                result = await session.execute(insert_stmt)
                genre_id = int(result.inserted_primary_key[0])
            await session.commit()
            return genre_id

    async def upsert_label(self, *, name: str, name_normalized: str) -> int:
        async with self.session_factory() as session:
            stmt = select(labels.c.id).where(labels.c.name_normalized == name_normalized)
            result = await session.execute(stmt)
            row = result.first()
            if row:
                label_id = int(row[0])
                await session.execute(
                    update(labels)
                    .where(labels.c.id == label_id)
                    .values(name=name, updated_at=func.now())
                )
            else:
                insert_stmt = insert(labels).values(name=name, name_normalized=name_normalized)
                result = await session.execute(insert_stmt)
                label_id = int(result.inserted_primary_key[0])
            await session.commit()
            return label_id

    async def upsert_media_file(
        self,
        *,
        file_path: str,
        file_size: int | None,
        file_mtime: datetime | None,
        audio_hash: str | None,
        duration: int | None,
        metadata: dict,
    ) -> int:
        file_path_hash = hashlib.sha1(file_path.encode("utf-8")).hexdigest()
        async with self.session_factory() as session:
            stmt = select(media_files.c.id).where(media_files.c.file_path_hash == file_path_hash)
            result = await session.execute(stmt)
            row = result.first()
            payload = {
                "file_path": file_path,
                "file_path_hash": file_path_hash,
                "file_size": file_size,
                "file_mtime": file_mtime,
                "audio_hash": audio_hash,
                "duration_secs": duration,
                "parsed_metadata_json": json.dumps(metadata, ensure_ascii=False),
                "last_scan_at": func.now(),
                "updated_at": func.now(),
            }
            if row:
                media_id = int(row[0])
                await session.execute(
                    update(media_files).where(media_files.c.id == media_id).values(**payload)
                )
            else:
                result = await session.execute(insert(media_files).values(**payload))
                media_id = int(result.inserted_primary_key[0])
            await session.commit()
            return media_id

    async def fetch_pending_listens(
        self,
        *,
        since: datetime | None,
        limit: int,
    ) -> Sequence[dict]:
        async with self.session_factory() as session:
            stmt = (
                select(listens)
                .where(listens.c.enrich_status.in_(["pending", "unmatched"]))
                .order_by(listens.c.listened_at.asc())
                .limit(limit)
            )
            if since:
                stmt = stmt.where(listens.c.listened_at >= since)
            rows = await session.execute(stmt)
            return [dict(row._mapping) for row in rows.fetchall()]

    async def find_track_by_uid(self, track_uid: str) -> dict | None:
        async with self.session_factory() as session:
            stmt = select(tracks).where(tracks.c.track_uid == track_uid)
            row = await session.execute(stmt)
            record = row.first()
            return dict(record._mapping) if record else None

    async def search_tracks_by_metadata(
        self,
        *,
        artist: str | None,
        title: str | None,
        duration: int | None,
        limit: int,
    ) -> Sequence[tuple[int, int]]:
        async with self.session_factory() as session:
            filters = []
            normalized_artist = normalize_text(artist) if artist else None
            normalized_title = normalize_text(title) if title else None
            stmt = (
                select(tracks.c.id, tracks.c.duration_secs)
                .select_from(tracks.outerjoin(artists, tracks.c.primary_artist_id == artists.c.id))
                .limit(limit)
            )
            if normalized_artist:
                filters.append(artists.c.name_normalized.like(f"%{normalized_artist}%"))
            if normalized_title:
                filters.append(tracks.c.title_normalized.like(f"%{normalized_title}%"))
            if filters:
                stmt = stmt.where(or_(*filters))
            rows = await session.execute(stmt)
            results = []
            for row in rows.fetchall():
                track_id = int(row[0])
                duration_val = row[1]
                confidence = 50
                if duration is not None and duration_val is not None:
                    if abs(duration_val - duration) <= 2:
                        confidence = 80
                results.append((track_id, confidence))
            return results

    async def link_listen(
        self,
        *,
        listen_id: int,
        track_id: int,
        status: str,
        confidence: int,
    ) -> None:
        async with self.session_factory() as session:
            await session.execute(
                update(listens)
                .where(listens.c.id == listen_id)
                .values(
                    track_id=track_id,
                    enrich_status=status,
                    match_confidence=confidence,
                    last_enriched_at=func.now(),
                )
            )
            await session.execute(
                delete(listen_match_candidates).where(listen_match_candidates.c.listen_id == listen_id)
            )
            await session.commit()

    async def store_candidates(
        self,
        *,
        listen_id: int,
        candidates: Iterable[dict],
    ) -> Sequence[dict]:
        async with self.session_factory() as session:
            await session.execute(
                delete(listen_match_candidates).where(listen_match_candidates.c.listen_id == listen_id)
            )
            stored: list[dict] = []
            for candidate in candidates:
                if not candidate:
                    continue
                track_id = candidate.get("track_id")
                confidence = candidate.get("confidence", 0)
                if track_id is None:
                    continue
                await session.execute(
                    insert(listen_match_candidates).values(
                        listen_id=listen_id,
                        track_id=track_id,
                        confidence=confidence,
                    )
                )
                stored.append({"track_id": track_id, "confidence": confidence})
            await session.commit()
            return stored

    async def mark_listen_status(
        self,
        *,
        listen_id: int,
        status: str,
        confidence: int | None,
    ) -> None:
        async with self.session_factory() as session:
            await session.execute(
                update(listens)
                .where(listens.c.id == listen_id)
                .values(
                    enrich_status=status,
                    match_confidence=confidence,
                    last_enriched_at=func.now(),
                )
            )
            await session.commit()

    async def learn_aliases_from_listen(self, listen_id: int, track_id: int) -> None:
        async with self.session_factory() as session:
            listen_row = await session.execute(
                select(listens.c.artist_name_raw, listens.c.track_title_raw).where(listens.c.id == listen_id)
            )
            listen = listen_row.first()
            if not listen:
                return
            artist_alias = listen[0]
            title_alias = listen[1]
            track_stmt = await session.execute(
                select(tracks.c.primary_artist_id).where(tracks.c.id == track_id)
            )
            track_row = track_stmt.first()
            if track_row and artist_alias:
                alias_stmt = select(artist_aliases.c.id).where(
                    artist_aliases.c.alias_normalized == artist_alias.lower()
                )
                alias_existing = await session.execute(alias_stmt)
                if alias_existing.first() is None:
                    await session.execute(
                        insert(artist_aliases).values(
                            artist_id=track_row[0],
                            alias_normalized=artist_alias.lower(),
                        )
                    )
            if title_alias:
                title_stmt = select(title_aliases.c.id).where(
                    title_aliases.c.alias_normalized == title_alias.lower()
                )
                title_existing = await session.execute(title_stmt)
                if title_existing.first() is None:
                    await session.execute(
                        insert(title_aliases).values(
                            track_id=track_id,
                            alias_normalized=title_alias.lower(),
                        )
                    )
            await session.commit()

    async def refresh_track_uids(self) -> None:
        async with self.session_factory() as session:
            stmt = select(
                tracks.c.id,
                tracks.c.title,
                tracks.c.duration_secs,
                artists.c.name,
                release_groups.c.title.label("album_title"),
            ).select_from(
                tracks.outerjoin(artists, tracks.c.primary_artist_id == artists.c.id)
                .outerjoin(release_groups, tracks.c.album_id == release_groups.c.id)
            )
            rows = await session.execute(stmt)
            for row in rows.fetchall():
                track_id = int(row[0])
                title = row[1]
                duration = row[2]
                artist_name = row[3]
                album_title = row[4]
                uid = make_track_uid(
                    artist=artist_name,
                    title=title,
                    album=album_title,
                    duration=duration,
                )
                await session.execute(
                    update(tracks)
                    .where(tracks.c.id == track_id)
                    .values(track_uid=uid, updated_at=func.now())
                )
            await session.commit()

    async def fetch_library_summary(self) -> dict:
        """Return aggregate counts used by the analyzer dashboard."""

        async with self.session_factory() as session:
            total_files = await session.scalar(select(func.count(media_files.c.id))) or 0
            songs_filter = or_(tracks.c.duration_secs.is_(None), tracks.c.duration_secs < 600)
            songs_count = await session.scalar(
                select(func.count()).select_from(tracks).where(songs_filter)
            ) or 0
            livesets_count = await session.scalar(
                select(func.count())
                .select_from(tracks)
                .where(
                    tracks.c.duration_secs.is_not(None),
                    tracks.c.duration_secs >= 600,
                )
            ) or 0

            artist_song_count = func.count(tracks.c.id).label("songs")
            artist_rows = await session.execute(
                select(artists.c.name.label("artist"), artist_song_count)
                .select_from(tracks.join(artists, tracks.c.primary_artist_id == artists.c.id))
                .where(songs_filter)
                .group_by(artists.c.id, artists.c.name)
                .order_by(artist_song_count.desc(), artists.c.name)
                .limit(50)
            )
            artists_summary = [
                {"artist": row.artist, "songs": int(row.songs)} for row in artist_rows.fetchall()
            ]

            genre_song_count = func.count(track_genres.c.track_id).label("songs")
            genre_rows = await session.execute(
                select(genres.c.name.label("genre"), genre_song_count)
                .select_from(
                    genres.join(track_genres, genres.c.id == track_genres.c.genre_id).join(
                        tracks, track_genres.c.track_id == tracks.c.id
                    )
                )
                .where(songs_filter)
                .group_by(genres.c.id, genres.c.name)
                .order_by(genre_song_count.desc(), genres.c.name)
                .limit(50)
            )
            genres_summary = [
                {"genre": row.genre, "songs": int(row.songs)} for row in genre_rows.fetchall()
            ]

            return {
                "files": int(total_files),
                "songs": int(songs_count),
                "livesets": int(livesets_count),
                "artists": artists_summary,
                "genres": genres_summary,
            }

    async def fetch_library_artists(self, *, limit: int, offset: int) -> tuple[list[dict], int]:
        """Return artists ordered by song count within the library."""

        async with self.session_factory() as session:
            song_count = func.count(tracks.c.id).label("count")
            base_query = (
                select(
                    artists.c.id.label("artist_id"),
                    artists.c.name.label("artist"),
                    song_count,
                )
                .select_from(tracks.join(artists, tracks.c.primary_artist_id == artists.c.id))
                .group_by(artists.c.id, artists.c.name)
            )
            total_query = select(func.count()).select_from(base_query.subquery())
            total = await session.scalar(total_query) or 0
            rows = await session.execute(
                base_query.order_by(song_count.desc(), artists.c.name).offset(offset).limit(limit)
            )
            items = [
                {
                    "artist_id": int(row.artist_id),
                    "artist": row.artist,
                    "count": int(row.count),
                }
                for row in rows.fetchall()
            ]
            return items, int(total)

    async def fetch_library_albums(self, *, limit: int, offset: int) -> tuple[list[dict], int]:
        """Return albums ordered by song count within the library."""

        async with self.session_factory() as session:
            song_count = func.count(tracks.c.id).label("count")
            base_query = (
                select(
                    release_groups.c.id.label("album_id"),
                    release_groups.c.title.label("album"),
                    release_groups.c.year.label("release_year"),
                    artists.c.name.label("artist"),
                    song_count,
                )
                .select_from(
                    release_groups.join(artists, release_groups.c.primary_artist_id == artists.c.id).join(
                        tracks, tracks.c.album_id == release_groups.c.id
                    )
                )
                .group_by(release_groups.c.id, release_groups.c.title, release_groups.c.year, artists.c.name)
            )
            total_query = select(func.count()).select_from(base_query.subquery())
            total = await session.scalar(total_query) or 0
            rows = await session.execute(
                base_query.order_by(song_count.desc(), release_groups.c.title).offset(offset).limit(limit)
            )
            items = [
                {
                    "album_id": int(row.album_id),
                    "album": row.album,
                    "artist": row.artist,
                    "release_year": row.release_year,
                    "count": int(row.count),
                }
                for row in rows.fetchall()
            ]
            return items, int(total)

    async def fetch_library_genres(self, *, limit: int, offset: int) -> tuple[list[dict], int]:
        """Return genres ordered by song count within the library."""

        async with self.session_factory() as session:
            song_count = func.count(track_genres.c.track_id).label("count")
            base_query = (
                select(
                    genres.c.id.label("genre_id"),
                    genres.c.name.label("genre"),
                    song_count,
                )
                .select_from(
                    genres.join(track_genres, genres.c.id == track_genres.c.genre_id).join(
                        tracks, track_genres.c.track_id == tracks.c.id
                    )
                )
                .group_by(genres.c.id, genres.c.name)
            )
            total_query = select(func.count()).select_from(base_query.subquery())
            total = await session.scalar(total_query) or 0
            rows = await session.execute(
                base_query.order_by(song_count.desc(), genres.c.name).offset(offset).limit(limit)
            )
            items = [
                {
                    "genre_id": int(row.genre_id),
                    "genre": row.genre,
                    "count": int(row.count),
                }
                for row in rows.fetchall()
            ]
            return items, int(total)

    async def fetch_library_tracks(self, *, limit: int, offset: int) -> tuple[list[dict], int]:
        """Return tracks ordered alphabetically for the library view."""

        async with self.session_factory() as session:
            base_query = (
                select(
                    tracks.c.id.label("track_id"),
                    tracks.c.title.label("track"),
                    release_groups.c.title.label("album"),
                    artists.c.name.label("artist"),
                    tracks.c.duration_secs.label("duration_secs"),
                )
                .select_from(
                    tracks.outerjoin(release_groups, tracks.c.album_id == release_groups.c.id).outerjoin(
                        artists, tracks.c.primary_artist_id == artists.c.id
                    )
                )
            )
            total = await session.scalar(select(func.count(tracks.c.id))) or 0
            name_sort = case((artists.c.name.is_(None), 1), else_=0)
            rows = await session.execute(
                base_query
                .order_by(name_sort, artists.c.name.asc(), tracks.c.title.asc())
                .offset(offset)
                .limit(limit)
            )
            records = rows.fetchall()
            track_ids = [int(row.track_id) for row in records]
            label_map: dict[int, list[str]] = defaultdict(list)
            catalog_map: dict[int, str] = {}
            festival_map: dict[int, str] = {}
            if track_ids:
                label_rows = await session.execute(
                    select(track_labels.c.track_id, labels.c.name)
                    .select_from(track_labels.join(labels, track_labels.c.label_id == labels.c.id))
                    .where(track_labels.c.track_id.in_(track_ids))
                    .order_by(track_labels.c.track_id, labels.c.name)
                )
                for row in label_rows.fetchall():
                    label_map[int(row.track_id)].append(row.name)

                catalog_rows = await session.execute(
                    select(
                        track_tag_attributes.c.track_id,
                        track_tag_attributes.c.value,
                    )
                    .select_from(
                        track_tag_attributes.join(
                            tag_sources,
                            track_tag_attributes.c.source_id == tag_sources.c.id,
                        )
                    )
                    .where(
                        track_tag_attributes.c.key == "catalog_number",
                        track_tag_attributes.c.track_id.in_(track_ids),
                    )
                    .order_by(
                        track_tag_attributes.c.track_id,
                        tag_sources.c.priority.asc(),
                        track_tag_attributes.c.updated_at.desc(),
                    )
                )
                for row in catalog_rows.fetchall():
                    track_id = int(row.track_id)
                    if track_id not in catalog_map:
                        catalog_map[track_id] = row.value

                festival_rows = await session.execute(
                    select(
                        track_tag_attributes.c.track_id,
                        track_tag_attributes.c.value,
                    )
                    .select_from(
                        track_tag_attributes.join(
                            tag_sources,
                            track_tag_attributes.c.source_id == tag_sources.c.id,
                        )
                    )
                    .where(
                        track_tag_attributes.c.key == "festival",
                        track_tag_attributes.c.track_id.in_(track_ids),
                    )
                    .order_by(
                        track_tag_attributes.c.track_id,
                        tag_sources.c.priority.asc(),
                        track_tag_attributes.c.updated_at.desc(),
                    )
                )
                for row in festival_rows.fetchall():
                    track_id = int(row.track_id)
                    if track_id not in festival_map:
                        festival_map[track_id] = row.value

            items = [
                {
                    "track_id": int(row.track_id),
                    "track": row.track,
                    "album": row.album,
                    "artist": row.artist,
                    "duration_secs": row.duration_secs,
                    "labels": label_map.get(int(row.track_id), []),
                    "catalog_number": catalog_map.get(int(row.track_id)),
                    "festival": festival_map.get(int(row.track_id)),
                    "count": 1,
                }
                for row in records
            ]
            return items, int(total)

    async def reset_library(self) -> dict[str, int]:
        """Remove analyzer-managed media library data."""

        tables = [
            track_tag_attributes,
            track_labels,
            track_genres,
            track_artists,
            title_aliases,
            media_files,
            tracks,
            release_groups,
            artist_aliases,
            labels,
            genres,
            artists,
        ]
        results: dict[str, int] = {}
        async with self.session_factory() as session:
            for table in tables:
                outcome = await session.execute(delete(table))
                results[table.name] = int(outcome.rowcount or 0)
            await session.commit()
        return results
