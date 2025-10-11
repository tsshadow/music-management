from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)

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
    Column("name", String(255), nullable=False),
    Column("name_normalized", String(255), nullable=False, unique=True),
    Column("sort_name", String(255), nullable=False),
    Column("mbid", String(36)),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)

artist_aliases = Table(
    "artist_aliases",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("artist_id", ForeignKey("artists.id", ondelete="CASCADE"), nullable=False),
    Column("alias_normalized", String(255), nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)

genres = Table(
    "genres",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100), nullable=False),
    Column("name_normalized", String(100), nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)

albums = Table(
    "albums",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("artist_id", ForeignKey("artists.id", ondelete="CASCADE"), nullable=False),
    Column("title", String(255), nullable=False),
    Column("title_normalized", String(255), nullable=False),
    Column("year", SmallInteger),
    Column("mbid", String(36)),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    UniqueConstraint("artist_id", "title_normalized", name="uq_albums_artist_title"),
)

tracks = Table(
    "tracks",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", String(255), nullable=False),
    Column("title_normalized", String(255), nullable=False),
    Column("album_id", ForeignKey("albums.id", ondelete="SET NULL")),
    Column("primary_artist_id", ForeignKey("artists.id", ondelete="SET NULL")),
    Column("duration_secs", Integer),
    Column("disc_no", SmallInteger),
    Column("track_no", SmallInteger),
    Column("mbid", String(36)),
    Column("isrc", String(12)),
    Column("acoustid", String(40)),
    Column("track_uid", String(40), unique=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    UniqueConstraint(
        "album_id",
        "title_normalized",
        "disc_no",
        "track_no",
        name="uq_tracks_album_title_disc_track",
    ),
)

track_artists = Table(
    "track_artists",
    metadata,
    Column("track_id", ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True),
    Column("artist_id", ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "role",
        Enum(
            "primary",
            "featured",
            "featuring",
            "remixer",
            "producer",
            "composer",
            name="artist_role",
        ),
        primary_key=True,
    ),
)

track_genres = Table(
    "track_genres",
    metadata,
    Column("track_id", ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
    Column("weight", SmallInteger, nullable=False, server_default="100"),
)

labels = Table(
    "labels",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(255), nullable=False),
    Column("name_normalized", String(255), nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)

track_labels = Table(
    "track_labels",
    metadata,
    Column("track_id", ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True),
    Column("label_id", ForeignKey("labels.id", ondelete="CASCADE"), primary_key=True),
)

title_aliases = Table(
    "title_aliases",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("track_id", ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False),
    Column("alias_normalized", String(255), nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)

media_files = Table(
    "media_files",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("file_path", Text, nullable=False),
    Column("file_path_hash", String(64), nullable=False, unique=True),
    Column("file_size", Integer),
    Column("file_mtime", DateTime(timezone=True)),
    Column("audio_hash", String(64)),
    Column("duration_secs", Integer),
    Column("parsed_metadata_json", Text),
    Column("last_scan_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)

tag_sources = Table(
    "tag_sources",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100), nullable=False, unique=True),
    Column("priority", SmallInteger, nullable=False, server_default="0"),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)

track_tag_attributes = Table(
    "track_tag_attributes",
    metadata,
    Column("track_id", ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True),
    Column("key", String(64), primary_key=True),
    Column("value", String(255), nullable=False),
    Column("source_id", ForeignKey("tag_sources.id", ondelete="CASCADE"), nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)


listen_enrich_status = Enum(
    "pending",
    "matched",
    "ambiguous",
    "unmatched",
    name="listen_enrich_status",
)

listens = Table(
    "listens",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("track_id", ForeignKey("tracks.id", ondelete="SET NULL")),
    Column("listened_at", DateTime(timezone=True), nullable=False),
    Column("source", String(64), nullable=False),
    Column("source_track_id", String(128)),
    Column("position_secs", Integer),
    Column("duration_secs", Integer),
    Column("artist_name_raw", String(255)),
    Column("track_title_raw", String(255)),
    Column("album_title_raw", String(255)),
    Column("enrich_status", listen_enrich_status, nullable=False, server_default="pending"),
    Column("match_confidence", SmallInteger),
    Column("last_enriched_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    UniqueConstraint("user_id", "track_id", "listened_at", name="uq_listen_dedupe"),
)

listen_match_candidates = Table(
    "listen_match_candidates",
    metadata,
    Column("listen_id", ForeignKey("listens.id", ondelete="CASCADE"), primary_key=True),
    Column("track_id", ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True),
    Column("confidence", SmallInteger, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)

Index("ix_artists_name_normalized", artists.c.name_normalized, unique=True)
Index("ix_albums_artist_title", albums.c.artist_id, albums.c.title_normalized, unique=True)
Index("ix_tracks_track_uid", tracks.c.track_uid, unique=True)
Index("ix_tracks_primary_artist", tracks.c.primary_artist_id)
Index("ix_listens_enrich_status", listens.c.enrich_status)
Index("ix_listens_listened_at", listens.c.listened_at)
Index("ix_media_files_path_hash", media_files.c.file_path_hash, unique=True)

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
    "artist_aliases",
    "genres",
    "albums",
    "tracks",
    "title_aliases",
    "track_artists",
    "track_genres",
    "labels",
    "track_labels",
    "listens",
    "listen_match_candidates",
    "listen_artists",
    "listen_genres",
    "media_files",
    "tag_sources",
    "track_tag_attributes",
    "config",
]
