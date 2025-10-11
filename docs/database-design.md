# Database Design

This document describes the relational data model shared by the `scrobbler` and `analyzer` modules. Use it as a quick reference to find where data lives and how tables relate to one another.

## High-level overview

- **User activity** is stored in `listens`, with optional relationships to `tracks`, `artists`, and `genres` to enrich listening history.
- **Media library** metadata flows in through the analyzer. It enriches artists, albums, tracks, and media files while populating association tables (`track_artists`, `track_genres`, `track_labels`, `track_tag_attributes`).
- **Analyzer ↔ Scrobbler** operate on dedicated schemas (`medialibrary` and `listens`) that keep write ownership isolated while preserving cross-schema foreign keys.

### Relationship model (text representation)

```
users ──< listens >── tracks ──< track_artists >── artists
                      │                       └── artist_aliases
                      │
                      ├──< track_genres >── genres ──< listen_genres >── listens
                      ├──< track_labels >── labels
                      ├──< track_tag_attributes >── tag_sources
                      ├──< title_aliases
                      └── media_files (1:N)

tracks ──< listen_match_candidates >── listens
tracks ──< listen_artists >── artists
albums ──< tracks
artists ──< albums
```

## Tables by domain

### Users

| Table | Purpose | Key columns | Notes |
|-------|---------|-------------|-------|
| `users` | Application user management. | `username` (unique), `created_at`. | `id` is referenced by `listens`. |

### Music metadata (written by the analyzer)

| Table | Purpose | Key columns | Relationships |
|-------|---------|-------------|---------------|
| `artists` | Canonical artist records. | `name`, `name_normalized` (unique), `sort_name`, `mbid`. | Referenced by `albums`, `tracks.primary_artist_id`, `track_artists`, `listen_artists`. |
| `artist_aliases` | Alternate artist spellings. | `alias_normalized` (unique). | Points to `artists.id`. Used during normalization. |
| `albums` | Albums per artist. | `title`, `title_normalized`, `year`, `mbid`. | `artist_id` → `artists.id`; unique combination of `artist_id` + `title_normalized`. |
| `tracks` | Core entity of the data model. | `title`, `title_normalized`, `album_id`, `primary_artist_id`, `duration_secs`, `track_uid` (unique), `mbid`, `isrc`, `acoustid`. | References `albums.id` and `artists.id`. Analyzer uses `track_uid` for de-duplication. |
| `track_artists` | Artist roles per track. | `artist_id`, `role`. | Connects multiple artists to a track. |
| `title_aliases` | Alternate track titles. | `alias_normalized`. | References `tracks.id`; used when matching listens. |
| `genres` | Canonical genres. | `name`, `name_normalized`. | Referenced by `track_genres` and `listen_genres`. |
| `track_genres` | Assigns weighted genres to tracks. | `weight` (default 100). | Composite of `track_id` and `genre_id`. |
| `labels` | Music labels. | `name`, `name_normalized`. | Linked via `track_labels`. |
| `track_labels` | Connects tracks to labels. | - | Composite primary key (`track_id`, `label_id`). |
| `tag_sources` | Provenance for tag attributes. | `name`, `priority`. | Referenced by `track_tag_attributes`. |
| `track_tag_attributes` | Arbitrary tag/value pairs per track. | `key`, `value`, `source_id`. | Stores attributes such as mood or BPM. The analyzer applies `priority` ordering. |
| `media_files` | Local media files scanned by the analyzer. | `file_path`, `file_path_hash` (unique), `file_size`, `file_mtime`, `audio_hash`, `duration_secs`, `parsed_metadata_json`, `last_scan_at`. | Links one-to-many to `tracks` via matching (no FK). Analyzer stores scan results here. |

### Listening history (primarily written by the scrobbler)

| Table | Purpose | Key columns | Relationships |
|-------|---------|-------------|---------------|
| `listens` | Listening events per user. | `user_id`, `track_id`, `listened_at`, `source`, `source_track_id`, `artist_name_raw`, `track_title_raw`, `album_title_raw`, `enrich_status`, `match_confidence`. | Foreign keys to `users` and optionally `tracks`. The analyzer enriches listens and updates `enrich_status`, `match_confidence`, `last_enriched_at`. |
| `listen_match_candidates` | Stores alternate matches discovered by the analyzer. | `track_id`, `confidence`. | Connects `listens` to potential `tracks`. |
| `listen_artists` | Flattened artists per listening event. | - | Joins `listens` to `artists`. |
| `listen_genres` | Genres per listening event. | - | Joins `listens` to `genres`. |

