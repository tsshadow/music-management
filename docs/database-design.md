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
rules_festivals ──< rules_festival_aliases
                └─< rules_festival_editions
rules_podcasts ──< rules_podcast_aliases
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
| `rules_genres` | Every genre ever seen, with its curation state (`white` keep, `black` drop, `unknown` awaiting a decision) and optional correction target. See [docs/designs/genre-curation/technical.md](designs/genre-curation/technical.md). | `name`, `normalized_name`, `state`, `canonical_id`, `occurrences` |
| `rules_artist_genres` | Mapping from artist name to a default genre. | `artist_name`, `genre_id` |
| `rules_label_genres` | Mapping from label name to a default genre. | `label_name`, `genre_id` |
| `rules_subgenre_hierarchy` | Defines relationships (e.g., Uptempo is a subgenre of Hardcore). | `subgenre`, `genre` |
| `rules_ignored_artists` | Artists to skip during processing. | `name` |
| `rules_artist_evidence` | Per artist name, the last verdict of the scheduled external-evidence run (`approve`/`unresolved`/`skipped`/`incomplete`), its rule, evidence JSON, round and when it was applied. Not a decision -- that is `rules_artists`, signed `auto-external` when applied. See [docs/designs/artist-curation/technical.md](designs/artist-curation/technical.md), "Scheduled evidence run". | `name`, `verdict`, `run_id`, `applied_at` |
| `rules_artist_evidence_runs` | One row per round of the scheduled evidence run: dry run or not, and its counts. | `id`, `started_at` |
| `rules_artist_legacy_trust` | Artist names already in the library when the curation queue was wired to the tagger (migrate_v40). The tagger trusts an approved name or one of these that is still undecided; every other name is pending. | `name` |
| `rules_ignored_genres` | (Legacy) Migrated into `rules_genres` as state `black`; no longer read by the tagger. | `name` |
| `rules_catid_label` | Mapping Catalog IDs to library_labels. | `catid`, `label` |
| `rules_festival_data` | (Legacy) Migrated into `rules_festivals` and `rules_festival_editions` by `migrate_v7_festivals.sql`; no longer read by the tagger. | `festival`, `year` |
| `rules_festivals` | One row per festival: the name that ends up on the `FESTIVAL` tag and thus on the card in the app. | `id`, `normalized_name` |
| `rules_festival_aliases` | The spellings a festival occurs under in titles and folder names. The longest matching alias wins. | `festival_id`, `normalized_alias` |
| `rules_festival_editions` | The date of one edition. Optional -- without it a set is still labelled, only its date is left alone. | `festival_id`, `year` |
| `rules_podcasts` | One row per radio show or podcast series, curated white/black/unknown; only `white` is ever tagged. | `id`, `normalized_name`, `state` |
| `getsongbpm_lookups` | GetSongBPM's tempo per song, keyed on a SHA-256 of the normalised first artist and title: asked once by the bpm-analyzer while a key is set, a miss again after 90 days. The octave choice reads `bpm` as a prior. See [docs/designs/getsongbpm-prior/technical.md](designs/getsongbpm-prior/technical.md). | `lookup_key`, `status`, `bpm`, `fetched_at` |
| `radio_stations` | One row per live station from outside MuMa, kept in Beheer. A device plays `stream_url` directly. No seed adds a station, so a new database has none. | `slug`, `name`, `stream_url`, `sort_order`, `enabled` |
| `rules_podcast_aliases` | The spellings one show occurs under, so every variant matches the same name. The longest matching alias wins. | `podcast_id`, `normalized_alias` |
| `rules_genre_backlog` | (Legacy) Migrated into `rules_genres` as state `unknown`; no longer read by the tagger. | `genre` |
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
| `channels` | An account on a platform that a file arrived through — a SoundCloud or YouTube account, a Telegram chat. Not a label: a platform is how music arrived, not who released it. `label_id` and `artist_id` are independent and both nullable, so a channel may be a label, an artist, both, or neither until someone decides. Platforms stay split, so one imprint's SoundCloud and YouTube accounts are two rows that converge through `label_id`. | `platform`, `normalized_name`, `label_id`, `artist_id` | Unique on (`platform`, `normalized_name`). |
| `library_track_channels` | Junction table for library_tracks and channels. | `track_id`, `channel_id` | |
| `library_tagged_files` | Tracking which files were tagged. | `path`, `last_tagged` | |
| `tagger_processed_files` | The tagger's bookkeeping and retag queue: one row per file it has seen. | `filepath`, `mtime`, `needs_rescan`, `rescan_reason`, `attempts`, `last_attempt` | `filepath` is the primary key and `utf8mb4_bin` (migrate_v37): under the server default a case, accent or emoji difference made two files one row. `attempts`/`last_attempt` pace the retries of a file that keeps failing; after five it is parked with reason `failed` ([bug report 051](bug-reports/051-a-failing-file-is-retried-every-round-forever.md)). |
| `library_broken_songs` | Files that failed analysis. | `path`, `error_code` | |
| `library_broken_song_artist_lookup`| Mapping for problematic artist names. | `raw_name` | |

