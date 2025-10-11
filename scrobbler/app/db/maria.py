from __future__ import annotations

from collections import defaultdict
from datetime import datetime
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
from analyzer.matching.uid import make_track_uid

from .adapter import DatabaseAdapter
from ..models import (
    albums,
    artists,
    config,
    genres,
    listen_artists,
    listen_genres,
    listens,
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

    async def upsert_artist(self, name: str, mbid: str | None = None) -> int:
        """Return the artist id for the name, inserting when not present."""

        normalized = normalize_text(name)
        async with self.session_factory() as session:
            stmt = select(artists.c.id).where(artists.c.name_normalized == normalized)
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing is not None:
                await session.execute(
                    update(artists)
                    .where(artists.c.id == existing)
                    .values(
                        name=name,
                        sort_name=normalized,
                        mbid=mbid,
                        updated_at=func.now(),
                    )
                )
                await session.commit()
                return int(existing)
            res = await session.execute(
                insert(artists).values(
                    name=name,
                    name_normalized=normalized,
                    sort_name=normalized,
                    mbid=mbid,
                )
            )
            await session.commit()
            return int(res.inserted_primary_key[0])

    async def upsert_genre(self, name: str) -> int:
        """Return the genre id for the name, inserting when missing."""

        normalized = normalize_text(name)
        async with self.session_factory() as session:
            stmt = select(genres.c.id).where(genres.c.name_normalized == normalized)
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing is not None:
                await session.execute(
                    update(genres)
                    .where(genres.c.id == existing)
                    .values(name=name, updated_at=func.now())
                )
                await session.commit()
                return int(existing)
            res = await session.execute(
                insert(genres).values(name=name, name_normalized=normalized)
            )
            await session.commit()
            return int(res.inserted_primary_key[0])

    async def upsert_album(
        self,
        title: str,
        *,
        artist_id: int,
        release_year: int | None = None,
        mbid: str | None = None,
    ) -> int:
        """Return the album id for the title and year, creating a row if absent."""

        normalized = normalize_text(title)
        async with self.session_factory() as session:
            stmt = select(albums.c.id).where(
                and_(
                    albums.c.artist_id == artist_id,
                    albums.c.title_normalized == normalized,
                )
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing is not None:
                await session.execute(
                    update(albums)
                    .where(albums.c.id == existing)
                    .values(
                        title=title,
                        year=release_year,
                        mbid=mbid,
                        updated_at=func.now(),
                    )
                )
                await session.commit()
                return int(existing)
            res = await session.execute(
                insert(albums).values(
                    artist_id=artist_id,
                    title=title,
                    title_normalized=normalized,
                    year=release_year,
                    mbid=mbid,
                )
            )
            await session.commit()
            return int(res.inserted_primary_key[0])

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
    ) -> int:
        """Return the track id for the provided fingerprint, inserting if needed."""

        async with self.session_factory() as session:
            normalized = normalize_text(title)
            computed_uid = track_uid
            if computed_uid is None:
                artist_name = None
                if primary_artist_id:
                    artist_row = await session.execute(
                        select(artists.c.name).where(artists.c.id == primary_artist_id)
                    )
                    artist_name = artist_row.scalar_one_or_none()
                album_title = None
                if album_id:
                    album_row = await session.execute(
                        select(albums.c.title).where(albums.c.id == album_id)
                    )
                    album_title = album_row.scalar_one_or_none()
                computed_uid = make_track_uid(artist_name, title, album_title, duration_secs)
            stmt = select(tracks.c.id).where(tracks.c.track_uid == computed_uid)
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing is not None:
                await session.execute(
                    update(tracks)
                    .where(tracks.c.id == existing)
                    .values(
                        title=title,
                        title_normalized=normalized,
                        album_id=album_id,
                        primary_artist_id=primary_artist_id,
                        duration_secs=duration_secs,
                        disc_no=disc_no,
                        track_no=track_no,
                        mbid=mbid,
                        isrc=isrc,
                        acoustid=acoustid,
                        track_uid=computed_uid,
                        updated_at=func.now(),
                    )
                )
                await session.commit()
                return int(existing)
            res = await session.execute(
                insert(tracks).values(
                    title=title,
                    title_normalized=normalized,
                    album_id=album_id,
                    primary_artist_id=primary_artist_id,
                    duration_secs=duration_secs,
                    disc_no=disc_no,
                    track_no=track_no,
                    mbid=mbid,
                    isrc=isrc,
                    acoustid=acoustid,
                    track_uid=computed_uid,
                )
            )
            await session.commit()
            return int(res.inserted_primary_key[0])

    async def link_track_artists(self, track_id: int, artists_pairs: list[tuple[int, str]]) -> None:
        """Ensure each artist-role pairing is linked to the track."""

        async with self.session_factory() as session:
            for artist_id, role in artists_pairs:
                exists = await session.execute(
                    select(track_artists.c.track_id)
                    .where(track_artists.c.track_id == track_id)
                    .where(track_artists.c.artist_id == artist_id)
                    .where(track_artists.c.role == role)
                )
                if exists.scalar_one_or_none() is None:
                    await session.execute(
                        insert(track_artists).values(track_id=track_id, artist_id=artist_id, role=role)
                    )
            await session.commit()

    async def link_track_genres(self, track_id: int, genre_ids: Iterable[int]) -> None:
        """Ensure each genre is linked to the track."""

        async with self.session_factory() as session:
            for genre_id in genre_ids:
                exists = await session.execute(
                    select(track_genres.c.track_id)
                    .where(track_genres.c.track_id == track_id)
                    .where(track_genres.c.genre_id == genre_id)
                )
                if exists.scalar_one_or_none() is None:
                    await session.execute(
                        insert(track_genres).values(track_id=track_id, genre_id=genre_id)
                    )
            await session.commit()

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
    ) -> tuple[int, bool]:
        """Insert a listen and return its id plus a creation flag."""

        async with self.session_factory() as session:
            created = True
            try:
                result = await session.execute(
                    insert(listens).values(
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

    async def fetch_recent_listens(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return the latest listens with joined artist and genre names."""

        stmt = (
            select(
                listens.c.id,
                listens.c.listened_at,
                listens.c.source,
                listens.c.position_secs,
                listens.c.duration_secs,
                tracks.c.title.label("track_title"),
                albums.c.title.label("album_title"),
                func.group_concat(artists.c.name, ", ").label("artists"),
                func.group_concat(genres.c.name, ", ").label("genres"),
            )
            .select_from(listens)
            .join(tracks, listens.c.track_id == tracks.c.id)
            .outerjoin(albums, tracks.c.album_id == albums.c.id)
            .outerjoin(track_artists, track_artists.c.track_id == tracks.c.id)
            .outerjoin(artists, artists.c.id == track_artists.c.artist_id)
            .outerjoin(track_genres, track_genres.c.track_id == tracks.c.id)
            .outerjoin(genres, genres.c.id == track_genres.c.genre_id)
            .group_by(listens.c.id)
            .order_by(listens.c.listened_at.desc())
            .limit(limit)
        )
        async with self.session_factory() as session:
            result = await session.execute(stmt)
            return [dict(row) for row in result.mappings().all()]

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
                    albums.c.title.label("album_title"),
                    users.c.username,
                )
                .select_from(listens)
                .join(users, listens.c.user_id == users.c.id)
                .join(tracks, listens.c.track_id == tracks.c.id)
                .outerjoin(albums, tracks.c.album_id == albums.c.id)
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

    async def stats_artists(self, period: str, value: str | None) -> list[dict[str, Any]]:
        """Return artist listen counts constrained by a time period."""

        clause = self._period_clause(period, value)
        stmt = (
            select(artists.c.name.label("artist"), func.count().label("count"))
            .select_from(listens)
            .join(tracks, listens.c.track_id == tracks.c.id)
            .join(track_artists, track_artists.c.track_id == tracks.c.id)
            .join(artists, artists.c.id == track_artists.c.artist_id)
            .where(clause)
            .group_by(artists.c.name)
            .order_by(func.count().desc())
        )
        async with self.session_factory() as session:
            rows = await session.execute(stmt)
            return [dict(row._mapping) for row in rows]

    async def stats_albums(self, period: str, value: str | None) -> list[dict[str, Any]]:
        """Return album listen counts constrained by a time period."""

        clause = self._period_clause(period, value)
        stmt = (
            select(albums.c.title.label("album"), func.count().label("count"))
            .select_from(listens)
            .join(tracks, listens.c.track_id == tracks.c.id)
            .join(albums, tracks.c.album_id == albums.c.id)
            .where(clause)
            .group_by(albums.c.title)
            .order_by(func.count().desc())
        )
        async with self.session_factory() as session:
            rows = await session.execute(stmt)
            return [dict(row._mapping) for row in rows]

    async def stats_tracks(self, period: str, value: str | None) -> list[dict[str, Any]]:
        """Return track listen counts constrained by a time period."""

        clause = self._period_clause(period, value)
        stmt = (
            select(tracks.c.title.label("track"), func.count().label("count"))
            .select_from(listens)
            .join(tracks, listens.c.track_id == tracks.c.id)
            .where(clause)
            .group_by(tracks.c.title)
            .order_by(func.count().desc())
        )
        async with self.session_factory() as session:
            rows = await session.execute(stmt)
            return [dict(row._mapping) for row in rows]

    async def stats_genres(self, period: str, value: str | None) -> list[dict[str, Any]]:
        """Return genre listen counts constrained by a time period."""

        clause = self._period_clause(period, value)
        stmt = (
            select(genres.c.name.label("genre"), func.count().label("count"))
            .select_from(listens)
            .join(tracks, listens.c.track_id == tracks.c.id)
            .join(track_genres, track_genres.c.track_id == tracks.c.id)
            .join(genres, genres.c.id == track_genres.c.genre_id)
            .where(clause)
            .group_by(genres.c.name)
            .order_by(func.count().desc())
        )
        async with self.session_factory() as session:
            rows = await session.execute(stmt)
            return [dict(row._mapping) for row in rows]

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
