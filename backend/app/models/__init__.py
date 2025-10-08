from __future__ import annotations

from sqlalchemy import (Column, DateTime, Enum, ForeignKey, Integer, MetaData,
                        SmallInteger, String, Table, Text, UniqueConstraint, func)

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(190), nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)

artists = Table(
    "artists",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(255), nullable=False, unique=True),
    Column("mbid", String(36)),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)

genres = Table(
    "genres",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100), nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)

albums = Table(
    "albums",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", String(255), nullable=False),
    Column("release_year", SmallInteger),
    Column("mbid", String(36)),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    UniqueConstraint("title", "release_year", name="uq_albums_title_year"),
)

tracks = Table(
    "tracks",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", String(255), nullable=False),
    Column("album_id", ForeignKey("albums.id", ondelete="SET NULL")),
    Column("duration_secs", Integer),
    Column("disc_no", SmallInteger),
    Column("track_no", SmallInteger),
    Column("mbid", String(36)),
    Column("isrc", String(12)),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    UniqueConstraint("album_id", "title", "disc_no", "track_no", name="uq_tracks_album_title_disc_track"),
)

track_artists = Table(
    "track_artists",
    metadata,
    Column("track_id", ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True),
    Column("artist_id", ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True),
    Column("role", Enum("primary", "featured", "remixer", "composer", name="artist_role"), primary_key=True),
)

track_genres = Table(
    "track_genres",
    metadata,
    Column("track_id", ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
)

listens = Table(
    "listens",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("track_id", ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False),
    Column("listened_at", DateTime(timezone=True), nullable=False),
    Column("source", String(64), nullable=False),
    Column("source_track_id", String(128)),
    Column("position_secs", Integer),
    Column("duration_secs", Integer),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    UniqueConstraint("user_id", "track_id", "listened_at", name="uq_listen_dedupe"),
)

listen_artists = Table(
    "listen_artists",
    metadata,
    Column("listen_id", ForeignKey("listens.id", ondelete="CASCADE"), primary_key=True),
    Column("artist_id", ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True),
)

listen_genres = Table(
    "listen_genres",
    metadata,
    Column("listen_id", ForeignKey("listens.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
)

config = Table(
    "config",
    metadata,
    Column("key", String(64), primary_key=True),
    Column("value", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)

__all__ = [
    "metadata",
    "users",
    "artists",
    "genres",
    "albums",
    "tracks",
    "track_artists",
    "track_genres",
    "listens",
    "listen_artists",
    "listen_genres",
    "config",
]
