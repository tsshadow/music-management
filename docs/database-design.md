# Database Design

This document describes the relational data model used by the music management system. The database is organized into four logical domains to separate responsibilities and ensure scalability.

## High-level overview

The system is organized around the following four domains:

1.  **Tagger Domain (`rules`)**: Contains knowledge about how music should be classified. This includes validation lists and hardcoded rules (e.g., Artist -> Genre mapping).
2.  **Downloader Domain (`downloads`)**: Manages the sources where music is acquired (Soundcloud, YouTube) and library_tracks download history.
3.  **Library Domain (`library`)**: The "Source of Truth" for the collection. Contains file paths, metadata (library_artists, rules_genres), and technical analysis results (BPM, ML features).
4.  **Listening Domain (`listens`)**: Records user listening history and links it to library_tracks in the library.

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
1. TAGGER DOMAIN (RULES & VALIDATION)
──────────────────────────────────────────────────────────────────────────────
rules_genres ──< rules_subgenre_hierarchy
rules_artist_genres ──> rules_genres
rules_label_genres  ──> rules_genres
rules_ignored_artists, rules_ignored_genres
rules_catid_label, rules_festival_data
rules_genre_backlog

──────────────────────────────────────────────────────────────────────────────
2. DOWNLOADER DOMAIN
──────────────────────────────────────────────────────────────────────────────
{soundcloud|youtube}_accounts ──< {soundcloud|youtube}_archive
{soundcloud|youtube}_songs (queue)

──────────────────────────────────────────────────────────────────────────────
3. LIBRARY DOMAIN (SOURCE OF TRUTH)
──────────────────────────────────────────────────────────────────────────────
library_tracks ──< library_track_artists >── library_artists
   │           │               └─< library_artist_aliases
   │
   ├──< library_track_genres >── rules_genres
   │
   ├──< library_track_labels >── library_labels
   │
   ├──< library_media_files (1 ── N)
   │
   ├─── library_track_audio_features (1 ── 1)
   │
   ├─── library_track_ml_labels (1 ── 1)
   │
   └─── library_track_ml_predictions (1 ── 1)

library_tagged_files (status)
library_broken_songs, library_broken_song_artist_lookup (errors)

──────────────────────────────────────────────────────────────────────────────
4. LISTENING DOMAIN
──────────────────────────────────────────────────────────────────────────────
users ──< listens_raw
            │
            └─< listens
                 └──library_tracks (Library)
                 ├──< listen_artists >── library_artists
                 └──< listen_genres >── rules_genres
