from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping

from sqlalchemy import Integer, and_, func, insert, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

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

        stmt = select(artists.c.id).where(func.lower(artists.c.name) == name.lower())
        return await self._get_or_create(
            stmt,
            {"name": name, "mbid": mbid},
            artists,
        )

    async def upsert_genre(self, name: str) -> int:
        """Return the genre id for the name, inserting when missing."""

        stmt = select(genres.c.id).where(func.lower(genres.c.name) == name.lower())
        return await self._get_or_create(stmt, {"name": name}, genres)

    async def upsert_album(
        self, title: str, release_year: int | None = None, mbid: str | None = None
    ) -> int:
        """Return the album id for the title and year, creating a row if absent."""

        stmt = select(albums.c.id).where(
            and_(func.lower(albums.c.title) == title.lower(), albums.c.release_year == release_year)
        )
        return await self._get_or_create(
            stmt,
            {"title": title, "release_year": release_year, "mbid": mbid},
            albums,
        )

    async def upsert_track(
        self,
        *,
        title: str,
        album_id: int | None,
        duration_secs: int | None,
        disc_no: int | None,
        track_no: int | None,
        mbid: str | None,
        isrc: str | None,
    ) -> int:
        """Return the track id for the provided fingerprint, inserting if needed."""

        async with self.session_factory() as session:
            stmt = select(tracks.c.id).where(
                and_(
                    func.lower(tracks.c.title) == title.lower(),
                    (tracks.c.album_id == album_id) if album_id is not None else tracks.c.album_id.is_(None),
                    (tracks.c.disc_no == disc_no) if disc_no is not None else tracks.c.disc_no.is_(None),
                    (tracks.c.track_no == track_no) if track_no is not None else tracks.c.track_no.is_(None),
                )
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing is not None:
                return int(existing)
            res = await session.execute(
                insert(tracks).values(
                    title=title,
                    album_id=album_id,
                    duration_secs=duration_secs,
                    disc_no=disc_no,
                    track_no=track_no,
                    mbid=mbid,
                    isrc=isrc,
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

    def _period_clause(self, period: str, value: str):
        """Return a SQL clause that filters listens by the requested period."""

        if period == "day":
            return func.strftime("%Y-%m-%d", listens.c.listened_at) == value
        if period == "month":
            return func.strftime("%Y-%m", listens.c.listened_at) == value
        return func.strftime("%Y", listens.c.listened_at) == value

    async def stats_artists(self, period: str, value: str) -> list[dict[str, Any]]:
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

    async def stats_genres(self, period: str, value: str) -> list[dict[str, Any]]:
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
            .where(func.strftime("%Y", listens.c.listened_at) == str(year))
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

        hour = func.cast(func.strftime("%H", listens.c.listened_at), Integer)

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
            .where(func.strftime("%Y", listens.c.listened_at) == str(year))
            .where(clause)
            .group_by(tracks.c.title)
            .order_by(func.count().desc())
        )
        async with self.session_factory() as session:
            rows = await session.execute(stmt)
            return [dict(row._mapping) for row in rows]