### Configuration

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `config` | Stores key/value configuration, such as analyzer settings or API keys. | `key`, `value`, `updated_at`. |

## Usage patterns

- **Analyzer ingest** reads files (`media_files`), creates or updates `artists`, `albums`, `tracks`, and relationship tables (`track_artists`, `track_genres`, `track_labels`, `track_tag_attributes`, `title_aliases`). When matching listens the analyzer populates `listen_match_candidates` and updates `listens.track_id`, `enrich_status`, and `match_confidence`.
- **Scrobbler API/UI** writes new `listens` (including raw fields `artist_name_raw`, `track_title_raw`, `album_title_raw`) and consumes enriched data via the relationships. It relies on canonical metadata to support search and browsing.

## Media library and listening history schemas

The application now enforces a physical split between media metadata and listening history. Two schemas are created automatically during bootstrap:

| Schema | Ownership | Tables (indicative) | Notes |
|--------|-----------|---------------------|-------|
| `medialibrary` | Analyzer | `artists`, `artist_aliases`, `albums`, `tracks`, `track_artists`, `track_genres`, `genres`, `labels`, `track_labels`, `track_tag_attributes`, `tag_sources`, `media_files`, `title_aliases` | Contains canonical metadata derived from local scans or enrichment jobs. |
| `listens` | Scrobbler | `users`, `listens`, `listen_artists`, `listen_genres`, `listen_match_candidates`, configuration tables that drive ingestion | Stores listening events, aggregates, and app configuration. |

The `listens.listens` table keeps a foreign key into `medialibrary.tracks`, so every listen still resolves to canonical track metadata while writes remain isolated to the owning service.

Existing single-schema deployments are upgraded in place. During application start-up the bootstrap routine will:

1. Create the `medialibrary` and `listens` schemas (or in-memory attachments for SQLite-based tests).
2. Move legacy tables into their new schemas while preserving primary keys and data.
3. Re-run column/index guards to ensure historical databases gain any newer analyzer fields.

Fresh installations simply create the tables directly inside the appropriate schema.

## Column reference

The table below maps common properties to their storage locations:

| Property | Table.column | Description |
|----------|--------------|-------------|
| Title (canonical) | `tracks.title` | Final title used in the UI and during matching. |
| Title (normalized) | `tracks.title_normalized` | Analyzer leverages this for de-duplication. |
| Artist name (canonical) | `artists.name` | Displayed name. |
| Artist name (normalized) | `artists.name_normalized` | Unique key for artist matching. |
| Album title | `albums.title` | Parent album of a track. |
| Raw artist input | `listens.artist_name_raw` | Original string from the source prior to matching. |
| Raw track title | `listens.track_title_raw` | Original track title. |
| Duration (track) | `tracks.duration_secs` | Analyzer-derived duration in seconds. |
| Duration (listen) | `listens.duration_secs` | Observed length of the listening event. |
| Genre | `genres.name` / via `track_genres`, `listen_genres` | Canonical genre. |
| Label | `labels.name` | Music label associated with the track. |
| Audio hash | `media_files.audio_hash` | Analyzer uses this to detect duplicates. |

## Indexing and constraints

- Uniqueness on `artists.name_normalized`, `albums.artist_id + title_normalized`, `tracks.track_uid`, `track_artists` (track/artist/role), and `track_labels` prevents duplicates.
- `listens` enforces `uq_listen_dedupe` on (`user_id`, `track_id`, `listened_at`) to avoid duplicate scrobbles.
- Indexes on normalized names and status fields speed up analyzer queries for matching and enrichment.

## Extensibility guidelines

New tables should follow the existing normalization strategy:

1. Introduce a canonical table with normalized columns (`*_normalized`).
2. Use join tables with composite primary keys for many-to-many relationships.
3. Preserve raw source columns in `listens` or a similar event table to avoid losing original data.

These practices keep analyzer and scrobbler in sync and make it easy to locate and enrich properties.
