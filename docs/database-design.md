# Database Design

This document describes the relational data model shared by the `scrobbler` and `analyzer` modules. Use it as a quick
reference to find where data lives and how tables relate to one another.

## High-level overview

- User activity is stored in listens, with optional relationships to tracks, artists, and genres to enrich listening
  history.

- Media library metadata flows in through the analyzer. It enriches artists, releases/release_groups, tracks, and media
  files while populating association tables (track_artists, track_genres, release_labels, track_tag_attributes,
  title_aliases).

- Analyzer ↔ Scrobbler can operate on dedicated schemas (medialibrary and listens) that keep write ownership isolated
  while preserving cross-schema foreign keys. Deployments without schema privileges can continue to run in a single
  shared
  schema.

### Relationship model (text representation)

```
LEGEND
───────
A ──< B         : one-to-many   (A 1 ── N B)
A >──< B        : many-to-many  (via junction table)
[ ]             : junction/association table
( )             : optional relationship / nullable FK
{XOR}           : exactly one of the referenced FKs must be set

──────────────────────────────────────────────────────────────────────────────
USERS & LISTENING
──────────────────────────────────────────────────────────────────────────────
users ──< listens_raw
            │
            └─< listens
                 └──tracks

users ──< listens
users ──< listens_raw

──────────────────────────────────────────────────────────────────────────────
MEDIA LIBRARY (TRACKS, ARTISTS, GENRES, TAGS, FILES)
──────────────────────────────────────────────────────────────────────────────
tracks ──< track_artists >── artists
   │           │               └─< artist_aliases
   │
   ├──< track_genres >── genres
   │
   ├──< track_tag_attributes >── tag_sources
   │
   └── media_files (1 ── N)

tracks ──< external_ids
artists ──< external_ids
genres  ──< external_ids  (rare, but possible if you standardize)
tag_sources ──< (referenced by track_tag_attributes)

──────────────────────────────────────────────────────────────────────────────
RELEASE MODEL (GROUPS, RELEASES, LABELS, TRACKLISTS)
──────────────────────────────────────────────────────────────────────────────
release_groups ──< releases
      (umbrella)     │
                     ├──< release_items >── tracks
                     │
                     ├──< [release_labels] >── labels
                     │          (cat_id, role, territory on the junction)
                     │
                     ├──< [release_publishers] >── publishers
                     │
                     └──< external_ids

labels     ──< release_labels >── releases
publishers ──< release_publishers >── releases

NOTE: releases.release_group_id is NULLABLE (single-edition releases don’t need a group)

──────────────────────────────────────────────────────────────────────────────
PLAYLISTS & CHANNELS
──────────────────────────────────────────────────────────────────────────────
publishers ──< playlists
playlists  ──< playlist_items {XOR: track_id OR release_id}
                 ├───→ tracks
                 └───→ releases

publishers ──< external_ids (e.g., youtube_channel_id)

──────────────────────────────────────────────────────────────────────────────
EVENTS (FESTIVALS/SHOWS) & LIVE RECORDINGS
──────────────────────────────────────────────────────────────────────────────
events ──< event_recordings >── tracks
events ──< external_ids
tracks ──< external_ids (e.g., youtube_video_id, sc_track_id, acoustid, isrc)

──────────────────────────────────────────────────────────────────────────────
CONFIG / AUX
──────────────────────────────────────────────────────────────────────────────
config (key/value store; app settings)

```

## Tables by domain

### Users

| Table   | Purpose                      | Key columns                        | Notes                            |
|---------|------------------------------|------------------------------------|----------------------------------|
| `users` | Application user management. | `username` (unique), `created_at`. | `id` is referenced by `listens`. |

### Music metadata (written by the analyzer)

