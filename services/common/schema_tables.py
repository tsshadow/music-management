"""Every table of the shared database, declared once (docs/designs/declarative-schema/).

Each statement is the shape production has, as `SHOW CREATE TABLE` prints it, so a fresh
database built from these equals production. `db_init.ensure_tables_exist()` runs them on start-up
and `schema_reconcile` adds what a live database is missing. A change MariaDB cannot make by
adding (a rename, a type change, a dropped column) is a script of its own, run with a backup.

Order matters: a table comes after every table its foreign keys point at.
"""

# (table name, CREATE TABLE statement), parents before children.
TABLES: tuple[tuple[str, str], ...] = (
    (
        'artist_external_ids',
        """
CREATE TABLE IF NOT EXISTS `artist_external_ids` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `artist_id` int(11) NOT NULL,
  `source` varchar(50) NOT NULL,
  `external_id` varchar(255) NOT NULL,
  `external_url` text DEFAULT NULL,
  `verified` tinyint(4) DEFAULT 0,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT NULL ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_artist_source_external` (`artist_id`,`source`,`external_id`),
  KEY `idx_artist_id` (`artist_id`),
  KEY `idx_source_external_id` (`source`,`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    # The top list itself, each entry with the library track it matched. matched_track_uid is what
    # the feed joins on: track_uid survives a rebuild, track and work ids do not.
    (
        'artist_popular_tracks',
        """
CREATE TABLE IF NOT EXISTS `artist_popular_tracks` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `artist_key` varchar(191) NOT NULL,
  `source` varchar(16) NOT NULL,
  `external_track_id` varchar(64) NOT NULL,
  `title` varchar(512) DEFAULT NULL,
  `normalized_title` varchar(191) DEFAULT NULL,
  `popularity` int(11) DEFAULT NULL,
  `position` int(11) NOT NULL,
  `matched_track_uid` varchar(255) DEFAULT NULL,
  `matched_work_id` int(11) DEFAULT NULL,
  `fetched_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_popular_track` (`artist_key`,`source`,`external_track_id`),
  KEY `idx_popular_tracks_matched` (`matched_track_uid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    # Per artist (normalized name, stable across a library rebuild) and source: when the
    # popular-tracks loop last fetched its top list and whether the artist was found. See
    # services/music_manager/popular_tracks/worker.py.
    (
        'artist_popularity_fetches',
        """
CREATE TABLE IF NOT EXISTS `artist_popularity_fetches` (
  `artist_key` varchar(191) NOT NULL,
  `source` varchar(16) NOT NULL,
  `artist_name` varchar(255) DEFAULT NULL,
  `external_artist_id` varchar(64) DEFAULT NULL,
  `status` enum('ok','not_found','error') NOT NULL,
  `track_count` int(11) NOT NULL DEFAULT 0,
  `matched_count` int(11) NOT NULL DEFAULT 0,
  `fetched_at` datetime NOT NULL,
  PRIMARY KEY (`artist_key`,`source`),
  KEY `idx_popularity_fetches_fetched_at` (`fetched_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'audit_events',
        """
CREATE TABLE IF NOT EXISTS `audit_events` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `event_type` varchar(100) NOT NULL,
  `actor_user_id` int(11) DEFAULT NULL,
  `target_user_id` int(11) DEFAULT NULL,
  `details` text DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'downloads_account_checks',
        """
CREATE TABLE IF NOT EXISTS `downloads_account_checks` (
  `source` varchar(32) NOT NULL,
  `account` varchar(255) NOT NULL,
  `last_checked_at` datetime NOT NULL,
  `last_upload_at` datetime DEFAULT NULL,
  `last_seen_track_id` varchar(64) DEFAULT NULL,
  `last_deep_sweep_at` datetime DEFAULT NULL,
  `snapshot_listed` int(11) DEFAULT NULL,
  `snapshot_held` int(11) DEFAULT NULL,
  `snapshot_excluded` int(11) DEFAULT NULL,
  `snapshot_remaining` int(11) DEFAULT NULL,
  `snapshot_state` varchar(16) DEFAULT NULL,
  `snapshot_at` datetime DEFAULT NULL,
  PRIMARY KEY (`source`,`account`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'downloads_rate_state',
        """
CREATE TABLE IF NOT EXISTS `downloads_rate_state` (
  `source` varchar(32) NOT NULL,
  `multiplier` int(11) NOT NULL DEFAULT 1,
  `consecutive_403` int(11) NOT NULL DEFAULT 0,
  `consecutive_429` int(11) NOT NULL DEFAULT 0,
  `clean_runs` int(11) NOT NULL DEFAULT 0,
  `last_403_at` datetime DEFAULT NULL,
  `last_429_at` datetime DEFAULT NULL,
  `cooldown_until` datetime DEFAULT NULL,
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `block_reason` varchar(32) DEFAULT NULL,
  PRIMARY KEY (`source`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'downloads_settings',
        """
CREATE TABLE IF NOT EXISTS `downloads_settings` (
  `source` varchar(32) NOT NULL,
  `setting_key` varchar(64) NOT NULL,
  `value` varchar(255) NOT NULL,
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`source`,`setting_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'downloads_soundcloud_accounts',
        """
CREATE TABLE IF NOT EXISTS `downloads_soundcloud_accounts` (
  `name` varchar(255) NOT NULL,
  `soundcloud_id` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'downloads_soundcloud_archive',
        """
CREATE TABLE IF NOT EXISTS `downloads_soundcloud_archive` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `account` varchar(255) NOT NULL,
  `video_id` varchar(255) NOT NULL,
  `filename` text DEFAULT NULL,
  `url` text DEFAULT NULL,
  `title` text DEFAULT NULL,
  `added_at` datetime DEFAULT current_timestamp(),
  `info_json` longtext DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_account_video` (`account`,`video_id`),
  KEY `idx_filename` (`filename`(255))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'downloads_soundcloud_unavailable',
        """
CREATE TABLE IF NOT EXISTS `downloads_soundcloud_unavailable` (
  `account` varchar(255) NOT NULL,
  `track_id` varchar(255) NOT NULL,
  `reason` varchar(64) NOT NULL,
  `first_seen` datetime NOT NULL,
  `last_seen` datetime NOT NULL,
  `source` varchar(32) NOT NULL DEFAULT 'soundcloud',
  `duration_seconds` int(11) DEFAULT NULL,
  `attempts` int(11) NOT NULL DEFAULT 0,
  PRIMARY KEY (`account`,`track_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'downloads_youtube_accounts',
        """
CREATE TABLE IF NOT EXISTS `downloads_youtube_accounts` (
  `name` varchar(255) NOT NULL,
  `channel_id` text DEFAULT NULL,
  `active` tinyint(1) DEFAULT 1,
  `download_type` enum('audio','video') NOT NULL DEFAULT 'audio',
  `min_duration` int(11) DEFAULT 60,
  `output_folder_override` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`name`,`download_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'downloads_youtube_archive',
        """
CREATE TABLE IF NOT EXISTS `downloads_youtube_archive` (
  `video_id` varchar(32) NOT NULL,
  `path` varchar(255) DEFAULT NULL,
  `account` varchar(255) NOT NULL,
  `filename` varchar(255) NOT NULL,
  `url` varchar(255) NOT NULL,
  `title` varchar(255) NOT NULL,
  `download_type` enum('audio','video') NOT NULL DEFAULT 'audio',
  `info_json` longtext DEFAULT NULL,
  `added_at` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`video_id`,`download_type`),
  UNIQUE KEY `uniq_video_id_download_type` (`video_id`,`download_type`),
  KEY `idx_path` (`path`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'events',
        """
CREATE TABLE IF NOT EXISTS `events` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `created_at` timestamp(3) NOT NULL DEFAULT current_timestamp(3),
  `level` varchar(10) NOT NULL,
  `source` varchar(50) NOT NULL,
  `logger` varchar(120) DEFAULT NULL,
  `title` varchar(255) DEFAULT NULL,
  `message` text DEFAULT NULL,
  `context` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`context`)),
  PRIMARY KEY (`id`),
  KEY `idx_created` (`created_at`),
  KEY `idx_level_created` (`level`,`created_at`),
  KEY `idx_source_created` (`source`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'feeds_profile_exclusions',
        """
CREATE TABLE IF NOT EXISTS `feeds_profile_exclusions` (
  `username` varchar(255) NOT NULL,
  `entity_type` enum('artist','label','genre') NOT NULL,
  `entity_name` varchar(255) NOT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`username`,`entity_type`,`entity_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'feeds_snapshot',
        """
CREATE TABLE IF NOT EXISTS `feeds_snapshot` (
  `username` varchar(255) NOT NULL,
  `slug` varchar(64) NOT NULL,
  `feed_date` date NOT NULL,
  `generated_at` datetime NOT NULL,
  `params_key` varchar(64) NOT NULL,
  `payload` longtext NOT NULL,
  PRIMARY KEY (`username`,`slug`,`feed_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    # Folder pairs the importer's renamer or mover left in place because the name it wanted was taken
    # by a folder holding a different release (bug report 091). One row per standing pair, keyed by a
    # hash of (step, source, target); the importer warns once when a row is created and deletes it
    # when the pair is no longer met. `fingerprint` is what both folders looked like when they were
    # last compared. The extractor files single files here too (bug report 119): `target` is empty or
    # a detail, and `reason` says why the file was left in place; NULL for a folder pair.
    # GetSongBPM's tempo per song (issue #152), keyed on a SHA-256 of the normalised first artist and
    # title: asked once, a miss again after 90 days. Read by the bpm-analyzer's octave choice.
    # See services/music_manager/bpm/getsongbpm.py.
    (
        'getsongbpm_lookups',
        """
CREATE TABLE IF NOT EXISTS `getsongbpm_lookups` (
  `lookup_key` char(64) NOT NULL,
  `artist` varchar(255) NOT NULL,
  `title` varchar(255) NOT NULL,
  `status` enum('ok','not_found') NOT NULL,
  `bpm` decimal(5,2) DEFAULT NULL,
  `song_id` varchar(64) DEFAULT NULL,
  `song_url` varchar(512) DEFAULT NULL,
  `fetched_at` datetime NOT NULL,
  PRIMARY KEY (`lookup_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'importer_conflicts',
        """
CREATE TABLE IF NOT EXISTS `importer_conflicts` (
  `pair_key` char(64) NOT NULL,
  `step` enum('renamer','mover','extractor') NOT NULL,
  `source` varchar(1024) NOT NULL,
  `target` varchar(1024) NOT NULL,
  `fingerprint` char(64) DEFAULT NULL,
  `reason` varchar(32) DEFAULT NULL,
  `first_seen` timestamp NULL DEFAULT current_timestamp(),
  `last_seen` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`pair_key`),
  KEY `step` (`step`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'library_artist_images',
        """
CREATE TABLE IF NOT EXISTS `library_artist_images` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `artist_id` int(11) NOT NULL,
  `source` varchar(50) NOT NULL,
  `source_id` varchar(255) DEFAULT NULL,
  `original_url` text DEFAULT NULL,
  `cached_path` text NOT NULL,
  `public_path` text DEFAULT NULL,
  `width` int(11) DEFAULT NULL,
  `height` int(11) DEFAULT NULL,
  `mime_type` varchar(100) DEFAULT NULL,
  `file_size` int(11) DEFAULT NULL,
  `confidence` tinyint(4) DEFAULT NULL,
  `is_primary` tinyint(4) DEFAULT 0,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT NULL ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_artist_source_id` (`artist_id`,`source`,`source_id`),
  KEY `idx_artist_id` (`artist_id`),
  KEY `idx_source` (`source`),
  KEY `idx_is_primary` (`is_primary`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'library_artists',
        """
CREATE TABLE IF NOT EXISTS `library_artists` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `sort_name` varchar(255) DEFAULT NULL,
  `mbid` varchar(36) DEFAULT NULL,
  `primary_image_id` int(11) DEFAULT NULL,
  `image_updated_at` datetime DEFAULT NULL,
  `image_status` varchar(50) DEFAULT NULL,
  `normalized_name` varchar(191) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`),
  KEY `idx_artists_normalized_name` (`normalized_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'library_bpm_priors',
        """
CREATE TABLE IF NOT EXISTS `library_bpm_priors` (
  `kind` varchar(8) NOT NULL,
  `prior_key` varchar(191) NOT NULL,
  `centre` double NOT NULL,
  `spread` double NOT NULL,
  `samples` int(11) NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`kind`,`prior_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    # What a file said before the tagger first touched it, plus the version of the code and a
    # fingerprint of the rules in force at that moment. The tagger rewrites tags in place and kept no
    # copy: ORIGINAL_TITLE and ORIGINAL_ARTIST are the two fields somebody noticed losing and
    # hand-rolled a rescue for, one rule each. Written once per file and never updated -- a later
    # pass sees a file this tagger already rewrote, so its idea of "arrival" is worth less than the
    # first one's. See services/tagger/ingestion.py.
    (
        'library_ingestion_records',
        """
CREATE TABLE IF NOT EXISTS `library_ingestion_records` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `file_path` text NOT NULL,
  `file_path_hash` varchar(64) NOT NULL,
  `file_size` bigint(20) DEFAULT NULL,
  `source` varchar(32) NOT NULL,
  `tags_json` longtext NOT NULL,
  `code_version` varchar(32) DEFAULT NULL,
  `rules_fingerprint` varchar(32) DEFAULT NULL,
  `recorded_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `file_path_hash` (`file_path_hash`),
  KEY `idx_ingestion_recorded_at` (`recorded_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    # Index and constraint names below are the ones the migrations gave production. Left unnamed,
    # MariaDB names an index after its column, so a fresh stack and a migrated one disagreed about
    # every one of them (tests/integration/test_schema_drift.py).
    (
        'library_labels',
        """
CREATE TABLE IF NOT EXISTS `library_labels` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `mbid` varchar(36) DEFAULT NULL,
  `parent_label_id` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`),
  KEY `fk_labels_parent` (`parent_label_id`),
  CONSTRAINT `fk_labels_parent` FOREIGN KEY (`parent_label_id`) REFERENCES `library_labels` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    # The measured tempo per track (BPM browse), keyed on track_uid so a rebuild or a file move keeps
    # it. Filled by the BPM analysis worker; read by services/music_manager/bpm/.
    (
        'library_track_bpm',
        """
CREATE TABLE IF NOT EXISTS `library_track_bpm` (
  `track_uid` varchar(255) NOT NULL,
  `status` enum('ok','failed') NOT NULL DEFAULT 'ok',
  `bpm` decimal(5,2) DEFAULT NULL,
  `raw_bpm` decimal(5,2) DEFAULT NULL,
  `confidence` decimal(4,3) DEFAULT NULL,
  `method` varchar(32) NOT NULL,
  `octave_corrected` tinyint(1) NOT NULL DEFAULT 0,
  `file_mtime` double DEFAULT NULL,
  `file_size` bigint(20) DEFAULT NULL,
  `attempts` int(11) NOT NULL DEFAULT 1,
  `error` varchar(255) DEFAULT NULL,
  `analyzed_at` datetime NOT NULL,
  `tag_bpm` decimal(5,2) DEFAULT NULL,
  `tag_action` varchar(16) DEFAULT NULL,
  `tag_checked_at` datetime DEFAULT NULL,
  `raw_confidence` decimal(4,3) DEFAULT NULL,
  `strength` float DEFAULT NULL,
  `half_score` float DEFAULT NULL,
  `double_score` float DEFAULT NULL,
  `fold_evidence` varchar(16) DEFAULT NULL,
  `fold_margin` float DEFAULT NULL,
  `fold_version` smallint(6) DEFAULT NULL,
  `external_bpm` decimal(5,2) DEFAULT NULL,
  PRIMARY KEY (`track_uid`),
  KEY `idx_track_bpm_bpm` (`bpm`),
  KEY `idx_track_bpm_status` (`status`,`analyzed_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'library_track_bpm_manual',
        """
CREATE TABLE IF NOT EXISTS `library_track_bpm_manual` (
  `track_uid` varchar(255) NOT NULL,
  `bpm` decimal(5,2) NOT NULL,
  `set_by` int(11) DEFAULT NULL,
  `set_at` datetime NOT NULL,
  PRIMARY KEY (`track_uid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'library_track_ml_predictions',
        """
CREATE TABLE IF NOT EXISTS `library_track_ml_predictions` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `track_id` varchar(255) NOT NULL,
  `model_version` varchar(50) NOT NULL,
  `predicted_genre` varchar(100) DEFAULT NULL,
  `confidence_genre` float DEFAULT NULL,
  `predicted_subgenre` varchar(100) DEFAULT NULL,
  `confidence_subgenre` float DEFAULT NULL,
  `predictions_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`predictions_json`)),
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `track_id` (`track_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'library_tracks',
        """
CREATE TABLE IF NOT EXISTS `library_tracks` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `track_uid` varchar(255) DEFAULT NULL,
  `title` varchar(512) DEFAULT NULL,
  `duration_secs` float DEFAULT NULL,
  `primary_artist_id` int(11) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `normalized_title` varchar(191) DEFAULT NULL,
  `normalized_base_title` varchar(191) DEFAULT NULL,
  `work_id` int(11) DEFAULT NULL,
  `version_kind` varchar(32) DEFAULT NULL,
  `version_score` int(11) DEFAULT NULL,
  `work_locked` tinyint(4) NOT NULL DEFAULT 0,
  `display_artist` varchar(512) DEFAULT NULL,
  `release_date` varchar(10) DEFAULT NULL,
  `form` varchar(16) DEFAULT NULL,
  `performance_date` varchar(10) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `track_uid` (`track_uid`),
  KEY `idx_created_at` (`created_at`),
  KEY `idx_tracks_normalized_title` (`normalized_title`),
  KEY `idx_tracks_normalized_base_title` (`normalized_base_title`),
  KEY `idx_tracks_work_id` (`work_id`),
  KEY `idx_tracks_primary_artist` (`primary_artist_id`),
  KEY `idx_tracks_form` (`form`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'library_works',
        """
CREATE TABLE IF NOT EXISTS `library_works` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `work_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `title` varchar(512) DEFAULT NULL,
  `primary_artist_id` int(11) DEFAULT NULL,
  `canonical_track_id` int(11) DEFAULT NULL,
  `pinned_track_id` int(11) DEFAULT NULL,
  `related_work_id` int(11) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `ranking_signature` varchar(32) DEFAULT NULL,
  `previous_canonical_track_id` int(11) DEFAULT NULL,
  `canonical_changed_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `work_key` (`work_key`),
  KEY `idx_works_canonical_changed_at` (`canonical_changed_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'news_bulletins',
        """
CREATE TABLE IF NOT EXISTS `news_bulletins` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `source_id` int(11) NOT NULL,
  `started_at` double NOT NULL,
  `duration_ms` int(11) NOT NULL,
  `size_bytes` bigint(20) NOT NULL,
  `filename` varchar(255) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_source_started` (`source_id`,`started_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'news_sources',
        """
CREATE TABLE IF NOT EXISTS `news_sources` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `slug` varchar(64) NOT NULL,
  `name` varchar(128) NOT NULL,
  `stream_url` varchar(512) NOT NULL,
  `minute_of_hour` tinyint(4) NOT NULL DEFAULT 0,
  `duration_seconds` int(11) NOT NULL DEFAULT 600,
  `lead_seconds` int(11) NOT NULL DEFAULT 5,
  `retention_count` int(11) NOT NULL DEFAULT 12,
  `enabled` tinyint(1) NOT NULL DEFAULT 1,
  `last_error` varchar(512) DEFAULT NULL,
  `last_success_at` double DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `slug` (`slug`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'permissions',
        """
CREATE TABLE IF NOT EXISTS `permissions` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `description` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'radio_channels',
        """
CREATE TABLE IF NOT EXISTS `radio_channels` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `slug` varchar(64) NOT NULL,
  `name` varchar(128) NOT NULL,
  `genre` varchar(128) DEFAULT NULL,
  `filter_json` text DEFAULT NULL,
  `enabled` tinyint(1) NOT NULL DEFAULT 1,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `slug` (`slug`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'radio_stations',
        """
CREATE TABLE IF NOT EXISTS `radio_stations` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `slug` varchar(64) NOT NULL,
  `name` varchar(128) NOT NULL,
  `stream_url` varchar(1024) NOT NULL,
  `sort_order` int(11) NOT NULL DEFAULT 0,
  `enabled` tinyint(1) NOT NULL DEFAULT 1,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `slug` (`slug`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'radio_timeline',
        """
CREATE TABLE IF NOT EXISTS `radio_timeline` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `channel_id` int(11) NOT NULL,
  `track_id` varchar(64) NOT NULL,
  `title` varchar(512) DEFAULT NULL,
  `artist` varchar(512) DEFAULT NULL,
  `album` varchar(512) DEFAULT NULL,
  `cover_art` varchar(64) DEFAULT NULL,
  `duration_ms` int(11) NOT NULL,
  `started_at` double NOT NULL,
  `ends_at` double NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_channel_started` (`channel_id`,`started_at`),
  KEY `idx_channel_ends` (`channel_id`,`ends_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'rating_tracks',
        """
CREATE TABLE IF NOT EXISTS `rating_tracks` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `entity_type` varchar(50) NOT NULL,
  `entity_id` varchar(255) NOT NULL,
  `username` varchar(255) NOT NULL,
  `rating` int(11) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `entity_type` (`entity_type`,`entity_id`,`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'release_store_lookups',
        """
CREATE TABLE IF NOT EXISTS `release_store_lookups` (
  `store` varchar(16) NOT NULL,
  `album_id` varchar(64) NOT NULL,
  `status` enum('ok','not_found') NOT NULL,
  `label` varchar(255) DEFAULT NULL,
  `upc` varchar(32) DEFAULT NULL,
  `release_date` varchar(10) DEFAULT NULL,
  `title` varchar(255) DEFAULT NULL,
  `fetched_at` datetime NOT NULL,
  PRIMARY KEY (`store`,`album_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'roles',
        """
CREATE TABLE IF NOT EXISTS `roles` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `description` varchar(255) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'rules_artist_evidence',
        """
CREATE TABLE IF NOT EXISTS `rules_artist_evidence` (
  `name` varchar(255) NOT NULL,
  `policy` varchar(16) NOT NULL,
  `titles_hash` char(16) NOT NULL,
  `verdict` enum('approve','unresolved','skipped','incomplete') NOT NULL,
  `rule` varchar(64) DEFAULT NULL,
  `evidence` mediumtext DEFAULT NULL,
  `run_id` int(11) DEFAULT NULL,
  `checked_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `applied_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`name`),
  KEY `verdict` (`verdict`),
  KEY `run_id` (`run_id`),
  KEY `checked_at` (`checked_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    # The scheduled artist evidence run (services/music_manager/artist_auto_approve_worker.py,
    # docs/designs/artist-curation/technical.md "Scheduled evidence run"): one ledger row per round,
    # and per name the last verdict the external evidence gave. A verdict is not a decision -- the
    # decision is rules_artists -- it is what keeps the run from asking the outside world about the
    # same name every night. Keyed by name, like rules_artists.
    (
        'rules_artist_evidence_runs',
        """
CREATE TABLE IF NOT EXISTS `rules_artist_evidence_runs` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `started_at` timestamp NULL DEFAULT current_timestamp(),
  `finished_at` timestamp NULL DEFAULT NULL,
  `dry_run` tinyint(1) NOT NULL DEFAULT 1,
  `new_names` int(11) NOT NULL DEFAULT 0,
  `backlog_names` int(11) NOT NULL DEFAULT 0,
  `approved` int(11) NOT NULL DEFAULT 0,
  `applied` int(11) NOT NULL DEFAULT 0,
  `unresolved` int(11) NOT NULL DEFAULT 0,
  `skipped` int(11) NOT NULL DEFAULT 0,
  `incomplete` int(11) NOT NULL DEFAULT 0,
  `requests` int(11) NOT NULL DEFAULT 0,
  `failed_requests` int(11) NOT NULL DEFAULT 0,
  `stopped_early` tinyint(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `started_at` (`started_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    # The artist names that were already in library_artists when the curation queue was wired to the
    # tagger. The tagger trusts an approved name or one of these that nobody has decided on since;
    # every other library name is pending (services/common/Helpers/TrustedArtistHelper.py). Keyed by
    # name so a library rebuild keeps it.
    (
        'rules_artist_legacy_trust',
        """
CREATE TABLE IF NOT EXISTS `rules_artist_legacy_trust` (
  `name` varchar(255) NOT NULL,
  `trusted_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'rules_artist_proposals',
        """
CREATE TABLE IF NOT EXISTS `rules_artist_proposals` (
  `name` varchar(255) NOT NULL,
  `kind` enum('keep','rewrite','split','reject','unknown') NOT NULL,
  `target` varchar(512) DEFAULT NULL,
  `evidence` text DEFAULT NULL,
  `confidence` int(11) NOT NULL DEFAULT 0,
  `junk_score` int(11) NOT NULL DEFAULT 0,
  `analyzed_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`name`),
  KEY `kind` (`kind`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    # Artist curation (routers/artist_curation.py). `rules_artists` is the human decision -- white
    # keeps the name, black drops it or, with canonical_name, rewrites it -- and is mirrored into
    # rules_ignored_artists, which is what the tagger reads. Keyed by name like the other rule
    # tables: the library id is rebuilt with the library. `rules_artist_proposals` is what the last
    # analysis run suggested for each undecided name; every run rewrites it whole, and a decision
    # never lives here.
    (
        'rules_artists',
        """
CREATE TABLE IF NOT EXISTS `rules_artists` (
  `name` varchar(255) NOT NULL,
  `state` enum('white','black') NOT NULL,
  `canonical_name` varchar(255) DEFAULT NULL,
  `decided_at` timestamp NULL DEFAULT current_timestamp(),
  `decided_by` varchar(64) DEFAULT NULL,
  PRIMARY KEY (`name`),
  KEY `state` (`state`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'rules_catid_label',
        """
CREATE TABLE IF NOT EXISTS `rules_catid_label` (
  `catid` varchar(255) NOT NULL,
  `label` varchar(255) NOT NULL,
  PRIMARY KEY (`catid`),
  UNIQUE KEY `catid` (`catid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'rules_festival_data',
        """
CREATE TABLE IF NOT EXISTS `rules_festival_data` (
  `festival` varchar(255) NOT NULL,
  `year` int(11) NOT NULL,
  `date` date NOT NULL,
  PRIMARY KEY (`festival`,`year`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'rules_festivals',
        """
CREATE TABLE IF NOT EXISTS `rules_festivals` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `normalized_name` varchar(191) NOT NULL,
  `active` tinyint(1) NOT NULL DEFAULT 1,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `normalized_name` (`normalized_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'rules_genre_backlog',
        """
CREATE TABLE IF NOT EXISTS `rules_genre_backlog` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `genre` varchar(255) DEFAULT NULL,
  `detected_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `genre` (`genre`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'rules_genres',
        """
CREATE TABLE IF NOT EXISTS `rules_genres` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `normalized_name` varchar(191) NOT NULL,
  `state` enum('white','black','unknown') NOT NULL DEFAULT 'unknown',
  `canonical_id` int(11) DEFAULT NULL,
  `occurrences` int(11) NOT NULL DEFAULT 0,
  `corrected_genre` varchar(255) DEFAULT NULL,
  `detected_at` timestamp NULL DEFAULT current_timestamp(),
  `decided_at` timestamp NULL DEFAULT NULL,
  `decided_by` varchar(64) DEFAULT NULL,
  `hardness` tinyint(3) unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_rules_genres_normalized_name` (`normalized_name`),
  KEY `idx_rules_genres_state` (`state`),
  KEY `canonical_id` (`canonical_id`),
  CONSTRAINT `fk_rules_genres_canonical` FOREIGN KEY (`canonical_id`) REFERENCES `rules_genres` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'rules_ignored_artists',
        """
CREATE TABLE IF NOT EXISTS `rules_ignored_artists` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `corrected_name` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_ignored_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'rules_ignored_genres',
        """
CREATE TABLE IF NOT EXISTS `rules_ignored_genres` (
  `name` varchar(255) NOT NULL,
  PRIMARY KEY (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'rules_label_name_choices',
        """
CREATE TABLE IF NOT EXISTS `rules_label_name_choices` (
  `nfo_label_key` varchar(191) NOT NULL,
  `nfo_label` varchar(255) NOT NULL,
  `name_folder` varchar(255) NOT NULL,
  `history_folder` varchar(255) NOT NULL,
  `history_count` int(11) NOT NULL DEFAULT 0,
  `name_count` int(11) NOT NULL DEFAULT 0,
  `examples` text DEFAULT NULL,
  `chosen_folder` varchar(255) DEFAULT NULL,
  `decided_at` timestamp NULL DEFAULT NULL,
  `learned_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`nfo_label_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    # Releases the mover could not place, waiting for a human. `folder` is unique so a later import
    # cycle refreshes the row instead of adding a second one, and `catid` is nullable because "no
    # catalogue number in the name at all" is one of the two ways a release ends up here.
    (
        'rules_label_proposals',
        """
CREATE TABLE IF NOT EXISTS `rules_label_proposals` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `folder` varchar(255) NOT NULL,
  `catid` varchar(255) DEFAULT NULL,
  `proposed_label` varchar(255) DEFAULT NULL,
  `source` varchar(64) NOT NULL DEFAULT 'none',
  `confidence` int(11) NOT NULL DEFAULT 0,
  `status` enum('new','confirmed','rejected','stale') NOT NULL DEFAULT 'new',
  `decided_label` varchar(255) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `decided_at` timestamp NULL DEFAULT NULL,
  `resolved_fingerprint` char(64) DEFAULT NULL,
  `alternative_label` varchar(255) DEFAULT NULL,
  `label_choice_key` varchar(191) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `folder` (`folder`),
  KEY `status` (`status`),
  KEY `catid` (`catid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    # Radio shows and podcast series, curated the same way genres are: the detector files what it
    # finds as 'unknown' and only 'white' shows are ever written to a file. `host` and `station` are
    # descriptive; nothing reads them yet, but a station like Toxic Sickness carries dozens of
    # residencies and that is the field which will group them.
    (
        'rules_podcasts',
        """
CREATE TABLE IF NOT EXISTS `rules_podcasts` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `normalized_name` varchar(191) NOT NULL,
  `state` enum('white','black','unknown') NOT NULL DEFAULT 'unknown',
  `host` varchar(255) DEFAULT NULL,
  `station` varchar(255) DEFAULT NULL,
  `occurrences` int(11) NOT NULL DEFAULT 0,
  `detected_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `decided_at` timestamp NULL DEFAULT NULL,
  `decided_by` varchar(64) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `normalized_name` (`normalized_name`),
  KEY `state` (`state`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    # Overrides for scene groups that write M-D-Y instead of the usual D-M-Y. Empty is a valid state:
    # with no row for a group, NfoDate falls back to its positional default.
    (
        'rules_scene_group_date_format',
        """
CREATE TABLE IF NOT EXISTS `rules_scene_group_date_format` (
  `scene_group` varchar(64) NOT NULL,
  `date_format` varchar(8) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`scene_group`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'rules_subgenre_hierarchy',
        """
CREATE TABLE IF NOT EXISTS `rules_subgenre_hierarchy` (
  `subgenre` varchar(255) NOT NULL,
  `genre` varchar(255) NOT NULL,
  PRIMARY KEY (`subgenre`,`genre`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'scrobble_imports',
        """
CREATE TABLE IF NOT EXISTS `scrobble_imports` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `username` varchar(255) NOT NULL,
  `lb_username` varchar(255) NOT NULL,
  `status` varchar(50) NOT NULL,
  `total_found` int(11) DEFAULT 0,
  `processed` int(11) DEFAULT 0,
  `last_error` text DEFAULT NULL,
  `started_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `finished_at` timestamp NULL DEFAULT NULL,
  `oldest_listened_ts` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'scrobble_unmatched_listens',
        """
CREATE TABLE IF NOT EXISTS `scrobble_unmatched_listens` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `artist_name` varchar(512) DEFAULT NULL,
  `track_title` varchar(512) DEFAULT NULL,
  `album_name` varchar(512) DEFAULT NULL,
  `mbid_track` varchar(36) DEFAULT NULL,
  `mbid_artist` varchar(36) DEFAULT NULL,
  `listened_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `username` varchar(255) NOT NULL,
  `source` varchar(50) DEFAULT NULL,
  `data` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`data`)),
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `attempts` int(11) NOT NULL DEFAULT 0,
  `last_attempt_at` timestamp NULL DEFAULT NULL,
  `played_secs` int(10) unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`,`listened_at`,`artist_name`,`track_title`) USING HASH,
  KEY `idx_unmatched_retry` (`last_attempt_at`,`attempts`),
  KEY `idx_unmatched_listened_at` (`listened_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    # The tagger's record of every file it handled. filepath is utf8mb4_bin: the table default folds
    # case and accents and weighs every emoji the same, so two paths that differ only in such a
    # character would share one row. idx_tagger_processed_files_pending lets the pending pass page the
    # queue by (flag, path); the reason is not in the key because filepath already takes 3068 of the
    # 3072 bytes a key may have. attempts and last_attempt drive the retry backoff.
    (
        'tagger_processed_files',
        """
CREATE TABLE IF NOT EXISTS `tagger_processed_files` (
  `filepath` varchar(767) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `mtime` double DEFAULT NULL,
  `last_processed` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `needs_rescan` tinyint(1) DEFAULT 0,
  `rescan_reason` varchar(64) DEFAULT NULL,
  `attempts` int(11) NOT NULL DEFAULT 0,
  `last_attempt` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`filepath`),
  KEY `idx_tagger_processed_files_pending` (`needs_rescan`,`filepath`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'users',
        """
CREATE TABLE IF NOT EXISTS `users` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `username` varchar(255) NOT NULL,
  `email` varchar(255) DEFAULT NULL,
  `display_name` varchar(255) DEFAULT NULL,
  `avatar_url` varchar(1024) DEFAULT NULL,
  `is_admin` tinyint(1) DEFAULT 0,
  `role_id` int(11) DEFAULT NULL,
  `enabled` tinyint(1) DEFAULT 1,
  `password_hash` varchar(255) DEFAULT NULL,
  `api_key` varchar(255) DEFAULT NULL,
  `server_user_id` varchar(255) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `last_login_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    # An account on a platform, which a file arrived through. Kept apart from library_labels because
    # a platform is not a label -- see services/common/channels.py. Platforms stay split, so a
    # SoundCloud channel and a YouTube channel are two rows even when they belong to the same
    # imprint; they converge through label_id rather than by being merged, which keeps "where did
    # this file come from" answerable. label_id and artist_id are independent and both nullable: a
    # channel may be a label, may be an artist, may be both (an artist who runs their own imprint)
    # and may be neither until someone decides.
    (
        'channels',
        """
CREATE TABLE IF NOT EXISTS `channels` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `platform` enum('soundcloud','youtube','telegram') NOT NULL,
  `name` varchar(255) NOT NULL,
  `normalized_name` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `label_id` int(11) DEFAULT NULL,
  `artist_id` int(11) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_channel` (`platform`,`normalized_name`),
  KEY `idx_channel_label` (`label_id`),
  KEY `idx_channel_artist` (`artist_id`),
  CONSTRAINT `channels_ibfk_1` FOREIGN KEY (`label_id`) REFERENCES `library_labels` (`id`) ON DELETE SET NULL,
  CONSTRAINT `channels_ibfk_2` FOREIGN KEY (`artist_id`) REFERENCES `library_artists` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'crash_reports',
        """
CREATE TABLE IF NOT EXISTS `crash_reports` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) DEFAULT NULL,
  `device_model` varchar(255) DEFAULT NULL,
  `os_version` varchar(50) DEFAULT NULL,
  `app_version_name` varchar(50) DEFAULT NULL,
  `app_version_code` int(11) DEFAULT NULL,
  `build_type` varchar(20) DEFAULT NULL,
  `stacktrace_text` longtext DEFAULT NULL,
  `ring_buffer_text` longtext DEFAULT NULL,
  `status` varchar(20) NOT NULL DEFAULT 'new',
  `stacktrace_hash` char(64) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `crash_reports_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'dynamic_playlists',
        """
CREATE TABLE IF NOT EXISTS `dynamic_playlists` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `remote_id` int(11) DEFAULT NULL,
  `source` varchar(50) DEFAULT NULL,
  `name` varchar(255) NOT NULL,
  `params` text NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_source_remote_id` (`source`,`remote_id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `dynamic_playlists_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    # Mirrors artist_external_ids rather than sharing one polymorphic table with it: a table keyed by
    # (entity_type, entity_id) cannot carry a real foreign key, and artist_external_ids is already
    # written to by the image fetcher.
    (
        'label_external_ids',
        """
CREATE TABLE IF NOT EXISTS `label_external_ids` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `label_id` int(11) NOT NULL,
  `source` varchar(50) NOT NULL,
  `external_id` varchar(255) NOT NULL,
  `external_url` text DEFAULT NULL,
  `verified` tinyint(1) NOT NULL DEFAULT 0,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT NULL ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_label_source` (`label_id`,`source`),
  CONSTRAINT `label_external_ids_ibfk_1` FOREIGN KEY (`label_id`) REFERENCES `library_labels` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'library_artist_aliases',
        """
CREATE TABLE IF NOT EXISTS `library_artist_aliases` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `artist_id` int(11) NOT NULL,
  `alias` varchar(255) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `artist_id` (`artist_id`,`alias`),
  CONSTRAINT `library_artist_aliases_ibfk_1` FOREIGN KEY (`artist_id`) REFERENCES `library_artists` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'library_media_files',
        """
CREATE TABLE IF NOT EXISTS `library_media_files` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `file_path` text NOT NULL,
  `file_path_hash` varchar(64) NOT NULL,
  `audio_hash` varchar(64) DEFAULT NULL,
  `duration_secs` float DEFAULT NULL,
  `track_id` int(11) DEFAULT NULL,
  `file_size` bigint(20) DEFAULT NULL,
  `file_mtime` double DEFAULT NULL,
  `last_seen` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `file_path_hash` (`file_path_hash`),
  KEY `track_id` (`track_id`),
  KEY `idx_media_file_path` (`file_path`(255)),
  CONSTRAINT `library_media_files_ibfk_1` FOREIGN KEY (`track_id`) REFERENCES `library_tracks` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'library_track_artists',
        """
CREATE TABLE IF NOT EXISTS `library_track_artists` (
  `track_id` int(11) NOT NULL,
  `artist_id` int(11) NOT NULL,
  `role` enum('primary','featuring','remixer','producer','composer') NOT NULL DEFAULT 'primary',
  `position` int(11) DEFAULT 0,
  PRIMARY KEY (`track_id`,`artist_id`,`role`),
  KEY `artist_id` (`artist_id`),
  CONSTRAINT `library_track_artists_ibfk_1` FOREIGN KEY (`track_id`) REFERENCES `library_tracks` (`id`) ON DELETE CASCADE,
  CONSTRAINT `library_track_artists_ibfk_2` FOREIGN KEY (`artist_id`) REFERENCES `library_artists` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'library_track_audio_features',
        """
CREATE TABLE IF NOT EXISTS `library_track_audio_features` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `track_id` varchar(255) NOT NULL,
  `tempo` float DEFAULT NULL,
  `duration` float DEFAULT NULL,
  `mean_spectral_centroid` float DEFAULT NULL,
  `mean_spectral_rolloff` float DEFAULT NULL,
  `mean_rms` float DEFAULT NULL,
  `mean_zcr` float DEFAULT NULL,
  `mfcc_1` float DEFAULT NULL,
  `mfcc_2` float DEFAULT NULL,
  `mfcc_3` float DEFAULT NULL,
  `mfcc_4` float DEFAULT NULL,
  `mfcc_5` float DEFAULT NULL,
  `mean_chroma` float DEFAULT NULL,
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `internal_track_id` int(11) DEFAULT NULL,
  `file_path` text DEFAULT NULL,
  `artist_name` varchar(255) DEFAULT NULL,
  `label_name` varchar(255) DEFAULT NULL,
  `release_year` int(11) DEFAULT NULL,
  `source_platform` varchar(50) DEFAULT NULL,
  `bpm_tag` float DEFAULT NULL,
  `genre_tag` varchar(100) DEFAULT NULL,
  `std_spectral_centroid` float DEFAULT NULL,
  `mean_spectral_bandwidth` float DEFAULT NULL,
  `std_spectral_bandwidth` float DEFAULT NULL,
  `std_spectral_rolloff` float DEFAULT NULL,
  `std_rms` float DEFAULT NULL,
  `std_zcr` float DEFAULT NULL,
  `mean_spectral_contrast` float DEFAULT NULL,
  `std_spectral_contrast` float DEFAULT NULL,
  `mfcc_6` float DEFAULT NULL,
  `mfcc_7` float DEFAULT NULL,
  `mfcc_8` float DEFAULT NULL,
  `mfcc_9` float DEFAULT NULL,
  `mfcc_10` float DEFAULT NULL,
  `mfcc_11` float DEFAULT NULL,
  `mfcc_12` float DEFAULT NULL,
  `mfcc_13` float DEFAULT NULL,
  `std_mfcc_1` float DEFAULT NULL,
  `std_mfcc_2` float DEFAULT NULL,
  `std_mfcc_3` float DEFAULT NULL,
  `std_mfcc_4` float DEFAULT NULL,
  `std_mfcc_5` float DEFAULT NULL,
  `std_mfcc_6` float DEFAULT NULL,
  `std_mfcc_7` float DEFAULT NULL,
  `std_mfcc_8` float DEFAULT NULL,
  `std_mfcc_9` float DEFAULT NULL,
  `std_mfcc_10` float DEFAULT NULL,
  `std_mfcc_11` float DEFAULT NULL,
  `std_mfcc_12` float DEFAULT NULL,
  `std_mfcc_13` float DEFAULT NULL,
  `std_chroma` float DEFAULT NULL,
  `release_date` varchar(10) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `track_id` (`track_id`),
  KEY `idx_af_file_path` (`file_path`(255)),
  KEY `idx_af_internal_track_id` (`internal_track_id`),
  CONSTRAINT `fk_audio_features_internal_track_id` FOREIGN KEY (`internal_track_id`) REFERENCES `library_tracks` (`id`) ON DELETE SET NULL,
  CONSTRAINT `library_track_audio_features_ibfk_1` FOREIGN KEY (`internal_track_id`) REFERENCES `library_tracks` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'library_track_effective_bpm',
        """
CREATE TABLE IF NOT EXISTS `library_track_effective_bpm` (
  `track_id` int(11) NOT NULL,
  `bpm` decimal(5,2) NOT NULL,
  `source` enum('measured','tag','analyzer','manual') NOT NULL,
  `confidence` enum('low','medium','high') NOT NULL,
  `approximate` tinyint(1) NOT NULL DEFAULT 0,
  `folded` tinyint(1) NOT NULL DEFAULT 0,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`track_id`),
  KEY `idx_effective_bpm_bpm` (`bpm`),
  CONSTRAINT `1` FOREIGN KEY (`track_id`) REFERENCES `library_tracks` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'library_track_genres',
        """
CREATE TABLE IF NOT EXISTS `library_track_genres` (
  `track_id` int(11) NOT NULL,
  `genre_id` int(11) NOT NULL,
  `weight` float DEFAULT 1,
  PRIMARY KEY (`track_id`,`genre_id`),
  KEY `idx_genre_id` (`genre_id`),
  CONSTRAINT `library_track_genres_ibfk_1` FOREIGN KEY (`track_id`) REFERENCES `library_tracks` (`id`) ON DELETE CASCADE,
  CONSTRAINT `library_track_genres_ibfk_2` FOREIGN KEY (`genre_id`) REFERENCES `rules_genres` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'library_track_labels',
        """
CREATE TABLE IF NOT EXISTS `library_track_labels` (
  `track_id` int(11) NOT NULL,
  `label_id` int(11) NOT NULL,
  PRIMARY KEY (`track_id`,`label_id`),
  KEY `idx_label_id` (`label_id`),
  CONSTRAINT `library_track_labels_ibfk_1` FOREIGN KEY (`track_id`) REFERENCES `library_tracks` (`id`) ON DELETE CASCADE,
  CONSTRAINT `library_track_labels_ibfk_2` FOREIGN KEY (`label_id`) REFERENCES `library_labels` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'library_track_ml_labels',
        """
CREATE TABLE IF NOT EXISTS `library_track_ml_labels` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `track_id` varchar(255) NOT NULL,
  `ml_genre` varchar(100) DEFAULT NULL,
  `ml_review_status` enum('unreviewed','human_verified','borderline','do_not_train') DEFAULT 'unreviewed',
  `approved_for_training` tinyint(1) DEFAULT 0,
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `internal_track_id` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `track_id` (`track_id`),
  KEY `fk_ml_labels_internal_track_id` (`internal_track_id`),
  CONSTRAINT `fk_ml_labels_internal_track_id` FOREIGN KEY (`internal_track_id`) REFERENCES `library_tracks` (`id`) ON DELETE SET NULL,
  CONSTRAINT `library_track_ml_labels_ibfk_1` FOREIGN KEY (`internal_track_id`) REFERENCES `library_tracks` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'role_permissions',
        """
CREATE TABLE IF NOT EXISTS `role_permissions` (
  `role_id` int(11) NOT NULL,
  `permission_id` int(11) NOT NULL,
  PRIMARY KEY (`role_id`,`permission_id`),
  KEY `permission_id` (`permission_id`),
  CONSTRAINT `role_permissions_ibfk_1` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`) ON DELETE CASCADE,
  CONSTRAINT `role_permissions_ibfk_2` FOREIGN KEY (`permission_id`) REFERENCES `permissions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'rules_artist_genres',
        """
CREATE TABLE IF NOT EXISTS `rules_artist_genres` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `artist_name` varchar(255) NOT NULL,
  `genre_id` int(11) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `created_by` varchar(64) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `artist_name` (`artist_name`,`genre_id`),
  KEY `genre_id` (`genre_id`),
  CONSTRAINT `rules_artist_genres_ibfk_1` FOREIGN KEY (`genre_id`) REFERENCES `rules_genres` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'rules_festival_aliases',
        """
CREATE TABLE IF NOT EXISTS `rules_festival_aliases` (
  `festival_id` int(11) NOT NULL,
  `alias` varchar(255) NOT NULL,
  `normalized_alias` varchar(191) NOT NULL,
  PRIMARY KEY (`festival_id`,`normalized_alias`),
  KEY `idx_normalized_alias` (`normalized_alias`),
  CONSTRAINT `rules_festival_aliases_ibfk_1` FOREIGN KEY (`festival_id`) REFERENCES `rules_festivals` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'rules_festival_editions',
        """
CREATE TABLE IF NOT EXISTS `rules_festival_editions` (
  `festival_id` int(11) NOT NULL,
  `year` int(11) NOT NULL,
  `date` date NOT NULL,
  PRIMARY KEY (`festival_id`,`year`),
  CONSTRAINT `rules_festival_editions_ibfk_1` FOREIGN KEY (`festival_id`) REFERENCES `rules_festivals` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'rules_genre_expansions',
        """
CREATE TABLE IF NOT EXISTS `rules_genre_expansions` (
  `genre_id` int(11) NOT NULL,
  `target_id` int(11) NOT NULL,
  `position` int(11) NOT NULL DEFAULT 0,
  PRIMARY KEY (`genre_id`,`target_id`),
  KEY `idx_rules_genre_expansions_target` (`target_id`),
  CONSTRAINT `rules_genre_expansions_ibfk_1` FOREIGN KEY (`genre_id`) REFERENCES `rules_genres` (`id`) ON DELETE CASCADE,
  CONSTRAINT `rules_genre_expansions_ibfk_2` FOREIGN KEY (`target_id`) REFERENCES `rules_genres` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    # Genre curation advice (routers/genre_curation.py): what the last analysis run proposed for each
    # queued genre. Rewritten whole on every run; the decision itself is the state on rules_genres
    # plus rules_genre_expansions, never this. Targets are stored as JSON `[{id, name}]` so the page
    # can post the decision without a second lookup.
    (
        'rules_genre_proposals',
        """
CREATE TABLE IF NOT EXISTS `rules_genre_proposals` (
  `genre_id` int(11) NOT NULL,
  `kind` enum('keep','rewrite','split','reject','unknown') NOT NULL,
  `targets` text DEFAULT NULL,
  `evidence` text DEFAULT NULL,
  `confidence` int(11) NOT NULL DEFAULT 0,
  `analyzed_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`genre_id`),
  KEY `kind` (`kind`),
  CONSTRAINT `1` FOREIGN KEY (`genre_id`) REFERENCES `rules_genres` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'rules_label_genres',
        """
CREATE TABLE IF NOT EXISTS `rules_label_genres` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `label_name` varchar(255) NOT NULL,
  `genre_id` int(11) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `created_by` varchar(64) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `label_name` (`label_name`,`genre_id`),
  KEY `genre_id` (`genre_id`),
  CONSTRAINT `rules_label_genres_ibfk_1` FOREIGN KEY (`genre_id`) REFERENCES `rules_genres` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'rules_podcast_aliases',
        """
CREATE TABLE IF NOT EXISTS `rules_podcast_aliases` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `podcast_id` int(11) NOT NULL,
  `alias` varchar(255) NOT NULL,
  `normalized_alias` varchar(191) NOT NULL,
  `occurrences` int(11) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `normalized_alias` (`normalized_alias`),
  KEY `podcast_id` (`podcast_id`),
  CONSTRAINT `rules_podcast_aliases_ibfk_1` FOREIGN KEY (`podcast_id`) REFERENCES `rules_podcasts` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    # One play. listened_at has an explicit DEFAULT and no ON UPDATE: without the DEFAULT, a server
    # with explicit_defaults_for_timestamp=OFF gives the first TIMESTAMP column ON UPDATE as well, and
    # every UPDATE of the row moves the listen to now (bug report 039). track_id is SET NULL when the
    # track row goes, so a library rebuild never deletes listening history.
    (
        'scrobble_listens',
        """
CREATE TABLE IF NOT EXISTS `scrobble_listens` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `track_id` int(11) DEFAULT NULL,
  `listened_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `username` varchar(255) NOT NULL,
  `source` varchar(50) DEFAULT NULL,
  `mbid_track` varchar(36) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `match_method` enum('exact','normalized','base_title','fuzzy') NOT NULL DEFAULT 'exact',
  `match_score` tinyint(3) unsigned DEFAULT NULL,
  `played_secs` int(10) unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`,`listened_at`,`track_id`),
  KEY `track_id` (`track_id`),
  KEY `idx_listens_match_method` (`match_method`),
  KEY `idx_listens_listened_at` (`listened_at`),
  KEY `idx_listens_track_user` (`track_id`,`username`),
  CONSTRAINT `scrobble_listens_ibfk_1` FOREIGN KEY (`track_id`) REFERENCES `library_tracks` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'user_app_settings',
        """
CREATE TABLE IF NOT EXISTS `user_app_settings` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `app_id` varchar(50) NOT NULL,
  `settings_json` longtext NOT NULL,
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_id` (`user_id`,`app_id`),
  CONSTRAINT `user_app_settings_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'user_identities',
        """
CREATE TABLE IF NOT EXISTS `user_identities` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `provider` varchar(50) NOT NULL,
  `provider_subject` varchar(255) NOT NULL,
  `email_at_provider` varchar(255) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_used_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_provider_subject` (`provider`,`provider_subject`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `user_identities_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'user_listenbrainz_accounts',
        """
CREATE TABLE IF NOT EXISTS `user_listenbrainz_accounts` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `lb_username` varchar(255) NOT NULL,
  `lb_token` varchar(255) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_id` (`user_id`),
  CONSTRAINT `user_listenbrainz_accounts_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'user_refresh_tokens',
        """
CREATE TABLE IF NOT EXISTS `user_refresh_tokens` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `token` varchar(255) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `last_used_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `revoked_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `token` (`token`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `user_refresh_tokens_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'user_requests',
        """
CREATE TABLE IF NOT EXISTS `user_requests` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `google_subject` varchar(255) NOT NULL,
  `email` varchar(255) DEFAULT NULL,
  `display_name` varchar(255) DEFAULT NULL,
  `avatar_url` varchar(1024) DEFAULT NULL,
  `status` varchar(20) NOT NULL DEFAULT 'pending',
  `requested_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `reviewed_at` timestamp NULL DEFAULT NULL,
  `reviewed_by_user_id` int(11) DEFAULT NULL,
  `created_user_id` int(11) DEFAULT NULL,
  `linked_existing` tinyint(1) DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `google_subject` (`google_subject`),
  KEY `reviewed_by_user_id` (`reviewed_by_user_id`),
  KEY `created_user_id` (`created_user_id`),
  CONSTRAINT `user_requests_ibfk_1` FOREIGN KEY (`reviewed_by_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `user_requests_ibfk_2` FOREIGN KEY (`created_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    # One row per proposed (channel, kind, target), whatever its status: the unique key is what keeps
    # a rejected proposal rejected when the search runs again. target_id points into library_labels
    # or library_artists depending on kind, so it carries no foreign key. See
    # docs/designs/channel-links/technical.md.
    (
        'channel_link_proposals',
        """
CREATE TABLE IF NOT EXISTS `channel_link_proposals` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `channel_id` int(11) NOT NULL,
  `kind` enum('label','artist') NOT NULL,
  `target_id` int(11) NOT NULL,
  `target_name` varchar(255) NOT NULL,
  `source` enum('name','alias','redirect','manual') NOT NULL,
  `status` enum('new','confirmed','rejected','stale') NOT NULL DEFAULT 'new',
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `decided_at` timestamp NULL DEFAULT NULL,
  `decided_by` varchar(64) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_channel_link` (`channel_id`,`kind`,`target_id`),
  KEY `idx_channel_link_status` (`status`),
  CONSTRAINT `1` FOREIGN KEY (`channel_id`) REFERENCES `channels` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
    (
        'library_track_channels',
        """
CREATE TABLE IF NOT EXISTS `library_track_channels` (
  `track_id` int(11) NOT NULL,
  `channel_id` int(11) NOT NULL,
  PRIMARY KEY (`track_id`,`channel_id`),
  KEY `idx_track_channel_channel` (`channel_id`),
  CONSTRAINT `library_track_channels_ibfk_1` FOREIGN KEY (`track_id`) REFERENCES `library_tracks` (`id`) ON DELETE CASCADE,
  CONSTRAINT `library_track_channels_ibfk_2` FOREIGN KEY (`channel_id`) REFERENCES `channels` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    ),
)

# (view name, CREATE VIEW statement). Views read the tables above, so they come last.
VIEWS: tuple[tuple[str, str], ...] = (
    (
        'rules_artist_genre',
        'CREATE VIEW IF NOT EXISTS rules_artist_genre AS '
        'SELECT r.artist_name AS artist, g.name AS genre '
        'FROM rules_artist_genres r JOIN rules_genres g ON r.genre_id = g.id',
    ),
    (
        'rules_label_genre',
        'CREATE VIEW IF NOT EXISTS rules_label_genre AS '
        'SELECT r.label_name AS label, g.name AS genre '
        'FROM rules_label_genres r JOIN rules_genres g ON r.genre_id = g.id',
    ),
)
