from __future__ import annotations

import os

from sqlalchemy import (
    Column,
    Date,
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


def _schema_from_env(env_var: str, default: str | None = None) -> str | None:
    """Return an optional schema name derived from environment configuration."""

    value = os.getenv(env_var)
    if value is None:
        return default
    value = value.strip()
    return value or None


def _schema_kwargs(schema: str | None) -> dict[str, str]:
    return {"schema": schema} if schema else {}


def _fk(schema: str | None, table: str, column: str) -> str:
    return f"{schema}.{table}.{column}" if schema else f"{table}.{column}"


MEDIALIBRARY_SCHEMA = _schema_from_env("SCROBBLER_MEDIALIBRARY_SCHEMA")
LISTENS_SCHEMA = _schema_from_env("SCROBBLER_LISTENS_SCHEMA")

metadata = MetaData()


users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(190), nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    **_schema_kwargs(LISTENS_SCHEMA),
)


listen_enrich_status = Enum(
    "pending",
    "matched",
    "ambiguous",
    "unmatched",
    name="listen_enrich_status",
)


release_group_type = Enum(
    "album",
    "single",
    "ep",
    "compilation",
    "live",
    "mixtape",
    "dj_mix",
    "remix",
    "other",
    name="release_group_type",
)


artist_role = Enum(
    "primary",
    "featured",
    "featuring",
    "remixer",
    "producer",
    "composer",
    name="artist_role",
)


external_entity = Enum(
    "artist",
    "track",
    "release",
    "release_group",
    "publisher",
    "event",
    "playlist",
    "genre",
    name="external_entity",
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
    **_schema_kwargs(MEDIALIBRARY_SCHEMA),
)


artist_aliases = Table(
    "artist_aliases",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "artist_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "artists", "id"), ondelete="CASCADE"),
        nullable=False,
    ),
    Column("alias", String(255), nullable=False),
    Column("alias_normalized", String(255), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    UniqueConstraint("artist_id", "alias_normalized", name="uq_artist_aliases"),
    **_schema_kwargs(MEDIALIBRARY_SCHEMA),
)


genres = Table(
    "genres",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100), nullable=False),
    Column("name_normalized", String(100), nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    **_schema_kwargs(MEDIALIBRARY_SCHEMA),
)


tracks = Table(
    "tracks",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", String(255), nullable=False),
    Column("title_normalized", String(255), nullable=False),
    Column(
        "album_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "release_groups", "id"), ondelete="SET NULL"),
    ),
    Column(
        "primary_artist_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "artists", "id"), ondelete="SET NULL"),
    ),
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
        name="uq_tracks_album_disc_track",
    ),
    **_schema_kwargs(MEDIALIBRARY_SCHEMA),
)


track_artists = Table(
    "track_artists",
    metadata,
    Column(
        "track_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "tracks", "id"), ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "artist_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "artists", "id"), ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("role", artist_role, nullable=False, primary_key=True),
    Column("position", SmallInteger, nullable=False, server_default="0", primary_key=True),
    **_schema_kwargs(MEDIALIBRARY_SCHEMA),
)


track_genres = Table(
    "track_genres",
    metadata,
    Column(
        "track_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "tracks", "id"), ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "genre_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "genres", "id"), ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("weight", SmallInteger, nullable=False, server_default="100"),
    **_schema_kwargs(MEDIALIBRARY_SCHEMA),
)


tag_sources = Table(
    "tag_sources",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100), nullable=False, unique=True),
    Column("priority", SmallInteger, nullable=False, server_default="0"),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    **_schema_kwargs(MEDIALIBRARY_SCHEMA),
)


track_tag_attributes = Table(
    "track_tag_attributes",
    metadata,
    Column(
        "track_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "tracks", "id"), ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("key", String(64), primary_key=True),
    Column("value", String(255), nullable=False),
    Column(
        "source_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "tag_sources", "id"), ondelete="CASCADE"),
        nullable=False,
    ),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    **_schema_kwargs(MEDIALIBRARY_SCHEMA),
)


title_aliases = Table(
    "title_aliases",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "track_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "tracks", "id"), ondelete="CASCADE"),
        nullable=False,
    ),
    Column("alias", String(255), nullable=False),
    Column("alias_normalized", String(255), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    UniqueConstraint("track_id", "alias_normalized", name="uq_title_aliases"),
    **_schema_kwargs(MEDIALIBRARY_SCHEMA),
)


release_groups = Table(
    "release_groups",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", String(255), nullable=False),
    Column("title_normalized", String(255), nullable=False),
    Column("primary_artist_id", ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "artists", "id"), ondelete="SET NULL")),
    Column("type", release_group_type, nullable=False, server_default="album"),
    Column("mbid", String(36)),
    Column("year", SmallInteger),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    UniqueConstraint("primary_artist_id", "title_normalized", name="uq_release_groups_artist_title"),
    **_schema_kwargs(MEDIALIBRARY_SCHEMA),
)