| Table                  | Purpose                | Key columns                                                             | Relationships                                                                                                               |
|------------------------|------------------------|-------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------|
| `media_files`          | Local files            | `file_path_hash` (unique), `audio_hash`, `duration_secs`                | Optional **FK** `track_id` → `tracks.id` (NULL when unmatched)                                                              |
| `tracks`               | Recordings             | `title`, `duration_secs`, `track_uid` (unique)                          | ⇐ `media_files.track_id`; ⇒ `track_artists`, `track_genres`, `track_tag_attributes`; optional `primary_artist_id`           |
| `track_artists`        | Artist roles per track | (`track_id`,`artist_id`,`role`,`position`) unique                       | ⇒ `artists.id` (role enum: primary/featuring/remixer/…; `position` keeps order)                                             |
| `artists`              | Canonical artists      | `name`, `sort_name`, `mbid`                                             | ⇐ `track_artists`, `artist_aliases`                                                                                         |
| `artist_aliases`       | Alternate spellings    | (`artist_id`,`alias`) unique                                            | ⇒ `artists.id`                                                                                                              |
| `genres`               | Canonical genres       | `name` unique                                                           | ⇐ `track_genres`                                                                                                            |
| `track_genres`         | Weighted genres        | (`track_id`,`genre_id`) unique, `weight`                                | ⇒ `tracks`,`genres`                                                                                                         |
| `releases`             | Concrete editions      | `title`, `release_date`, `release_group_id` (NULL), `country`, `format` | ⇒ `release_groups` (optional), ⇒ `release_labels`, ⇒ `release_items`                                                        |
| `release_groups`       | Bundles editions       | `title`, `type` (album/single/EP/comp/live), `mbid`                     | ⇐ `releases` (many-to-one)                                                                                                  |
| `release_items`        | Tracklist per release  | (`release_id`,`track_id`,`disc_no`,`track_no`) unique                   | ⇒ `releases`,`tracks` (captures CD/vinyl/digital differences)                                                               |
| `labels`               | Music labels           | `name`                                                                  | ⇐ `release_labels`                                                                                                          |
| `release_labels`       | Labels per release     | (`release_id`,`label_id`, `cat_id`) unique                              | ⇒ `releases`,`labels`                                                                                                       |
| `publishers`           | Channels/platforms     | `name`, `platform` (YouTube/SC/Spotify/…), `handle`                     | Use for Q-dance YouTube channel                                                                                             |
| `release_publishers`   | Publisher per release  | (`release_id`,`publisher_id`) unique                                    | ⇒ `releases`,`publishers`                                                                                                   |
| `playlists`            | Playlists/series       | `platform`, `owner_publisher_id`, `title`                               | ⇒ `publishers`                                                                                                              |
| `playlist_items`       | Items in a playlist    | (`playlist_id`,`position`) unique, `track_id` **or** `release_id`       | ⇒ `playlists`, ⇒ `tracks`/`releases`                                                                                        |
| `events`               | Events/festivals       | `name`, `start_date`, `end_date`, `location`                            | Defqon.1, Qlimax, etc.                                                                                                      |
| `event_recordings`     | Links sets to event    | (`event_id`,`track_id`) unique, `stage`, `set_time`                     | ⇒ `events`,`tracks`                                                                                                         |
| `tag_sources`          | Tag provenance         | `name`, `priority`                                                      | ⇐ `track_tag_attributes`                                                                                                    |
| `track_tag_attributes` | Key/val per track      | (`track_id`,`key`,`source_id`) unique, `value`                          | Resolve by `tag_sources.priority`                                                                                           |
| `external_ids`         | Generic external IDs   | (`entity_type`,`entity_id`,`scheme`,`value`) unique                     | For `tracks`/`releases`/`release_groups`/`artists` (schemes: `mbid`,`isrc`,`acoustid`,`youtube_id`,`sc_id`,`spotify_id`, …) |

### Listening history (primarily written by the scrobbler)

| Table                     | Purpose                                                | Key columns                                                                                                                                                  | Relationships                                                                                                                                                              |
|---------------------------|--------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `listens_raw`             | Immutable ingest of scrobbles from any source.         | `user_id`, `ingested_at`, `source`, `source_track_id`, `payload_json`, `listened_at`                                                                         | **Unique**: (`user_id`,`listened_at`,`source`,COALESCE(`source_track_id`,'')); referenced by `listens.raw_id`.                                                             |
| `listens`                 | Canonical listening events used for queries/analytics. | `raw_id`, `user_id`, `track_id` (nullable), `listened_at`, `duration_secs`(nullable) `enrich_status`, `match_confidence`, `match_reason`, `last_enriched_at` | **FKs**: `raw_id` → `listens_raw.id`; `user_id` → `users.id`; `track_id` → `tracks.id` (nullable). Indexes on (`user_id`,`listened_at DESC`), `enrich_status`, `track_id`. |
| `listen_match_candidates` | Alternate track matches discovered during enrichment.  | `listen_id`, `track_id`, `confidence`, `features_json`                                                                                                       | **FKs**: `listen_id` → `listens.id`, `track_id` → `tracks.id`. **Unique**: (`listen_id`,`track_id`).                                                                       |

### Configuration

| Table    | Purpose                                                                | Key columns                   |
|----------|------------------------------------------------------------------------|-------------------------------|
| `config` | Stores key/value configuration, such as analyzer settings or API keys. | `key`, `value`, `updated_at`. |