### 4. Listening Domain (`listens`)

*Note: This domain is currently defined in the architecture but not yet fully implemented in the physical database.*

| Table | Purpose | Key columns |
| :--- | :--- | :--- |
| `users` | Application users. | `username` |
| `listens` | Canonical listening events. | `user_id`, `track_id`, `listened_at` |

In the physical database this domain is `scrobble_listens` (resolved to a library track) and
`scrobble_unmatched_listens` (kept verbatim as artist/title until a match is found). Both carry:

- `source` — where the play happened: `frontend`, `mobile`, `auto` (phone in the car), `lms-web`,
  `listenbrainz`, `manual`. Rows written before 2026-08 carry `lms`, which meant only "played
  through the server".
- `played_secs` — seconds actually played, or `NULL` when the client did not report it. `NULL` is not
  zero: it means unknown. It matters more here than it would elsewhere, because the average track in
  this library is 939 seconds, so plays multiplied by track length is not an estimate of listening
  time. See [docs/designs/wrapped/technical.md](designs/wrapped/technical.md).

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
- `library_tracks.primary_artist_id` is indexed (`idx_tracks_primary_artist`): every join from a listen,
  a statistic or a feed to an artist goes through it. `scrobble_listens` has `idx_listens_track_user`
  on (`track_id`, `username`) for per-track questions, and `idx_listens_listened_at` /
  `idx_unmatched_listened_at` for date ranges across all users.
- The UNIQUE key on `scrobble_unmatched_listens` (`username`, `listened_at`, `artist_name`,
  `track_title`) is longer than InnoDB's index limit under utf8mb4, so MariaDB builds it as a `USING
  HASH` long unique key. It enforces uniqueness exactly (no prefix truncation), but it cannot serve a
  range seek -- a date range on that table relies on `idx_unmatched_listened_at`.
- A column that is compared as an identifier -- a path, a normalised key -- is `utf8mb4_bin`, not the
  server default. `utf8mb4_general_ci` folds case and accents and gives every character outside the
  BMP the same weight, which merged `channels.normalized_name` (migrate_v13), `library_works.work_key`
  (migrate_v19) and `tagger_processed_files.filepath` (migrate_v37). A join from such a column to a
  `_ci` one names `COLLATE utf8mb4_bin` explicitly: a newer server's default,
  `utf8mb4_uca1400_ai_ci`, is not reconciled with another collation implicitly.
- A TIMESTAMP column always declares its `DEFAULT`. On MariaDB before 10.10
  (`explicit_defaults_for_timestamp=OFF`) the first TIMESTAMP column of a table without one silently
  gets `ON UPDATE CURRENT_TIMESTAMP` too, and every UPDATE of the row rewrites it. That moved
  `listened_at` on both scrobble tables -- see
  [bug report 039](bug-reports/039-listened-at-rewritten-on-every-rematch.md).

## Extensibility guidelines

New tables should follow the existing normalization strategy:

1. Introduce a canonical table with normalized columns (`*_normalized`).
2. Use join tables with composite primary keys for many-to-many relationships.
3. Preserve raw source columns in `listens` or a similar event table to avoid losing original data.

These practices keep analyzer and scrobbler in sync and make it easy to locate and enrich properties.