releases = Table(
    "releases",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("release_group_id", ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "release_groups", "id"), ondelete="SET NULL")),
    Column("title", String(255), nullable=False),
    Column("title_normalized", String(255), nullable=False),
    Column("release_date", Date),
    Column("country", String(3)),
    Column("format", String(64)),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    UniqueConstraint("release_group_id", "title_normalized", "release_date", name="uq_releases_group_title_date"),
    **_schema_kwargs(MEDIALIBRARY_SCHEMA),
)


release_items = Table(
    "release_items",
    metadata,
    Column(
        "release_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "releases", "id"), ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "track_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "tracks", "id"), ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("disc_no", SmallInteger, nullable=False, server_default="1", primary_key=True),
    Column("track_no", SmallInteger, nullable=False, server_default="1", primary_key=True),
    **_schema_kwargs(MEDIALIBRARY_SCHEMA),
)


labels = Table(
    "labels",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(255), nullable=False),
    Column("name_normalized", String(255), nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    **_schema_kwargs(MEDIALIBRARY_SCHEMA),
)


release_labels = Table(
    "release_labels",
    metadata,
    Column(
        "release_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "releases", "id"), ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "label_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "labels", "id"), ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("cat_id", String(64)),
    Column("role", String(64)),
    Column("territory", String(64)),
    **_schema_kwargs(MEDIALIBRARY_SCHEMA),
)


track_labels = Table(
    "track_labels",
    metadata,
    Column(
        "track_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "tracks", "id"), ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "label_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "labels", "id"), ondelete="CASCADE"),
        primary_key=True,
    ),
    **_schema_kwargs(MEDIALIBRARY_SCHEMA),
)


publishers = Table(
    "publishers",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(255), nullable=False),
    Column("platform", String(64), nullable=False),
    Column("handle", String(255)),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    UniqueConstraint("platform", "handle", name="uq_publishers_platform_handle"),
    **_schema_kwargs(MEDIALIBRARY_SCHEMA),
)


release_publishers = Table(
    "release_publishers",
    metadata,
    Column(
        "release_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "releases", "id"), ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "publisher_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "publishers", "id"), ondelete="CASCADE"),
        primary_key=True,
    ),
    **_schema_kwargs(MEDIALIBRARY_SCHEMA),
)


playlists = Table(
    "playlists",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("platform", String(64), nullable=False),
    Column(
        "owner_publisher_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "publishers", "id"), ondelete="SET NULL"),
    ),
    Column("title", String(255), nullable=False),
    Column("description", Text),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    **_schema_kwargs(MEDIALIBRARY_SCHEMA),
)