## Usage patterns

- **Analyzer ingest** reads files (`media_files`), creates or updates `artists`, `albums`, `tracks`, and relationship
  tables (`track_artists`, `track_genres`, `track_labels`, `track_tag_attributes`, `title_aliases`). When matching
  listens the analyzer populates `listen_match_candidates` and updates `listens.track_id`, `enrich_status`, and
  `match_confidence`.
- **Scrobbler API/UI** writes new listens. If a canonical track.id exists, link it. If not, prefer creating a
  provisional_tracks entry (and set listens.enrich_status='provisional'), then let the analyzer promote/merge into
  tracks later. Only create real tracks immediately when you have high-confidence metadata (e.g., external IDs or audio
  hashes).

## Media library and listening history schemas

The application supports a physical split between media metadata and listening history. When configured, two schemas are
created (or attached for SQLite) during bootstrap:

| Schema         | Ownership | Tables (indicative)                                                                                                                                                                                                                                                                                                                                             | Notes                                                           |
|----------------|-----------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------|
| `medialibrary` | Analyzer  | `artists`, `artist_aliases`, **`release_groups`**, **`releases`**, `release_items`, `tracks`, `track_artists`, `track_genres`, `genres`, `labels`, **`release_labels`**, `track_tag_attributes`, `tag_sources`, `media_files`, `title_aliases`, `publishers`, `release_publishers`, `playlists`, `playlist_items`, `events`, `event_recordings`, `external_ids` | Canonical metadata derived from local scans or enrichment jobs. |
| `listens`      | Scrobbler | `users`, `listens_raw`, `listens`, `listen_match_candidates`, `config`                                                                                                                                                                                                                                                                                          | Stores listening events, candidates, and app configuration.     |

The `listens.listens` table keeps a foreign key into `medialibrary.tracks`, so every listen still resolves to canonical
track metadata while writes remain isolated to the owning service.

Configure the split by setting the following environment variables before starting the application:

- `SCROBBLER_MEDIALIBRARY_SCHEMA` – schema/database used for analyzer-owned tables.
- `SCROBBLER_LISTENS_SCHEMA` – schema/database used for scrobbler-owned tables.

Leave either variable unset (or set it to an empty string) to keep the associated tables in the connection's default
schema, which preserves compatibility for hosted MySQL/MariaDB accounts that lack privileges to create additional
databases.

When schemas are provided, existing single-schema deployments are upgraded in place. During application start-up the
bootstrap routine will:

1. Create or attach the configured schemas.
2. Move legacy tables into their new schemas while preserving primary keys and data.
3. Re-run column/index guards to ensure historical databases gain any newer analyzer fields.

Fresh installations simply create the tables directly inside the configured schema(s).

## Column reference

The table below maps common properties to their storage locations:

| Property                | Table.column                                                    | Description                                                    |
|-------------------------|-----------------------------------------------------------------|----------------------------------------------------------------|
| Title (canonical)       | `tracks.title`                                                  | Final title used in the UI and during matching.                |
| Artist name (canonical) | `artists.name`                                                  | Display name.                                                  |
| **Release title**       | `releases.title` *(or `release_groups.title` for the umbrella)* | Parent edition/group.                                          |
| Duration (track)        | `tracks.duration_secs`                                          | Analyzer-derived duration in seconds.                          |
| **Duration (listen)**   | `listens.duration_secs`                                         | Observed listening length (nullable).                          |
| Genre                   | via `track_genres` → `genres.name`                              | Canonical and/or per-listen.                                   |
| Label                   | via `release_labels` → `labels.name`                            | Label(s) per release; cat IDs live on `release_labels.cat_id`. |
| Audio hash              | `media_files.audio_hash`                                        | Analyzer uses this to detect duplicates.                       |


## Indexing and constraints

- Uniqueness on `artists.name_normalized`, `albums.artist_id + title_normalized`, `tracks.track_uid`, `track_artists` (
  track/artist/role), and `track_labels` prevents duplicates.
- `listens` enforces `uq_listen_dedupe` on (`user_id`, `track_id`, `listened_at`) to avoid duplicate scrobbles.
- Indexes on normalized names and status fields speed up analyzer queries for matching and enrichment.

## Extensibility guidelines

New tables should follow the existing normalization strategy:

1. Introduce a canonical table with normalized columns (`*_normalized`).
2. Use join tables with composite primary keys for many-to-many relationships.
3. Preserve raw source columns in `listens` or a similar event table to avoid losing original data.

These practices keep analyzer and scrobbler in sync and make it easy to locate and enrich properties.
