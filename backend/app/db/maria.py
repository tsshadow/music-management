from __future__ import annotations

from collections import defaultdict
import json
import re
from datetime import datetime, time, timedelta, timezone
from typing import Any, Iterable, Mapping

from sqlalchemy import (
    Integer,
    and_,
    cast,
    case,
    delete,
    func,
    insert,
    or_,
    select,
    true,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from analyzer.matching.normalizer import normalize_text

from .adapter import DatabaseAdapter
from ..models import (
    release_groups,
    artists,
    config,
    genres,
    listen_artists,
    listen_genres,
    listens,
    listens_raw,
    track_artists,
    track_genres,
    tracks,
    users,
)


class MariaDBAdapter(DatabaseAdapter):
    """SQLAlchemy adapter that targets MariaDB while remaining SQLite-compatible for tests."""

    def __init__(self, engine: AsyncEngine):
        """Store the async engine and session factory for later database work."""

        self.engine = engine
        self._dialect_name = getattr(engine.dialect, "name", "")
        self.session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def connect(self) -> None:  # pragma: no cover - handled by SQLAlchemy
        """Open a connection to validate connectivity."""

        async with self.engine.begin() as conn:
            await conn.run_sync(lambda _: None)

    async def close(self) -> None:
        """Dispose of the underlying engine resources."""

        await self.engine.dispose()

    async def get_config(self) -> Mapping[str, str]:
        """Return all configuration key-value pairs stored in the database."""

        async with self.session_factory() as session:
            rows = await session.execute(select(config.c.key, config.c.value))
            return {row.key: row.value for row in rows}

    async def update_config(self, kv: Mapping[str, str]) -> None:
        """Insert or update configuration keys with the provided values."""

        async with self.session_factory() as session:
            for key, value in kv.items():
                try:
                    await session.execute(insert(config).values(key=key, value=value))
                except IntegrityError:
                    await session.rollback()
                    await session.execute(
                        config.update().where(config.c.key == key).values(value=value)
                    )
                else:
                    await session.flush()
            await session.commit()

    async def _get_or_create(self, stmt, values: Mapping[str, Any], table) -> int:
        """Return an existing primary key for stmt or insert a new row with values."""

        async with self.session_factory() as session:
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing is not None:
                return int(existing)
            res = await session.execute(insert(table).values(**values))
            await session.commit()
            return int(res.inserted_primary_key[0])

    async def upsert_user(self, username: str) -> int:
        """Return the user id for the username, creating a row if needed."""

        stmt = select(users.c.id).where(func.lower(users.c.username) == username.lower())
        return await self._get_or_create(stmt, {"username": username}, users)

    async def lookup_artist_id(self, name: str) -> int | None:
        """Return the artist identifier if it exists in the media library."""

        normalized = normalize_text(name)
        async with self.session_factory() as session:
            stmt = select(artists.c.id).where(artists.c.name_normalized == normalized)
            existing = (await session.execute(stmt)).scalar_one_or_none()
            return int(existing) if existing is not None else None

    async def lookup_genre_id(self, name: str) -> int | None:
        """Return the genre identifier if it exists in the media library."""

        normalized = normalize_text(name)
        async with self.session_factory() as session:
            stmt = select(genres.c.id).where(genres.c.name_normalized == normalized)
            existing = (await session.execute(stmt)).scalar_one_or_none()
            return int(existing) if existing is not None else None

    async def lookup_album_id(
        self,
        *,
        title: str,
        artist_id: int | None,
        release_year: int | None = None,
    ) -> int | None:
        """Return the album identifier matching the provided metadata if present."""

        if artist_id is None:
            return None
        normalized = normalize_text(title)
        async with self.session_factory() as session:
            stmt = select(release_groups.c.id).where(
                and_(
                    release_groups.c.primary_artist_id == artist_id,
                    release_groups.c.title_normalized == normalized,
                )
            )
            if release_year is not None:
                stmt = stmt.where(release_groups.c.year == release_year)
            existing = (await session.execute(stmt)).scalar_one_or_none()
            return int(existing) if existing is not None else None

    async def lookup_track_id_by_uid(self, track_uid: str | None) -> int | None:
        """Return a track identifier by its computed UID when available."""

        if not track_uid:
            return None
        async with self.session_factory() as session:
            stmt = select(tracks.c.id).where(tracks.c.track_uid == track_uid)
            existing = (await session.execute(stmt)).scalar_one_or_none()
            return int(existing) if existing is not None else None

    async def lookup_track_details(
        self,
        *,
        title: str,
        artist_id: int | None,
        album_id: int | None,
    ) -> int | None:
        """Return a track identifier that matches the supplied metadata."""

        normalized = normalize_text(title)
        conditions = [tracks.c.title_normalized == normalized]
        if artist_id is not None:
            conditions.append(tracks.c.primary_artist_id == artist_id)
        if album_id is not None:
            conditions.append(tracks.c.album_id == album_id)
        if not conditions:
            return None
        async with self.session_factory() as session:
            stmt = select(tracks.c.id).where(and_(*conditions))
            existing = (await session.execute(stmt)).scalar_one_or_none()
            return int(existing) if existing is not None else None

    async def lookup_track_artist_ids(self, track_id: int) -> list[int]:
        """Return artist identifiers already linked to the provided track."""

        async with self.session_factory() as session:
            stmt = (
                select(track_artists.c.artist_id)
                .where(track_artists.c.track_id == track_id)
                .order_by(track_artists.c.artist_id)
            )
            rows = await session.execute(stmt)
            return [int(row[0]) for row in rows.fetchall() if row[0] is not None]

    async def lookup_track_genre_ids(self, track_id: int) -> list[int]:
        """Return genre identifiers already linked to the provided track."""

        async with self.session_factory() as session:
            stmt = (
                select(track_genres.c.genre_id)
                .where(track_genres.c.track_id == track_id)
                .order_by(track_genres.c.genre_id)
            )
            rows = await session.execute(stmt)
            return [int(row[0]) for row in rows.fetchall() if row[0] is not None]

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
        raw_payload: Mapping[str, Any],
        artist_ids: Iterable[int],
        genre_ids: Iterable[int],
    ) -> tuple[int, bool]:
        """Insert a listen and return its id plus a creation flag."""

        payload_json = json.dumps(raw_payload, sort_keys=True)
        normalized_source_track_id = source_track_id or ""

        async with self.session_factory() as session:
            try:
                result = await session.execute(
                    insert(listens_raw).values(
                        user_id=user_id,
                        source=source,
                        source_track_id=normalized_source_track_id,
                        payload_json=payload_json,
                        listened_at=listened_at,
                    )
                )
            except IntegrityError:
                await session.rollback()
                existing_raw = await session.execute(
                    select(listens_raw.c.id).where(
                        listens_raw.c.user_id == user_id,
                        listens_raw.c.source == source,
                        listens_raw.c.source_track_id == normalized_source_track_id,
                        listens_raw.c.listened_at == listened_at,
                    )
                )
                raw_id = int(existing_raw.scalar_one())
            else:
                await session.commit()
                raw_id = int(result.inserted_primary_key[0])

        async with self.session_factory() as session:
            created = True
            try:
                result = await session.execute(
                    insert(listens).values(
                        raw_id=raw_id,
                        user_id=user_id,
                        track_id=track_id,
                        listened_at=listened_at,
                        source=source,
                        source_track_id=source_track_id,
                        position_secs=position_secs,
                        duration_secs=duration_secs,
                        artist_name_raw=artist_name_raw,
                        track_title_raw=track_title_raw,
                        album_title_raw=album_title_raw,
                        enrich_status="matched",
                        match_confidence=100,
                        last_enriched_at=func.now(),
                    )
                )
                listen_id = int(result.inserted_primary_key[0])
            except IntegrityError:
                await session.rollback()
                existing = await session.execute(
                    select(listens.c.id).where(
                        listens.c.user_id == user_id,
                        listens.c.track_id == track_id,
                        listens.c.listened_at == listened_at,
                    )
                )
                listen_id = int(existing.scalar_one())
                created = False
                await session.execute(
                    update(listens)
                    .where(listens.c.id == listen_id)
                    .values(
                        raw_id=raw_id,
                        artist_name_raw=artist_name_raw,
                        track_title_raw=track_title_raw,
                        album_title_raw=album_title_raw,
                        position_secs=position_secs,
                        duration_secs=duration_secs,
                    )
                )
                await session.commit()
            else:
                await session.commit()

        async with self.session_factory() as session:
            for artist_id in set(artist_ids):
                exists = await session.execute(
                    select(listen_artists.c.listen_id)
                    .where(listen_artists.c.listen_id == listen_id)
                    .where(listen_artists.c.artist_id == artist_id)
                )
                if exists.scalar_one_or_none() is None:
                    await session.execute(
                        insert(listen_artists).values(listen_id=listen_id, artist_id=artist_id)
                    )
            for genre_id in set(genre_ids):
                exists = await session.execute(
                    select(listen_genres.c.listen_id)
                    .where(listen_genres.c.listen_id == listen_id)
                    .where(listen_genres.c.genre_id == genre_id)
                )
                if exists.scalar_one_or_none() is None:
                    await session.execute(
                        insert(listen_genres).values(listen_id=listen_id, genre_id=genre_id)
                    )
            await session.commit()
        return listen_id, created

    def _clean_artist_entries(self, entries: list[tuple[int | None, str]]) -> list[dict[str, Any]]:
        """Normalize artist names and return unique dictionaries preserving order."""

        cleaned: list[dict[str, Any]] = []
        seen: set[str] = set()
        for artist_id, raw_name in entries:
            if not raw_name:
                continue
            trimmed = raw_name.strip()
            if not trimmed:
                continue
            normalized = re.sub(r"^[,\s]+|[,\s]+$", "", trimmed)
            if not normalized:
                continue
            key = normalized.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append({"id": int(artist_id) if artist_id is not None else None, "name": normalized})
        return cleaned

    async def _hydrate_listen_rows(
        self,
        session,
        rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Attach artist arrays and normalized genre strings to listen rows."""

        if not rows:
            return rows

        listen_ids = [int(row["id"]) for row in rows]
        track_ids = {int(row["track_id"]) for row in rows if row.get("track_id") is not None}

        listen_artist_stmt = (
            select(listen_artists.c.listen_id, artists.c.id, artists.c.name)
            .select_from(listen_artists.join(artists, artists.c.id == listen_artists.c.artist_id))
            .where(listen_artists.c.listen_id.in_(listen_ids))
            .order_by(listen_artists.c.listen_id, listen_artists.c.artist_id)
        )
        listen_artist_rows = await session.execute(listen_artist_stmt)
        listen_artist_map: dict[int, list[tuple[int | None, str]]] = defaultdict(list)
        for listen_id, artist_id, name in listen_artist_rows:
            listen_artist_map[int(listen_id)].append((int(artist_id) if artist_id is not None else None, name))

        missing_track_ids = {
            track_id
            for track_id, listen_id in (
                (int(row["track_id"]) if row.get("track_id") is not None else None, int(row["id"]))
                for row in rows
            )
            if track_id is not None and listen_artist_map.get(listen_id) is None
        }

        track_artist_map: dict[int, list[tuple[int | None, str]]] = defaultdict(list)
        if missing_track_ids:
            track_artist_stmt = (
                select(track_artists.c.track_id, artists.c.id, artists.c.name)
                .select_from(track_artists.join(artists, artists.c.id == track_artists.c.artist_id))
                .where(track_artists.c.track_id.in_(missing_track_ids))
                .order_by(track_artists.c.track_id, track_artists.c.artist_id)
            )
            track_artist_rows = await session.execute(track_artist_stmt)
            for track_id, artist_id, name in track_artist_rows:
                track_artist_map[int(track_id)].append((int(artist_id) if artist_id is not None else None, name))

        for row in rows:
            listen_id = int(row["id"])
            track_id = row.get("track_id")
            artist_entries = listen_artist_map.get(listen_id)
            if not artist_entries and track_id is not None:
                artist_entries = track_artist_map.get(int(track_id), [])
            artists_list = self._clean_artist_entries(artist_entries or [])
            if not artists_list:
                raw_artist = row.get("artist_name_raw")
                if raw_artist:
                    cleaned = raw_artist.strip()
                    if cleaned:
                        artists_list = [{"id": None, "name": cleaned}]
            row["artists"] = artists_list
            row["artist_names"] = ", ".join(artist["name"] for artist in artists_list) if artists_list else None

            raw_genres = row.pop("genres", None)
            genre_list: list[str] = []
            if raw_genres:
                seen_genres: set[str] = set()
                for part in raw_genres.split(","):
                    trimmed = part.strip()
                    if not trimmed:
                        continue
                    key = trimmed.casefold()
                    if key in seen_genres:
                        continue
                    seen_genres.add(key)
                    genre_list.append(trimmed)
            row["genres"] = genre_list
            row["genre_names"] = ", ".join(genre_list) if genre_list else None

            if track_id is not None:
                row["track_id"] = int(track_id)
            album_id = row.get("album_id")
            if album_id is not None:
                row["album_id"] = int(album_id)

            for key in ("position_secs", "duration_secs"):
                if row.get(key) is not None:
                    row[key] = int(row[key])

            row.pop("track_title_raw", None)
            row.pop("artist_name_raw", None)

        return rows

    def _period_range(self, period: str, value: str | None) -> tuple[datetime, datetime] | None:
        """Return an inclusive start/exclusive end datetime window for a period filter."""

        if period == "all":
            return None
        if value is None:
            raise ValueError("Missing value for period filter")

        if period == "day":
            try:
                day = datetime.strptime(value, "%Y-%m-%d")
            except ValueError as exc:  # pragma: no cover - validated at API layer
                raise ValueError("Invalid day format") from exc
            start = datetime.combine(day.date(), time.min, tzinfo=timezone.utc)
            return start, start + timedelta(days=1)

        if period == "week":
            try:
                year_str, week_str = value.split("-W")
                year = int(year_str)
                week = int(week_str)
                iso_start = datetime.fromisocalendar(year, week, 1)
            except (ValueError, AttributeError) as exc:  # pragma: no cover - validated at API layer
                raise ValueError("Invalid week format") from exc
            start = iso_start.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
            return start, start + timedelta(days=7)

        if period == "month":
            try:
                month = datetime.strptime(value, "%Y-%m")
            except ValueError as exc:  # pragma: no cover - validated at API layer
                raise ValueError("Invalid month format") from exc
            start = datetime(month.year, month.month, 1, tzinfo=timezone.utc)
            if month.month == 12:
                end = datetime(month.year + 1, 1, 1, tzinfo=timezone.utc)
            else:
                end = datetime(month.year, month.month + 1, 1, tzinfo=timezone.utc)
            return start, end

        raise ValueError("Unsupported period")

    async def fetch_recent_listens(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return the latest listens with enriched metadata."""

        rows, _ = await self.fetch_listens(period="all", value=None, limit=limit, offset=0)
        return rows

    async def fetch_listens(
        self,
        *,
        period: str,
        value: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return listens filtered by a time period along with total count."""

        window = self._period_range(period, value)
        clause = None
        if window is not None:
            start, end = window
            clause = and_(listens.c.listened_at >= start, listens.c.listened_at < end)

        stmt = (
            select(
                listens.c.id,
                listens.c.listened_at,
                listens.c.source,
                listens.c.source_track_id,
                listens.c.position_secs,
                listens.c.duration_secs,
                listens.c.track_id,
                func.coalesce(tracks.c.title, listens.c.track_title_raw).label("track_title"),
                listens.c.track_title_raw,
                listens.c.artist_name_raw,
                release_groups.c.id.label("album_id"),
                release_groups.c.title.label("album_title"),
                release_groups.c.year.label("album_release_year"),
                func.group_concat(genres.c.name, ", ").label("genres"),
            )
            .select_from(listens)
            .outerjoin(tracks, listens.c.track_id == tracks.c.id)
            .outerjoin(release_groups, tracks.c.album_id == release_groups.c.id)
            .outerjoin(track_genres, track_genres.c.track_id == tracks.c.id)
            .outerjoin(genres, genres.c.id == track_genres.c.genre_id)
            .group_by(
                listens.c.id,
                listens.c.listened_at,
                listens.c.source,
                listens.c.source_track_id,
                listens.c.position_secs,
                listens.c.duration_secs,
                listens.c.track_id,
                tracks.c.title,
                listens.c.track_title_raw,
                listens.c.artist_name_raw,
                release_groups.c.id,
                release_groups.c.title,
                release_groups.c.year,
            )
            .order_by(listens.c.listened_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if clause is not None:
            stmt = stmt.where(clause)

        count_stmt = select(func.count()).select_from(listens)
        if clause is not None:
            count_stmt = count_stmt.where(clause)

        async with self.session_factory() as session:
            total_result = await session.execute(count_stmt)
            total = int(total_result.scalar_one())

            result = await session.execute(stmt)
            rows = [dict(row) for row in result.mappings().all()]
            rows = await self._hydrate_listen_rows(session, rows)

            return rows, total

    async def fetch_listen_detail(self, listen_id: int) -> dict[str, Any] | None:
        """Return a single listen with detailed track, album, artist, and genre metadata."""

        stmt = (
            select(
                listens.c.id,
                listens.c.listened_at,
                listens.c.source,
                listens.c.source_track_id,
                listens.c.position_secs,
                listens.c.duration_secs,
                listens.c.user_id,
                users.c.username,
                tracks.c.id.label("track_id"),
                tracks.c.title.label("track_title"),
                tracks.c.duration_secs.label("track_duration_secs"),
                tracks.c.disc_no,
                tracks.c.track_no,
                tracks.c.mbid.label("track_mbid"),
                tracks.c.isrc,
                release_groups.c.id.label("album_id"),
                release_groups.c.title.label("album_title"),
                release_groups.c.year.label("release_year"),
                release_groups.c.mbid.label("album_mbid"),
            )
            .select_from(listens)
            .join(users, listens.c.user_id == users.c.id)
            .join(tracks, listens.c.track_id == tracks.c.id)
            .outerjoin(release_groups, tracks.c.album_id == release_groups.c.id)
            .where(listens.c.id == listen_id)
        )

        async with self.session_factory() as session:
            result = await session.execute(stmt)
            mapping = result.mappings().one_or_none()
            if mapping is None:
                return None

            row = dict(mapping)
            row["id"] = int(row["id"])
            row["track_id"] = int(row["track_id"])
            if row.get("album_id") is not None:
                row["album_id"] = int(row["album_id"])
            if row.get("user_id") is not None:
                row["user_id"] = int(row["user_id"])
            if row.get("position_secs") is not None:
                row["position_secs"] = int(row["position_secs"])
            if row.get("duration_secs") is not None:
                row["duration_secs"] = int(row["duration_secs"])
            if row.get("track_duration_secs") is not None:
                row["track_duration_secs"] = int(row["track_duration_secs"])
            if row.get("disc_no") is not None:
                row["disc_no"] = int(row["disc_no"])
            if row.get("track_no") is not None:
                row["track_no"] = int(row["track_no"])
            if "release_year" in row:
                value = row.pop("release_year")
                if value is not None:
                    row["album_release_year"] = int(value)
                else:
                    row["album_release_year"] = None

            listen_artist_stmt = (
                select(artists.c.id, artists.c.name)
                .select_from(listen_artists.join(artists, artists.c.id == listen_artists.c.artist_id))
                .where(listen_artists.c.listen_id == listen_id)
                .order_by(listen_artists.c.artist_id)
            )
            listen_artists_rows = await session.execute(listen_artist_stmt)
            artist_entries = [
                (int(artist_id) if artist_id is not None else None, name)
                for artist_id, name in listen_artists_rows
            ]

            if not artist_entries:
                track_artist_stmt = (
                    select(artists.c.id, artists.c.name)
                    .select_from(track_artists.join(artists, artists.c.id == track_artists.c.artist_id))
                    .where(track_artists.c.track_id == row["track_id"])
                    .order_by(track_artists.c.artist_id)
                )
                track_artist_rows = await session.execute(track_artist_stmt)
                artist_entries = [
                    (int(artist_id) if artist_id is not None else None, name)
                    for artist_id, name in track_artist_rows
                ]

            row["artists"] = self._clean_artist_entries(artist_entries)

            listen_genre_stmt = (
                select(genres.c.id, genres.c.name)
                .select_from(listen_genres.join(genres, genres.c.id == listen_genres.c.genre_id))
                .where(listen_genres.c.listen_id == listen_id)
                .order_by(genres.c.name)
            )
            listen_genre_rows = await session.execute(listen_genre_stmt)
            genre_entries = [
                (int(genre_id) if genre_id is not None else None, name)
                for genre_id, name in listen_genre_rows
            ]

            if not genre_entries:
                track_genre_stmt = (
                    select(genres.c.id, genres.c.name)
                    .select_from(track_genres.join(genres, genres.c.id == track_genres.c.genre_id))
                    .where(track_genres.c.track_id == row["track_id"])
                    .order_by(genres.c.name)
                )
                track_genre_rows = await session.execute(track_genre_stmt)
                genre_entries = [
                    (int(genre_id) if genre_id is not None else None, name)
                    for genre_id, name in track_genre_rows
                ]

            seen_genres: set[str] = set()
            genres_list: list[dict[str, Any]] = []
            for genre_id, name in genre_entries:
                if not name:
                    continue
                trimmed = name.strip()
                if not trimmed:
                    continue
                key = trimmed.casefold()
                if key in seen_genres:
                    continue
                seen_genres.add(key)
                genres_list.append(
                    {
                        "id": int(genre_id) if genre_id is not None else None,
                        "name": trimmed,
                    }
                )
            row["genres"] = genres_list

            return row

    async def count_listens(self) -> int:
        """Return the total number of stored listen rows."""

        async with self.session_factory() as session:
            result = await session.execute(select(func.count()).select_from(listens))
            return int(result.scalar_one())

    async def delete_all_listens(self) -> None:
        """Remove all stored listens from the database."""

        async with self.session_factory() as session:
            await session.execute(delete(listens))
            await session.commit()

    async def fetch_listens_for_export(
        self,
        *,
        user: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return listens with related metadata for ListenBrainz exports."""

        async with self.session_factory() as session:
            stmt = (
                select(
                    listens.c.id.label("listen_id"),
                    listens.c.listened_at,
                    listens.c.duration_secs.label("listen_duration"),
                    listens.c.source,
                    listens.c.source_track_id,
                    tracks.c.id.label("track_id"),
                    tracks.c.title.label("track_title"),
                    tracks.c.duration_secs.label("track_duration"),
                    tracks.c.track_no,
                    tracks.c.disc_no,
                    tracks.c.mbid,
                    tracks.c.isrc,
                    release_groups.c.title.label("album_title"),
                    users.c.username,
                )
                .select_from(listens)
                .join(users, listens.c.user_id == users.c.id)
                .join(tracks, listens.c.track_id == tracks.c.id)
                .outerjoin(release_groups, tracks.c.album_id == release_groups.c.id)
                .order_by(listens.c.listened_at.asc(), listens.c.id.asc())
                .offset(offset)
                .limit(limit)
            )
            if user:
                stmt = stmt.where(func.lower(users.c.username) == user.lower())
            if since:
                stmt = stmt.where(listens.c.listened_at >= since)

            rows = (await session.execute(stmt)).mappings().all()
            if not rows:
                return []

            listen_ids = [row["listen_id"] for row in rows]
            track_ids = {row["track_id"] for row in rows}

            artist_order = case(
                (
                    track_artists.c.role == "primary",
                    0,
                ),
                (
                    track_artists.c.role == "featured",
                    1,
                ),
                (
                    track_artists.c.role == "remixer",
                    2,
                ),
                else_=3,
            )

            artist_stmt = (
                select(
                    track_artists.c.track_id,
                    artists.c.name,
                    track_artists.c.role,
                )
                .select_from(track_artists)
                .join(artists, artists.c.id == track_artists.c.artist_id)
                .where(track_artists.c.track_id.in_(track_ids))
                .order_by(track_artists.c.track_id, artist_order, artists.c.name)
            )
            artist_rows = await session.execute(artist_stmt)
            artist_map: dict[int, list[tuple[str, str]]] = defaultdict(list)
            for track_id, name, role in artist_rows:
                artist_map[int(track_id)].append((name, role))

            genre_stmt = (
                select(track_genres.c.track_id, genres.c.name)
                .select_from(track_genres)
                .join(genres, genres.c.id == track_genres.c.genre_id)
                .where(track_genres.c.track_id.in_(track_ids))
                .order_by(track_genres.c.track_id, genres.c.name)
            )
            genre_rows = await session.execute(genre_stmt)
            genre_map: dict[int, list[str]] = defaultdict(list)
            for track_id, name in genre_rows:
                genre_map[int(track_id)].append(name)

            result: list[dict[str, Any]] = []
            for row in rows:
                track_id = int(row["track_id"])
                result.append(
                    {
                        "listen_id": int(row["listen_id"]),
                        "username": row["username"],
                        "listened_at": row["listened_at"],
                        "listen_duration": row["listen_duration"],
                        "source": row["source"],
                        "source_track_id": row["source_track_id"],
                        "track": {
                            "id": track_id,
                            "title": row["track_title"],
                            "album": row["album_title"],
                            "duration": row["track_duration"],
                            "track_no": row["track_no"],
                            "disc_no": row["disc_no"],
                            "mbid": row["mbid"],
                            "isrc": row["isrc"],
                        },
                        "artists": [
                            {"name": name, "role": role}
                            for name, role in artist_map.get(track_id, [])
                        ],
                        "genres": genre_map.get(track_id, []),
                    }
                )

            listen_artist_stmt = (
                select(listen_artists.c.listen_id, artists.c.name)
                .select_from(listen_artists)
                .join(artists, artists.c.id == listen_artists.c.artist_id)
                .where(listen_artists.c.listen_id.in_(listen_ids))
                .order_by(listen_artists.c.listen_id, artists.c.name)
            )
            listen_artist_rows = await session.execute(listen_artist_stmt)
            listen_artist_map: dict[int, list[str]] = defaultdict(list)
            for listen_id, name in listen_artist_rows:
                listen_artist_map[int(listen_id)].append(name)

            for item in result:
                listen_id = item["listen_id"]
                if listen_artist_map.get(listen_id):
                    item["listen_artists"] = listen_artist_map[listen_id]
                else:
                    item["listen_artists"] = [artist["name"] for artist in item["artists"]]

            return result

    def _date_format(self, column, pattern: str):
        """Return a SQL expression that formats a datetime using the active dialect."""

        if self._dialect_name.startswith("sqlite"):
            return func.strftime(pattern, column)
        return func.date_format(column, pattern)

    def _period_clause(self, period: str, value: str | None):
        """Return a SQL clause that filters listens by the requested period."""

        if period == "all":
            return true()
        if value is None:
            raise ValueError("Missing value for period filter")
        if period == "day":
            formatted = self._date_format(listens.c.listened_at, "%Y-%m-%d")
            return formatted == value
        if period == "month":
            formatted = self._date_format(listens.c.listened_at, "%Y-%m")
            return formatted == value
        formatted = self._date_format(listens.c.listened_at, "%Y")
        return formatted == value

    async def stats_artists(
        self, period: str, value: str | None, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        """Return artist listen counts constrained by a time period."""

        clause = self._period_clause(period, value)
        base_query = (
            select(
                artists.c.id.label("artist_id"),
                artists.c.name.label("artist"),
                func.count().label("count"),
            )
            .select_from(listens)
            .join(tracks, listens.c.track_id == tracks.c.id)
            .join(track_artists, track_artists.c.track_id == tracks.c.id)
            .join(artists, artists.c.id == track_artists.c.artist_id)
            .where(clause)
            .group_by(artists.c.id, artists.c.name)
        )

        stmt = (
            base_query.order_by(func.count().desc(), artists.c.name).limit(limit).offset(offset)
        )

        count_stmt = select(func.count()).select_from(base_query.subquery())

        async with self.session_factory() as session:
            total = int((await session.execute(count_stmt)).scalar_one())
            rows = await session.execute(stmt)
            return [dict(row._mapping) for row in rows], total

    async def stats_albums(
        self, period: str, value: str | None, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        """Return album listen counts constrained by a time period."""

        clause = self._period_clause(period, value)
        base_query = (
            select(
                release_groups.c.id.label("album_id"),
                release_groups.c.title.label("album"),
                release_groups.c.year.label("release_year"),
                func.count().label("count"),
            )
            .select_from(listens)
            .join(tracks, listens.c.track_id == tracks.c.id)
            .join(release_groups, tracks.c.album_id == release_groups.c.id)
            .where(clause)
            .group_by(release_groups.c.id, release_groups.c.title, release_groups.c.year)
        )

        stmt = (
            base_query.order_by(func.count().desc(), release_groups.c.title).limit(limit).offset(offset)
        )
        count_stmt = select(func.count()).select_from(base_query.subquery())

        async with self.session_factory() as session:
            total = int((await session.execute(count_stmt)).scalar_one())
            rows = await session.execute(stmt)
            return [dict(row._mapping) for row in rows], total

    async def stats_tracks(
        self, period: str, value: str | None, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        """Return track listen counts constrained by a time period."""

        clause = self._period_clause(period, value)
        base_query = (
            select(
                tracks.c.id.label("track_id"),
                tracks.c.title.label("track"),
                func.count().label("count"),
            )
            .select_from(listens)
            .join(tracks, listens.c.track_id == tracks.c.id)
            .where(clause)
            .group_by(tracks.c.id, tracks.c.title)
        )

        stmt = (
            base_query.order_by(func.count().desc(), tracks.c.title).limit(limit).offset(offset)
        )
        count_stmt = select(func.count()).select_from(base_query.subquery())

        async with self.session_factory() as session:
            total = int((await session.execute(count_stmt)).scalar_one())
            rows = await session.execute(stmt)
            return [dict(row._mapping) for row in rows], total

    async def stats_genres(
        self, period: str, value: str | None, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        """Return genre listen counts constrained by a time period."""

        clause = self._period_clause(period, value)
        base_query = (
            select(
                genres.c.id.label("genre_id"),
                genres.c.name.label("genre"),
                func.count().label("count"),
            )
            .select_from(listens)
            .join(tracks, listens.c.track_id == tracks.c.id)
            .join(track_genres, track_genres.c.track_id == tracks.c.id)
            .join(genres, genres.c.id == track_genres.c.genre_id)
            .where(clause)
            .group_by(genres.c.id, genres.c.name)
        )

        stmt = (
            base_query.order_by(func.count().desc(), genres.c.name).limit(limit).offset(offset)
        )
        count_stmt = select(func.count()).select_from(base_query.subquery())

        async with self.session_factory() as session:
            total = int((await session.execute(count_stmt)).scalar_one())
            rows = await session.execute(stmt)
            return [dict(row._mapping) for row in rows], total

    async def stats_top_artist_by_genre(self, year: int) -> list[dict[str, Any]]:
        """Return the top artist per genre for a specific year."""

        stmt = (
            select(
                genres.c.name.label("genre"),
                artists.c.name.label("artist"),
                func.count().label("count"),
            )
            .select_from(listens)
            .join(tracks, listens.c.track_id == tracks.c.id)
            .join(track_genres, track_genres.c.track_id == tracks.c.id)
            .join(genres, genres.c.id == track_genres.c.genre_id)
            .join(track_artists, track_artists.c.track_id == tracks.c.id)
            .join(artists, artists.c.id == track_artists.c.artist_id)
            .where(self._date_format(listens.c.listened_at, "%Y") == str(year))
            .group_by(genres.c.name, artists.c.name)
        )
        async with self.session_factory() as session:
            rows = await session.execute(stmt)
            data: dict[str, dict[str, Any]] = {}
            for genre, artist, count in rows:
                existing = data.get(genre)
                if existing is None or count > existing["count"]:
                    data[genre] = {"genre": genre, "artist": artist, "count": count}
            return list(data.values())

    async def stats_time_of_day(self, year: int, period: str) -> list[dict[str, Any]]:
        """Return track listen counts filtered by the requested daypart."""

        hour = cast(self._date_format(listens.c.listened_at, "%H"), Integer)

        if period == "morning":
            clause = and_(hour >= 5, hour <= 11)
        elif period == "afternoon":
            clause = and_(hour >= 12, hour <= 16)
        elif period == "evening":
            clause = and_(hour >= 17, hour <= 22)
        else:
            clause = or_(hour >= 23, hour <= 4)

        stmt = (
            select(tracks.c.title.label("track"), func.count().label("count"))
            .select_from(listens)
            .join(tracks, listens.c.track_id == tracks.c.id)
            .where(self._date_format(listens.c.listened_at, "%Y") == str(year))
            .where(clause)
            .group_by(tracks.c.title)
            .order_by(func.count().desc())
        )
        async with self.session_factory() as session:
            rows = await session.execute(stmt)
            return [dict(row._mapping) for row in rows]

    async def artist_insights(self, artist_id: int) -> dict[str, Any] | None:
        """Return aggregated information for an artist across listens."""

        async with self.session_factory() as session:
            artist_stmt = (
                select(artists.c.id, artists.c.name, artists.c.mbid)
                .where(artists.c.id == artist_id)
            )
            artist_row = await session.execute(artist_stmt)
            artist = artist_row.mappings().one_or_none()
            if artist is None:
                return None

            base_join = (
                listens.join(tracks, listens.c.track_id == tracks.c.id)
                .join(track_artists, track_artists.c.track_id == tracks.c.id)
            )
            clause = track_artists.c.artist_id == artist_id

            count_stmt = select(func.count()).select_from(base_join).where(clause)
            total = int((await session.execute(count_stmt)).scalar_one())

            span_stmt = (
                select(
                    func.min(listens.c.listened_at).label("first_listen"),
                    func.max(listens.c.listened_at).label("last_listen"),
                )
                .select_from(base_join)
                .where(clause)
            )
            span = (await session.execute(span_stmt)).mappings().one()

            top_genres_stmt = (
                select(
                    genres.c.id.label("genre_id"),
                    genres.c.name.label("genre"),
                    func.count().label("count"),
                )
                .select_from(
                    base_join.join(track_genres, track_genres.c.track_id == tracks.c.id).join(
                        genres, genres.c.id == track_genres.c.genre_id
                    )
                )
                .where(clause)
                .group_by(genres.c.id, genres.c.name)
                .order_by(func.count().desc(), genres.c.name)
                .limit(10)
            )
            top_genres_rows = await session.execute(top_genres_stmt)

            period_expr = self._date_format(listens.c.listened_at, "%Y-%m")

            history_stmt = (
                select(period_expr.label("period"), func.count().label("count"))
                .select_from(base_join)
                .where(clause)
                .group_by(period_expr)
                .order_by(period_expr)
            )

            top_tracks_stmt = (
                select(
                    tracks.c.id.label("track_id"),
                    tracks.c.title.label("track"),
                    release_groups.c.id.label("album_id"),
                    release_groups.c.title.label("album_title"),
                    func.count().label("count"),
                )
                .select_from(
                    base_join.outerjoin(release_groups, release_groups.c.id == tracks.c.album_id)
                )
                .where(clause)
                .group_by(tracks.c.id, tracks.c.title, release_groups.c.id, release_groups.c.title)
                .order_by(func.count().desc(), tracks.c.title)
                .limit(10)
            )
            top_tracks_rows = await session.execute(top_tracks_stmt)

            top_albums_stmt = (
                select(
                    release_groups.c.id.label("album_id"),
                    release_groups.c.title.label("album"),
                    release_groups.c.year.label("release_year"),
                    func.count().label("count"),
                )
                .select_from(
                    base_join.join(release_groups, release_groups.c.id == tracks.c.album_id)
                )
                .where(clause)
                .group_by(release_groups.c.id, release_groups.c.title, release_groups.c.year)
                .order_by(func.count().desc(), release_groups.c.title)
                .limit(10)
            )
            history_rows = (await session.execute(history_stmt)).mappings().all()
            top_albums_rows = await session.execute(top_albums_stmt)

            def _convert_rows(rows, id_key: str):
                payload = []
                for item in rows.mappings():
                    data = dict(item)
                    if data.get(id_key) is not None:
                        data[id_key] = int(data[id_key])
                    if data.get("album_id") is not None:
                        data["album_id"] = int(data["album_id"])
                    if data.get("count") is not None:
                        data["count"] = int(data["count"])
                    payload.append(data)
                return payload

            history_payload = [
                {"period": row["period"], "count": int(row["count"])}
                for row in history_rows
                if row["period"] is not None
            ]

            return {
                "artist_id": int(artist["id"]),
                "name": artist["name"],
                "mbid": artist["mbid"],
                "listen_count": total,
                "first_listen": span["first_listen"],
                "last_listen": span["last_listen"],
                "listen_history": history_payload,
                "top_genres": _convert_rows(top_genres_rows, "genre_id"),
                "top_tracks": _convert_rows(top_tracks_rows, "track_id"),
                "top_albums": _convert_rows(top_albums_rows, "album_id"),
            }

    async def album_insights(self, album_id: int) -> dict[str, Any] | None:
        """Return aggregated information for an album across listens."""

        async with self.session_factory() as session:
            album_stmt = (
                select(
                    release_groups.c.id,
                    release_groups.c.title,
                    release_groups.c.year.label("release_year"),
                    release_groups.c.mbid,
                )
                .where(release_groups.c.id == album_id)
            )
            album_row = await session.execute(album_stmt)
            album = album_row.mappings().one_or_none()
            if album is None:
                return None

            base_clause = tracks.c.album_id == album_id

            count_stmt = (
                select(func.count())
                .select_from(listens.join(tracks, listens.c.track_id == tracks.c.id))
                .where(base_clause)
            )
            total = int((await session.execute(count_stmt)).scalar_one())

            span_stmt = (
                select(
                    func.min(listens.c.listened_at).label("first_listen"),
                    func.max(listens.c.listened_at).label("last_listen"),
                )
                .select_from(listens.join(tracks, listens.c.track_id == tracks.c.id))
                .where(base_clause)
            )
            span = (await session.execute(span_stmt)).mappings().one()

            artist_stmt = (
                select(artists.c.id.label("artist_id"), artists.c.name.label("artist"))
                .select_from(
                    track_artists.join(artists, artists.c.id == track_artists.c.artist_id).join(
                        tracks, track_artists.c.track_id == tracks.c.id
                    )
                )
                .where(base_clause)
                .group_by(artists.c.id, artists.c.name)
                .order_by(artists.c.name)
            )
            artist_rows = (await session.execute(artist_stmt)).mappings().all()

            artist_ids = [int(row["artist_id"]) for row in artist_rows]
            listen_totals: dict[int, int] = {}
            if artist_ids:
                artist_totals_stmt = (
                    select(track_artists.c.artist_id, func.count().label("count"))
                    .select_from(
                        listens
                        .join(tracks, listens.c.track_id == tracks.c.id)
                        .join(track_artists, track_artists.c.track_id == tracks.c.id)
                    )
                    .where(track_artists.c.artist_id.in_(artist_ids))
                    .group_by(track_artists.c.artist_id)
                )
                totals_rows = await session.execute(artist_totals_stmt)
                listen_totals = {
                    int(row.artist_id): int(row.count)
                    for row in totals_rows
                }

            genre_stmt = (
                select(
                    genres.c.id.label("genre_id"),
                    genres.c.name.label("genre"),
                    func.count().label("count"),
                )
                .select_from(
                    track_genres.join(genres, genres.c.id == track_genres.c.genre_id).join(
                        tracks, track_genres.c.track_id == tracks.c.id
                    )
                )
                .where(base_clause)
                .group_by(genres.c.id, genres.c.name)
                .order_by(func.count().desc(), genres.c.name)
            )
            genre_rows = (await session.execute(genre_stmt)).mappings().all()

            tracks_stmt = (
                select(
                    tracks.c.id.label("track_id"),
                    tracks.c.title.label("track"),
                    tracks.c.track_no,
                    tracks.c.disc_no,
                    tracks.c.duration_secs,
                    func.count().label("count"),
                )
                .select_from(listens.join(tracks, listens.c.track_id == tracks.c.id))
                .where(base_clause)
                .group_by(
                    tracks.c.id,
                    tracks.c.title,
                    tracks.c.track_no,
                    tracks.c.disc_no,
                    tracks.c.duration_secs,
                )
                .order_by(tracks.c.disc_no, tracks.c.track_no, tracks.c.title)
            )
            tracks_rows = (await session.execute(tracks_stmt)).mappings().all()

            def _convert_simple(rows: Iterable[Mapping[str, Any]], id_key: str):
                payload = []
                for item in rows:
                    data = dict(item)
                    if data.get(id_key) is not None:
                        data[id_key] = int(data[id_key])
                    if data.get("count") is not None:
                        data["count"] = int(data["count"])
                    if data.get("track_no") is not None:
                        data["track_no"] = int(data["track_no"])
                    if data.get("disc_no") is not None:
                        data["disc_no"] = int(data["disc_no"])
                    if data.get("duration_secs") is not None:
                        data["duration_secs"] = int(data["duration_secs"])
                    payload.append(data)
                return payload

            artist_payload = [
                {
                    "artist_id": int(row["artist_id"]),
                    "artist": row["artist"],
                    "listen_count": listen_totals.get(int(row["artist_id"]), 0),
                }
                for row in artist_rows
            ]

            return {
                "album_id": int(album["id"]),
                "title": album["title"],
                "release_year": album["release_year"],
                "mbid": album["mbid"],
                "listen_count": total,
                "first_listen": span["first_listen"],
                "last_listen": span["last_listen"],
                "artists": artist_payload,
                "genres": _convert_simple(genre_rows, "genre_id"),
                "tracks": _convert_simple(tracks_rows, "track_id"),
            }