playlist_items = Table(
    "playlist_items",
    metadata,
    Column(
        "playlist_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "playlists", "id"), ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("position", Integer, nullable=False, primary_key=True),
    Column(
        "track_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "tracks", "id"), ondelete="SET NULL"),
    ),
    Column(
        "release_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "releases", "id"), ondelete="SET NULL"),
    ),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    **_schema_kwargs(MEDIALIBRARY_SCHEMA),
)


events = Table(
    "events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(255), nullable=False),
    Column("start_date", Date),
    Column("end_date", Date),
    Column("location", String(255)),
    Column("description", Text),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    **_schema_kwargs(MEDIALIBRARY_SCHEMA),
)


event_recordings = Table(
    "event_recordings",
    metadata,
    Column(
        "event_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "events", "id"), ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "track_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "tracks", "id"), ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("stage", String(255)),
    Column("set_time", DateTime(timezone=True)),
    **_schema_kwargs(MEDIALIBRARY_SCHEMA),
)


external_ids = Table(
    "external_ids",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("entity_type", external_entity, nullable=False),
    Column("entity_id", Integer, nullable=False),
    Column("scheme", String(64), nullable=False),
    Column("value", String(255), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    UniqueConstraint("entity_type", "entity_id", "scheme", "value", name="uq_external_ids_entity"),
    **_schema_kwargs(MEDIALIBRARY_SCHEMA),
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
    Column(
        "track_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "tracks", "id"), ondelete="SET NULL"),
    ),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    **_schema_kwargs(MEDIALIBRARY_SCHEMA),
)


listens_raw = Table(
    "listens_raw",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "user_id",
        ForeignKey(_fk(LISTENS_SCHEMA, "users", "id"), ondelete="CASCADE"),
        nullable=False,
    ),
    Column("source", String(64), nullable=False),
    Column("source_track_id", String(128), nullable=False, server_default=""),
    Column("payload_json", Text, nullable=False),
    Column("listened_at", DateTime(timezone=True), nullable=False),
    Column("ingested_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    UniqueConstraint(
        "user_id",
        "listened_at",
        "source",
        "source_track_id",
        name="uq_listens_raw_dedupe",
    ),
    **_schema_kwargs(LISTENS_SCHEMA),
)


listens = Table(
    "listens",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "raw_id",
        ForeignKey(_fk(LISTENS_SCHEMA, "listens_raw", "id"), ondelete="SET NULL"),
    ),
    Column(
        "user_id",
        ForeignKey(_fk(LISTENS_SCHEMA, "users", "id"), ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "track_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "tracks", "id"), ondelete="SET NULL"),
    ),
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
    Column("match_reason", String(255)),
    Column("last_enriched_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    UniqueConstraint("user_id", "track_id", "listened_at", name="uq_listen_dedupe"),
    **_schema_kwargs(LISTENS_SCHEMA),
)


listen_match_candidates = Table(
    "listen_match_candidates",
    metadata,
    Column(
        "listen_id",
        ForeignKey(_fk(LISTENS_SCHEMA, "listens", "id"), ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "track_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "tracks", "id"), ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("confidence", SmallInteger, nullable=False),
    Column("features_json", Text),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    **_schema_kwargs(LISTENS_SCHEMA),
)


listen_artists = Table(
    "listen_artists",
    metadata,
    Column(
        "listen_id",
        ForeignKey(_fk(LISTENS_SCHEMA, "listens", "id"), ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "artist_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "artists", "id"), ondelete="CASCADE"),
        primary_key=True,
    ),
    **_schema_kwargs(LISTENS_SCHEMA),
)


listen_genres = Table(
    "listen_genres",
    metadata,
    Column(
        "listen_id",
        ForeignKey(_fk(LISTENS_SCHEMA, "listens", "id"), ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "genre_id",
        ForeignKey(_fk(MEDIALIBRARY_SCHEMA, "genres", "id"), ondelete="CASCADE"),
        primary_key=True,
    ),
    **_schema_kwargs(LISTENS_SCHEMA),
)


config = Table(
    "config",
    metadata,
    Column("key", String(64), primary_key=True),
    Column("value", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    **_schema_kwargs(LISTENS_SCHEMA),
)


Index("ix_artists_name_normalized", artists.c.name_normalized, unique=True)
Index("ix_tracks_track_uid", tracks.c.track_uid, unique=True)
Index("ix_tracks_primary_artist", tracks.c.primary_artist_id)
Index("ix_release_groups_title", release_groups.c.primary_artist_id, release_groups.c.title_normalized, unique=True)
Index("ix_listens_enrich_status", listens.c.enrich_status)
Index("ix_listens_listened_at", listens.c.listened_at)
Index("ix_media_files_path_hash", media_files.c.file_path_hash, unique=True)
Index("ix_listens_raw_source", listens_raw.c.user_id, listens_raw.c.source)


__all__ = [
    "metadata",
    "MEDIALIBRARY_SCHEMA",
    "LISTENS_SCHEMA",
    "users",
    "artists",
    "artist_aliases",
    "genres",
    "tracks",
    "title_aliases",
    "track_artists",
    "track_genres",
    "track_labels",
    "release_groups",
    "releases",
    "release_items",
    "labels",
    "release_labels",
    "publishers",
    "release_publishers",
    "playlists",
    "playlist_items",
    "events",
    "event_recordings",
    "external_ids",
    "listens_raw",
    "listens",
    "listen_match_candidates",
    "listen_artists",
    "listen_genres",
    "media_files",
    "tag_sources",
    "track_tag_attributes",
    "config",
]