```

## Tables by domain

### 1. Tagger Domain (`rules`)

These tables contain the "knowledge" of the system, used by the tagger service to clean up and enrich metadata.

| Table | Purpose | Key columns |
| :--- | :--- | :--- |
| `rules_genres` | List of allowed rules_genres and their corrections. | `genre`, `corrected_genre` |
| `rules_artist_genres` | Mapping from artist name to a default genre. | `artist_name`, `genre_id` |
| `rules_label_genres` | Mapping from label name to a default genre. | `label_name`, `genre_id` |
| `rules_subgenre_hierarchy` | Defines relationships (e.g., Uptempo is a subgenre of Hardcore). | `subgenre`, `genre` |
| `rules_ignored_artists` | Artists to skip during processing. | `name` |
| `rules_ignored_genres` | Genres to skip during processing. | `name` |
| `rules_catid_label` | Mapping Catalog IDs to library_labels. | `catid`, `label` |
| `rules_festival_data` | Information about festivals for title parsing. | `festival`, `year` |
| `rules_genre_backlog` | New rules_genres detected but not yet validated. | `genre` |
| `rules_genres_new` | (Legacy) New genre structure being phased in. | `name` |

### 2. Downloader Domain (`downloads`)

Focused on acquiring new library_tracks.

| Table | Purpose | Key columns |
| :--- | :--- | :--- |
| `downloads_soundcloud_accounts` | Followed Soundcloud channels. | `name`, `soundcloud_id` |
| `downloads_youtube_accounts` | Followed YouTube channels. | `name`, `channel_id` |
| `downloads_soundcloud_archive` | History of downloaded Soundcloud library_tracks. | `video_id`, `account` |
| `downloads_youtube_archive` | History of downloaded YouTube library_tracks. | `video_id`, `account` |
| `downloads_soundcloud_queue` | Queue for Soundcloud downloads. | `url`, `is_downloaded` |
| `downloads_youtube_queue` | Queue for YouTube downloads. | `url`, `is_downloaded` |

### 3. Library Domain (`library`)

The core of the collection, where metadata and analysis results converge.

| Table | Purpose | Key columns | Notes |
| :--- | :--- | :--- | :--- |
| `library_tracks` | Central track entity. | `title`, `track_uid` | Links to everything in the library. |
| `library_media_files` | Physical files on disk. | `file_path`, `file_path_hash` | Contains `audio_hash` for de-duplication. |
| `library_track_audio_features`| Technical ML features. | `track_id`, `tempo`, `mfcc_*` | Input for ML models. |
| `library_track_ml_labels` | Ground Truth library_labels. | `track_id`, `ml_genre` | Used for training models. |
| `library_track_ml_predictions`| ML Model predictions. | `track_id`, `predicted_genre` | Results from `predict.py`. |
| `library_artists` | Canonical library_artists. | `name`, `mbid` | |
| `library_labels` | Canonical library_labels. | `name` | |
| `library_track_artists` | Junction table for library_tracks and library_artists. | `track_id`, `artist_id` | Supports roles (remixer, producer, etc). |
| `library_track_genres` | Junction table for library_tracks and rules_genres. | `track_id`, `genre_id` | Supports weights. |
| `library_track_labels` | Junction table for library_tracks and library_labels. | `track_id`, `label_id` | |
| `library_tagged_files` | Tracking which files were tagged. | `path`, `last_tagged` | |
| `library_broken_songs` | Files that failed analysis. | `path`, `error_code` | |
| `library_broken_song_artist_lookup`| Mapping for problematic artist names. | `raw_name` | |

### 4. Listening Domain (`listens`)

*Note: This domain is currently defined in the architecture but not yet fully implemented in the physical database.*

| Table | Purpose | Key columns |
| :--- | :--- | :--- |
| `users` | Application users. | `username` |
| `listens` | Canonical listening events. | `user_id`, `track_id`, `listened_at` |

## ML Integration

The Library domain is specifically extended to support Machine Learning:

- **`library_track_audio_features`**: Stores the output of the `TrackAnalyzer`. These are the numerical values understood by the models.
- **`library_track_ml_labels`**: Stores human-verified library_labels (or high-confidence MP3 tags) that serve as "training material" for the ML trainer.
- **`library_track_ml_predictions`**: Stores the output of the trained models.
- **Feedback Loop**: Rules from the Tagger domain can be used to initially populate `library_track_ml_labels`, after which the ML model can learn to refine these classifications based on audio characteristics.

## Schema implementation

While the domains are logically separated, they can reside in a single physical database or be split across multiple schemas (`medialibrary`, `listens`, `rules`, `downloads`). The system supports cross-schema foreign keys to maintain integrity.


## Indexing and constraints

- Uniqueness on `library_artists.name_normalized`, `release_groups.primary_artist_id + title_normalized`,
  `releases.release_group_id + title_normalized + release_date`, `library_tracks.track_uid`, `library_track_artists` (track/artist/role),
  and `library_track_labels` prevents duplicates.
- `listens` enforces `uq_listen_dedupe` on (`user_id`, `track_id`, `listened_at`) to avoid duplicate scrobbles.
- Indexes on normalized names and status fields speed up analyzer queries for matching and enrichment.

## Extensibility guidelines

New tables should follow the existing normalization strategy:

1. Introduce a canonical table with normalized columns (`*_normalized`).
2. Use join tables with composite primary keys for many-to-many relationships.
3. Preserve raw source columns in `listens` or a similar event table to avoid losing original data.

These practices keep analyzer and scrobbler in sync and make it easy to locate and enrich properties.
