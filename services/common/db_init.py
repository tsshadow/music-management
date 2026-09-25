import logging

from services.common.Helpers.DatabaseConnector import DatabaseConnector

REQUIRED_TABLES = [
    'downloads_soundcloud_accounts',
    'downloads_soundcloud_archive',
    'downloads_youtube_accounts',
    'downloads_youtube_archive',
    'library_artists',
    # Read and written by routers/curation.py. Only migrate_v2 created it, so a fresh
    # stack had no such table and the artist edit page 500ed there (bug report 047).
    'library_artist_aliases',
    'library_labels',
    'label_external_ids',
    'library_tracks',
    'library_media_files',
    'library_works',
    'library_track_artists',
    'library_track_labels',
    # channels points at library_labels and library_artists, and library_track_channels points at
    # both channels and library_tracks, so all three have to exist first.
    'channels',
    'library_track_channels',
    # rules_genres must precede library_track_genres: the latter carries a foreign
    # key to it, and MariaDB rejects a CREATE naming a table that does not exist
    # yet. The failure was swallowed by the debug-level except below, so on a fresh
    # database library_track_genres was silently never created.
    'rules_genres',
    'library_track_genres',
    'rules_artist_genres',
    'rules_label_genres',
    'rules_artist_genre',
    'rules_label_genre',
    'rules_catid_label',
    'rules_label_proposals',
    'rules_festival_data',
    # rules_festivals must precede its two children: both carry a foreign key to it.
    'rules_festivals',
    'rules_festival_aliases',
    'rules_festival_editions',
    'rules_ignored_artists',
    'rules_artists',
    'rules_artist_proposals',
    'rules_artist_legacy_trust',
    'rules_ignored_genres',
    'rules_subgenre_hierarchy',
    'rules_genre_backlog',
    'rules_genre_expansions',
    'rules_genre_proposals',
    'rules_scene_group_date_format',
    # Same ordering constraint as rules_genres above: the alias table points at
    # rules_podcasts.
    'rules_podcasts',
    'rules_podcast_aliases',
    'library_track_audio_features',
    'library_track_ml_labels',
    'library_ingestion_records',
    # The deploy's migration ledger: which migrate_*.sql applied, with the sha256 of its
    # content (tools/apply_migrations.py, bug report 068).
    'schema_migrations',
]


def ensure_tables_exist() -> None:
    """Ensure required database tables exist."""
    table_queries = {
        'downloads_soundcloud_accounts': '\n            CREATE TABLE IF NOT EXISTS downloads_soundcloud_accounts (\n                name VARCHAR(255),\n                soundcloud_id VARCHAR(255),\n                PRIMARY KEY (name)\n            )\n        ',
        'downloads_soundcloud_archive': '\n            CREATE TABLE IF NOT EXISTS downloads_soundcloud_archive (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                account VARCHAR(255),\n                video_id VARCHAR(255),\n                filename TEXT,\n                url TEXT,\n                title TEXT,\n                added_at DATETIME DEFAULT CURRENT_TIMESTAMP,\n                INDEX(account),\n                INDEX(video_id)\n            )\n        ',
        'downloads_youtube_accounts': '\n            CREATE TABLE IF NOT EXISTS downloads_youtube_accounts (\n                name VARCHAR(255) PRIMARY KEY\n            )\n        ',
        'downloads_youtube_archive': '\n            CREATE TABLE IF NOT EXISTS downloads_youtube_archive (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                account VARCHAR(255),\n                video_id VARCHAR(255),\n                filename TEXT,\n                url TEXT,\n                title TEXT,\n                added_at DATETIME DEFAULT CURRENT_TIMESTAMP,\n                INDEX(account),\n                INDEX(video_id)\n            )\n        ',
        'library_artists': '\n            CREATE TABLE IF NOT EXISTS library_artists (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                name VARCHAR(255) NOT NULL UNIQUE,\n                normalized_name VARCHAR(191),\n                INDEX idx_artists_normalized_name (normalized_name),\n                sort_name VARCHAR(255),\n                mbid VARCHAR(36),\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n            )\n        ',
        'library_artist_aliases': '\n            CREATE TABLE IF NOT EXISTS library_artist_aliases (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                artist_id INT NOT NULL,\n                alias VARCHAR(255) NOT NULL,\n                UNIQUE KEY (artist_id, alias),\n                FOREIGN KEY (artist_id) REFERENCES library_artists(id) ON DELETE CASCADE\n            )\n        ',
        # Index and constraint names below are the ones the migrations gave production.
        # Left unnamed, MariaDB names an index after its column, so a fresh stack and a
        # migrated one disagreed about every one of them (tests/integration/test_schema_drift.py).
        'library_labels': '\n            CREATE TABLE IF NOT EXISTS library_labels (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                name VARCHAR(255) NOT NULL UNIQUE,\n                mbid VARCHAR(36) NULL,\n                parent_label_id INT NULL,\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                CONSTRAINT fk_labels_parent FOREIGN KEY (parent_label_id) REFERENCES library_labels(id) ON DELETE SET NULL\n            )\n        ',
        # Mirrors artist_external_ids rather than sharing one polymorphic table with it:
        # a table keyed by (entity_type, entity_id) cannot carry a real foreign key, and
        # artist_external_ids is already written to by the image fetcher.
        'label_external_ids': '\n            CREATE TABLE IF NOT EXISTS label_external_ids (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                label_id INT NOT NULL,\n                source VARCHAR(50) NOT NULL,\n                external_id VARCHAR(255) NOT NULL,\n                external_url TEXT NULL,\n                verified TINYINT(1) NOT NULL DEFAULT 0,\n                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,\n                updated_at DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,\n                UNIQUE KEY uq_label_source (label_id, source),\n                FOREIGN KEY (label_id) REFERENCES library_labels(id) ON DELETE CASCADE\n            )\n        ',
        'library_tracks': '\n            CREATE TABLE IF NOT EXISTS library_tracks (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                track_uid VARCHAR(255) UNIQUE,\n                title VARCHAR(512),\n                normalized_title VARCHAR(191),\n                normalized_base_title VARCHAR(191),\n                INDEX idx_tracks_normalized_title (normalized_title),\n                INDEX idx_tracks_normalized_base_title (normalized_base_title),\n                work_id INT NULL,\n                INDEX idx_tracks_work_id (work_id),\n                version_kind VARCHAR(32) NULL,\n                version_score INT NULL,\n                work_locked TINYINT NOT NULL DEFAULT 0,\n                duration_secs FLOAT,\n                primary_artist_id INT,\n                INDEX idx_tracks_primary_artist (primary_artist_id),\n                display_artist VARCHAR(512) NULL,\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n            )\n        ',
        'library_works': '\n            CREATE TABLE IF NOT EXISTS library_works (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                -- utf8mb4_bin, not the table default: utf8mb4_general_ci gives every character\n                -- outside the BMP the same weight, so two keys built from such characters compare\n                -- equal at equal length and the UNIQUE key merges two unrelated songs into one\n                -- work. The key is already normalized in Python, so binary equality is the\n                -- question actually asked. See migrate_v19_work_key_binary.sql.\n                work_key VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin UNIQUE NOT NULL,\n                title VARCHAR(512),\n                primary_artist_id INT,\n                canonical_track_id INT NULL,\n                pinned_track_id INT NULL,\n                related_work_id INT NULL,\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n            )\n        ',
        'library_media_files': '\n            CREATE TABLE IF NOT EXISTS library_media_files (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                file_path TEXT NOT NULL,\n                file_path_hash VARCHAR(64) UNIQUE NOT NULL,\n                audio_hash VARCHAR(64),\n                duration_secs FLOAT,\n                track_id INT,\n                file_size BIGINT,\n                file_mtime DOUBLE,\n                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,\n                INDEX idx_media_file_path (file_path(255)),\n                FOREIGN KEY (track_id) REFERENCES library_tracks(id) ON DELETE SET NULL\n            )\n        ',
        'library_track_artists': '\n            CREATE TABLE IF NOT EXISTS library_track_artists (\n                track_id INT NOT NULL,\n                artist_id INT NOT NULL,\n                role ENUM(\'primary\', \'featuring\', \'remixer\', \'producer\', \'composer\') DEFAULT \'primary\',\n                position INT DEFAULT 0,\n                PRIMARY KEY (track_id, artist_id, role),\n                FOREIGN KEY (track_id) REFERENCES library_tracks(id) ON DELETE CASCADE,\n                FOREIGN KEY (artist_id) REFERENCES library_artists(id) ON DELETE CASCADE\n            )\n        ',
        'library_track_genres': '\n            CREATE TABLE IF NOT EXISTS library_track_genres (\n                track_id INT NOT NULL,\n                genre_id INT NOT NULL,\n                weight FLOAT DEFAULT 1.0,\n                PRIMARY KEY (track_id, genre_id),\n                INDEX idx_genre_id (genre_id),\n                FOREIGN KEY (track_id) REFERENCES library_tracks(id) ON DELETE CASCADE,\n                FOREIGN KEY (genre_id) REFERENCES rules_genres(id) ON DELETE CASCADE\n            )\n        ',
        'library_track_labels': '\n            CREATE TABLE IF NOT EXISTS library_track_labels (\n                track_id INT NOT NULL,\n                label_id INT NOT NULL,\n                PRIMARY KEY (track_id, label_id),\n                FOREIGN KEY (track_id) REFERENCES library_tracks(id) ON DELETE CASCADE,\n                FOREIGN KEY (label_id) REFERENCES library_labels(id) ON DELETE CASCADE\n            )\n        ',
        # An account on a platform, which a file arrived through. Kept apart from library_labels
        # because a platform is not a label -- see services/common/channels.py. Platforms stay
        # split, so a SoundCloud channel and a YouTube channel are two rows even when they belong
        # to the same imprint; they converge through label_id rather than by being merged, which
        # keeps "where did this file come from" answerable. label_id and artist_id are independent
        # and both nullable: a channel may be a label, may be an artist, may be both (an artist who
        # runs their own imprint) and may be neither until someone decides.
        'channels': "\n            CREATE TABLE IF NOT EXISTS channels (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                platform ENUM('soundcloud', 'youtube', 'telegram') NOT NULL,\n                name VARCHAR(255) NOT NULL,\n                -- utf8mb4_bin, not the table default: utf8mb4_general_ci gives every\n                -- character outside the BMP the same weight, so two channel names made of\n                -- mathematical alphanumeric symbols compare equal whenever they are the same\n                -- length. The value is already lowercased in Python, so case folding by the\n                -- database buys nothing and binary equality is the question actually asked.\n                normalized_name VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,\n                label_id INT NULL,\n                artist_id INT NULL,\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                UNIQUE KEY uq_channel (platform, normalized_name),\n                INDEX idx_channel_label (label_id),\n                INDEX idx_channel_artist (artist_id),\n                FOREIGN KEY (label_id) REFERENCES library_labels(id) ON DELETE SET NULL,\n                FOREIGN KEY (artist_id) REFERENCES library_artists(id) ON DELETE SET NULL\n            )\n        ",
        'library_track_channels': '\n            CREATE TABLE IF NOT EXISTS library_track_channels (\n                track_id INT NOT NULL,\n                channel_id INT NOT NULL,\n                PRIMARY KEY (track_id, channel_id),\n                INDEX idx_track_channel_channel (channel_id),\n                FOREIGN KEY (track_id) REFERENCES library_tracks(id) ON DELETE CASCADE,\n                FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE\n            )\n        ',
        'rules_artist_genre': '\n            CREATE VIEW IF NOT EXISTS rules_artist_genre AS\n            SELECT r.artist_name AS artist, g.name AS genre\n            FROM rules_artist_genres r\n            JOIN rules_genres g ON r.genre_id = g.id\n        ',
        'rules_catid_label': '\n            CREATE TABLE IF NOT EXISTS rules_catid_label (\n                catid VARCHAR(255) PRIMARY KEY,\n                label VARCHAR(255) NOT NULL\n            )\n        ',
        # Releases the mover could not place, waiting for a human. `folder` is unique so
        # a later import cycle refreshes the row instead of adding a second one, and
        # `catid` is nullable because "no catalogue number in the name at all" is one of
        # the two ways a release ends up here.
        'rules_label_proposals': "\n            CREATE TABLE IF NOT EXISTS rules_label_proposals (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                folder VARCHAR(255) NOT NULL UNIQUE,\n                catid VARCHAR(255) NULL,\n                proposed_label VARCHAR(255) NULL,\n                source VARCHAR(64) NOT NULL DEFAULT 'none',\n                confidence INT NOT NULL DEFAULT 0,\n                status ENUM('new', 'confirmed', 'rejected', 'stale') NOT NULL DEFAULT 'new',\n                decided_label VARCHAR(255) NULL,\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                decided_at TIMESTAMP NULL,\n                resolved_fingerprint CHAR(64) NULL,\n                INDEX(status),\n                INDEX(catid)\n            )\n        ",
        'rules_festival_data': '\n            CREATE TABLE IF NOT EXISTS rules_festival_data (\n                festival VARCHAR(255) NOT NULL,\n                year INT NOT NULL,\n                date DATE NOT NULL,\n                PRIMARY KEY (festival, year)\n            )\n        ',
        'rules_festivals': '\n            CREATE TABLE IF NOT EXISTS rules_festivals (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                name VARCHAR(255) NOT NULL,\n                normalized_name VARCHAR(191) NOT NULL UNIQUE,\n                active TINYINT(1) NOT NULL DEFAULT 1,\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n            )\n        ',
        'rules_festival_aliases': '\n            CREATE TABLE IF NOT EXISTS rules_festival_aliases (\n                festival_id INT NOT NULL,\n                alias VARCHAR(255) NOT NULL,\n                normalized_alias VARCHAR(191) NOT NULL,\n                PRIMARY KEY (festival_id, normalized_alias),\n                INDEX idx_normalized_alias (normalized_alias),\n                FOREIGN KEY (festival_id) REFERENCES rules_festivals(id) ON DELETE CASCADE\n            )\n        ',
        'rules_festival_editions': '\n            CREATE TABLE IF NOT EXISTS rules_festival_editions (\n                festival_id INT NOT NULL,\n                year INT NOT NULL,\n                date DATE NOT NULL,\n                PRIMARY KEY (festival_id, year),\n                FOREIGN KEY (festival_id) REFERENCES rules_festivals(id) ON DELETE CASCADE\n            )\n        ',
        'rules_genres': "\n            CREATE TABLE IF NOT EXISTS rules_genres (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                name VARCHAR(255) NOT NULL,\n                normalized_name VARCHAR(191) NOT NULL,\n                state ENUM('white', 'black', 'unknown') NOT NULL DEFAULT 'unknown',\n                canonical_id INT NULL,\n                occurrences INT NOT NULL DEFAULT 0,\n                corrected_genre VARCHAR(255),\n                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                decided_at TIMESTAMP NULL,\n                decided_by VARCHAR(64),\n                UNIQUE KEY uq_rules_genres_normalized_name (normalized_name),\n                INDEX idx_rules_genres_state (state),\n                FOREIGN KEY (canonical_id) REFERENCES rules_genres(id) ON DELETE SET NULL\n            )\n        ",
        'rules_ignored_artists': '\n            CREATE TABLE IF NOT EXISTS rules_ignored_artists (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                name VARCHAR(255) NOT NULL,\n                corrected_name VARCHAR(255),\n                UNIQUE KEY name (name)\n            )\n        ',
        # Artist curation (routers/artist_curation.py). `rules_artists` is the human
        # decision -- white keeps the name, black drops it or, with canonical_name,
        # rewrites it -- and is mirrored into rules_ignored_artists, which is what the
        # tagger reads. Keyed by name like the other rule tables: the library id is
        # rebuilt with the library. `rules_artist_proposals` is what the last analysis
        # run suggested for each undecided name; every run rewrites it whole, and a
        # decision never lives here.
        'rules_artists': "\n            CREATE TABLE IF NOT EXISTS rules_artists (\n                name VARCHAR(255) NOT NULL PRIMARY KEY,\n                state ENUM('white', 'black') NOT NULL,\n                canonical_name VARCHAR(255) NULL,\n                decided_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                decided_by VARCHAR(64) NULL,\n                INDEX(state)\n            )\n        ",
        'rules_artist_proposals': "\n            CREATE TABLE IF NOT EXISTS rules_artist_proposals (\n                name VARCHAR(255) NOT NULL PRIMARY KEY,\n                kind ENUM('keep', 'rewrite', 'split', 'reject', 'unknown') NOT NULL,\n                target VARCHAR(512) NULL,\n                evidence TEXT NULL,\n                confidence INT NOT NULL DEFAULT 0,\n                junk_score INT NOT NULL DEFAULT 0,\n                analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                INDEX(kind)\n            )\n        ",
        # The artist names that were already in library_artists when the curation queue
        # was wired to the tagger (migrate_v40). The tagger trusts an approved name or one
        # of these that nobody has decided on since; every other library name is pending
        # (services/common/Helpers/TrustedArtistHelper.py). Keyed by name so a library
        # rebuild keeps it.
        'rules_artist_legacy_trust': "\n            CREATE TABLE IF NOT EXISTS rules_artist_legacy_trust (\n                name VARCHAR(255) NOT NULL PRIMARY KEY,\n                trusted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n            )\n        ",
        'rules_ignored_genres': '\n            CREATE TABLE IF NOT EXISTS rules_ignored_genres (\n                name VARCHAR(255) PRIMARY KEY\n            )\n        ',
        # Genre curation advice (routers/genre_curation.py): what the last analysis run
        # proposed for each queued genre. Rewritten whole on every run; the decision
        # itself is the state on rules_genres plus rules_genre_expansions, never this.
        # Targets are stored as JSON `[{id, name}]` so the page can post the decision
        # without a second lookup.
        'rules_genre_proposals': "\n            CREATE TABLE IF NOT EXISTS rules_genre_proposals (\n                genre_id INT NOT NULL PRIMARY KEY,\n                kind ENUM('keep', 'rewrite', 'split', 'reject', 'unknown') NOT NULL,\n                targets TEXT NULL,\n                evidence TEXT NULL,\n                confidence INT NOT NULL DEFAULT 0,\n                analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                INDEX(kind),\n                FOREIGN KEY (genre_id) REFERENCES rules_genres(id) ON DELETE CASCADE\n            )\n        ",
        'rules_label_genre': '\n            CREATE VIEW IF NOT EXISTS rules_label_genre AS\n            SELECT r.label_name AS label, g.name AS genre\n            FROM rules_label_genres r\n            JOIN rules_genres g ON r.genre_id = g.id\n        ',
        'rules_subgenre_hierarchy': '\n            CREATE TABLE IF NOT EXISTS rules_subgenre_hierarchy (\n                subgenre VARCHAR(255) NOT NULL,\n                genre VARCHAR(255) NOT NULL,\n                PRIMARY KEY (subgenre, genre)\n            )\n        ',
        'rules_genre_backlog': '\n            CREATE TABLE IF NOT EXISTS rules_genre_backlog (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                genre VARCHAR(255) UNIQUE,\n                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n            )\n        ',
        'rules_artist_genres': '\n            CREATE TABLE IF NOT EXISTS rules_artist_genres (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                artist_name VARCHAR(255) NOT NULL,\n                genre_id INT NOT NULL,\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                created_by VARCHAR(64) NULL,\n                FOREIGN KEY (genre_id) REFERENCES rules_genres(id) ON DELETE CASCADE,\n                UNIQUE KEY (artist_name, genre_id)\n            )\n        ',
        'rules_label_genres': '\n            CREATE TABLE IF NOT EXISTS rules_label_genres (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                label_name VARCHAR(255) NOT NULL,\n                genre_id INT NOT NULL,\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                created_by VARCHAR(64) NULL,\n                FOREIGN KEY (genre_id) REFERENCES rules_genres(id) ON DELETE CASCADE,\n                UNIQUE KEY (label_name, genre_id)\n            )\n        ',
        'rules_genre_expansions': '\n            CREATE TABLE IF NOT EXISTS rules_genre_expansions (\n                genre_id INT NOT NULL,\n                target_id INT NOT NULL,\n                position INT NOT NULL DEFAULT 0,\n                PRIMARY KEY (genre_id, target_id),\n                KEY idx_rules_genre_expansions_target (target_id),\n                FOREIGN KEY (genre_id) REFERENCES rules_genres(id) ON DELETE CASCADE,\n                FOREIGN KEY (target_id) REFERENCES rules_genres(id) ON DELETE CASCADE\n            )\n        ',
        # Overrides for scene groups that write M-D-Y instead of the usual D-M-Y. Empty is a valid
        # state: with no row for a group, NfoDate falls back to its positional default.
        'rules_scene_group_date_format': '\n            CREATE TABLE IF NOT EXISTS rules_scene_group_date_format (\n                scene_group VARCHAR(64) NOT NULL PRIMARY KEY,\n                date_format VARCHAR(8) NOT NULL,\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n            )\n        ',
        # Radio shows and podcast series, curated the same way genres are: the
        # detector files what it finds as 'unknown' and only 'white' shows are ever
        # written to a file. `host` and `station` are descriptive; nothing reads them
        # yet, but a station like Toxic Sickness carries dozens of residencies and
        # that is the field which will group them.
        'rules_podcasts': "\n            CREATE TABLE IF NOT EXISTS rules_podcasts (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                name VARCHAR(255) NOT NULL,\n                normalized_name VARCHAR(191) NOT NULL UNIQUE,\n                state ENUM('white', 'black', 'unknown') NOT NULL DEFAULT 'unknown',\n                host VARCHAR(255) NULL,\n                station VARCHAR(255) NULL,\n                occurrences INT NOT NULL DEFAULT 0,\n                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                decided_at TIMESTAMP NULL,\n                decided_by VARCHAR(64),\n                INDEX(state)\n            )\n        ",
        'rules_podcast_aliases': '\n            CREATE TABLE IF NOT EXISTS rules_podcast_aliases (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                podcast_id INT NOT NULL,\n                alias VARCHAR(255) NOT NULL,\n                normalized_alias VARCHAR(191) NOT NULL UNIQUE,\n                occurrences INT NOT NULL DEFAULT 0,\n                INDEX(podcast_id),\n                FOREIGN KEY (podcast_id) REFERENCES rules_podcasts(id) ON DELETE CASCADE\n            )\n        ',
        'library_track_audio_features': '\n            CREATE TABLE IF NOT EXISTS library_track_audio_features (\n                track_id VARCHAR(255) PRIMARY KEY,\n                internal_track_id INT,\n                file_path TEXT,\n                tempo FLOAT,\n                duration FLOAT,\n                mean_spectral_centroid FLOAT,\n                std_spectral_centroid FLOAT,\n                mean_spectral_bandwidth FLOAT,\n                std_spectral_bandwidth FLOAT,\n                mean_spectral_rolloff FLOAT,\n                std_spectral_rolloff FLOAT,\n                mean_rms FLOAT,\n                std_rms FLOAT,\n                mean_zcr FLOAT,\n                std_zcr FLOAT,\n                mean_spectral_contrast FLOAT,\n                std_spectral_contrast FLOAT,\n                mfcc_1 FLOAT, mfcc_2 FLOAT, mfcc_3 FLOAT, mfcc_4 FLOAT, mfcc_5 FLOAT, mfcc_6 FLOAT, mfcc_7 FLOAT, mfcc_8 FLOAT, mfcc_9 FLOAT, mfcc_10 FLOAT, mfcc_11 FLOAT, mfcc_12 FLOAT, mfcc_13 FLOAT,\n                std_mfcc_1 FLOAT, std_mfcc_2 FLOAT, std_mfcc_3 FLOAT, std_mfcc_4 FLOAT, std_mfcc_5 FLOAT, std_mfcc_6 FLOAT, std_mfcc_7 FLOAT, std_mfcc_8 FLOAT, std_mfcc_9 FLOAT, std_mfcc_10 FLOAT, std_mfcc_11 FLOAT, std_mfcc_12 FLOAT, std_mfcc_13 FLOAT,\n                mean_chroma FLOAT,\n                std_chroma FLOAT,\n                artist_name VARCHAR(255),\n                label_name VARCHAR(255),\n                release_year INT,\n                release_date VARCHAR(10),\n                source_platform VARCHAR(50),\n                bpm_tag FLOAT,\n                genre_tag VARCHAR(100),\n                INDEX idx_af_file_path (file_path(255)),\n                INDEX idx_af_internal_track_id (internal_track_id),\n                CONSTRAINT fk_audio_features_internal_track_id FOREIGN KEY (internal_track_id) REFERENCES library_tracks(id) ON DELETE SET NULL\n            )\n        ',
        'library_track_ml_labels': '\n            CREATE TABLE IF NOT EXISTS library_track_ml_labels (\n                track_id VARCHAR(255) PRIMARY KEY,\n                ml_genre VARCHAR(100),\n                ml_review_status ENUM(\'unreviewed\', \'human_verified\', \'borderline\', \'do_not_train\') DEFAULT \'unreviewed\',\n                approved_for_training BOOLEAN DEFAULT FALSE,\n                internal_track_id INT,\n                CONSTRAINT fk_ml_labels_internal_track_id FOREIGN KEY (internal_track_id) REFERENCES library_tracks(id) ON DELETE SET NULL\n            )\n        ',
        # What a file said before the tagger first touched it, plus the version of the
        # code and a fingerprint of the rules in force at that moment. The tagger rewrites
        # tags in place and kept no copy: ORIGINAL_TITLE and ORIGINAL_ARTIST are the two
        # fields somebody noticed losing and hand-rolled a rescue for, one rule each.
        # Written once per file and never updated -- a later pass sees a file this tagger
        # already rewrote, so its idea of "arrival" is worth less than the first one's.
        # See services/tagger/ingestion.py and migrate_v22_ingestion_records.sql.
        'library_ingestion_records': '\n            CREATE TABLE IF NOT EXISTS library_ingestion_records (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                file_path TEXT NOT NULL,\n                file_path_hash VARCHAR(64) NOT NULL UNIQUE,\n                file_size BIGINT NULL,\n                source VARCHAR(32) NOT NULL,\n                tags_json LONGTEXT NOT NULL,\n                code_version VARCHAR(32) NULL,\n                rules_fingerprint VARCHAR(32) NULL,\n                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                INDEX idx_ingestion_recorded_at (recorded_at)\n            )\n        ',
        # One row per migrate_*.sql the deploy applied, keyed by file name, with the sha256
        # of the content it applied. scripts/deploy.sh skips a file whose name and hash are
        # recorded here; a changed file runs again. Kept identical to LEDGER_DDL in
        # tools/apply_migrations.py, which creates it too: the first deploy reads the ledger
        # before this code has ever run. See bug report 068.
        'schema_migrations': '\n            CREATE TABLE IF NOT EXISTS schema_migrations (\n                filename VARCHAR(255) NOT NULL PRIMARY KEY,\n                sha256 CHAR(64) NOT NULL,\n                applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP\n            )\n        ',
    }
    queries = [table_queries[table] for table in REQUIRED_TABLES]
    try:
        conn = DatabaseConnector().connect()
        try:
            with conn.cursor() as cursor:
                for query in queries:
                    try:
                        cursor.execute(query)
                    except Exception as e:
                        logging.debug('Query failed (might already exist): %s', e)
                # Same reason as the indexes below: CREATE TABLE IF NOT EXISTS
                # never alters an existing table, so a column the code started
                # selecting after the table first shipped has to be added here.
                # Both of these were found by tests/integration/test_router_sql.py,
                # which runs every endpoint's SQL against a freshly built schema:
                # /api/youtube and /api/system/activity returned 500 on one.
                for column_sql in (
                    'ALTER TABLE downloads_youtube_accounts ADD COLUMN IF NOT EXISTS channel_id VARCHAR(255)',
                    "ALTER TABLE downloads_youtube_accounts ADD COLUMN IF NOT EXISTS download_type "
                    "ENUM('audio', 'video') NOT NULL DEFAULT 'audio'",
                    'ALTER TABLE downloads_youtube_accounts ADD COLUMN IF NOT EXISTS active TINYINT(1) NOT NULL DEFAULT 1',
                    'ALTER TABLE downloads_youtube_accounts ADD COLUMN IF NOT EXISTS min_duration INT DEFAULT 60',
                    'ALTER TABLE downloads_youtube_accounts ADD COLUMN IF NOT EXISTS '
                    'output_folder_override VARCHAR(255)',
                    # One channel can be both an audio and a video source, so the
                    # name alone stops being a key. Production already carries the
                    # composite key; this is what brings a db_init-built schema in
                    # line with it. See migrate_v6_youtube_video.sql.
                    'ALTER TABLE downloads_youtube_accounts DROP PRIMARY KEY, ADD PRIMARY KEY (name, download_type)',
                    "ALTER TABLE downloads_youtube_archive ADD COLUMN IF NOT EXISTS download_type "
                    "ENUM('audio', 'video') NOT NULL DEFAULT 'audio'",
                    'ALTER TABLE downloads_youtube_archive ADD COLUMN IF NOT EXISTS path VARCHAR(255)',
                    # Without this the audio row of a channel would permanently
                    # block the video row from ever archiving the same video.
                    'ALTER TABLE downloads_youtube_archive ADD UNIQUE KEY '
                    'uniq_video_id_download_type (video_id, download_type)',
                    'ALTER TABLE library_track_ml_labels ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP '
                    'DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP',
                    # The full release date, beside release_year rather than replacing it: the year
                    # filters and the analytics year histogram still read that column.
                    'ALTER TABLE library_track_audio_features ADD COLUMN IF NOT EXISTS release_date VARCHAR(10)',
                    # Why a file is on the retag pile. needs_rescan stays the gate the
                    # tagger reads; this is only so the UI can say what queued the work.
                    # See migrate_v16_rescan_reason.sql.
                    'ALTER TABLE tagger_processed_files ADD COLUMN IF NOT EXISTS rescan_reason VARCHAR(64) NULL',
                    # FLOAT has a 128 s step at today's epoch, so the stored mtime was never the
                    # real one and 70% of the library read as changed on every walk. See
                    # migrate_v29_processed_mtime_double.sql.
                    'ALTER TABLE tagger_processed_files MODIFY COLUMN mtime DOUBLE',
                    # The pending pass pages the queue by (flag, path); see
                    # migrate_v28_pending_rescan_index.sql.
                    'CREATE INDEX IF NOT EXISTS idx_tagger_processed_files_pending '
                    'ON tagger_processed_files (needs_rescan, filepath)',
                    # The retry backoff of a file that keeps failing; see
                    # migrate_v37_processed_files_binary_path.sql. The binary collation of
                    # filepath from the same migration is left to the migration: it rebuilds
                    # the table, which a start-up should not do, and a fresh table gets it
                    # from ProcessedFilesHelper.create_table.
                    'ALTER TABLE tagger_processed_files ADD COLUMN IF NOT EXISTS attempts INT NOT NULL DEFAULT 0',
                    'ALTER TABLE tagger_processed_files ADD COLUMN IF NOT EXISTS last_attempt TIMESTAMP NULL DEFAULT NULL',
                    # The artist string as read off the file before CleanTagsRule split "feat"/"vs"/
                    # "&" into separate values, for display only -- never re-parsed or matched
                    # against library_artists. NULL until a file goes through a tag-write pass that
                    # captures it. See migrate_v19_display_artist.sql.
                    'ALTER TABLE library_tracks ADD COLUMN IF NOT EXISTS display_artist VARCHAR(512) NULL',
                    # What yt-dlp knew about a download, pruned of transport detail. The
                    # tagger copies four fields out of the info dict and the rest used to be
                    # discarded when the process moved on, so SoundCloud's genre/tags and
                    # YouTube's music-credit artists were never written down anywhere. NULL
                    # for every row that predates this. See migrate_v21_download_info_json.sql
                    # and services/downloader/info_json.py.
                    'ALTER TABLE downloads_soundcloud_archive ADD COLUMN IF NOT EXISTS info_json LONGTEXT NULL',
                    'ALTER TABLE downloads_youtube_archive ADD COLUMN IF NOT EXISTS info_json LONGTEXT NULL',
                    # Production's archive predates the column above in CREATE TABLE and has no
                    # timestamp at all. Added NULL first and given its default second: ADD COLUMN
                    # with DEFAULT CURRENT_TIMESTAMP stamps every existing row with the moment of
                    # the ALTER, and 53.000 archived videos would read as downloaded on deploy day.
                    # See migrate_v31_youtube_archive_added_at.sql.
                    'ALTER TABLE downloads_youtube_archive ADD COLUMN IF NOT EXISTS added_at DATETIME NULL',
                    'ALTER TABLE downloads_youtube_archive ALTER COLUMN added_at SET DEFAULT CURRENT_TIMESTAMP',
                    # The release date the server read off the file, copied over by
                    # release_date_sync. Beside library_track_audio_features.release_date and not
                    # instead of it: that column only ever covered the tracks the ml-analyzer
                    # processed, which is why the feeds filtered on it and always came back empty.
                    # See migrate_v24_track_release_date.sql.
                    'ALTER TABLE library_tracks ADD COLUMN IF NOT EXISTS release_date VARCHAR(10) NULL',
                    # Where a genre sits between soft and hard, 0-100. Seeded from a curated
                    # anchor list and inherited down rules_subgenre_hierarchy by
                    # feeds.hardness.seed_genre_hardness (main.py startup), which only ever
                    # touches a row that is still NULL here -- a curator's own edit is never
                    # overwritten. See migrate_v25_genre_hardness.sql and
                    # docs/designs/feeds/functional.md, "Daily mixes v2".
                    'ALTER TABLE rules_genres ADD COLUMN IF NOT EXISTS hardness TINYINT UNSIGNED NULL',
                ):
                    try:
                        cursor.execute(column_sql)
                    except Exception as e:
                        logging.debug('Column already present or not applicable: %s', e)
                # CREATE TABLE IF NOT EXISTS never alters an existing table, which is how
                # library_track_audio_features ended up missing columns the code selected.
                # Index additions therefore need their own idempotent step.
                for index_sql in (
                    'ALTER TABLE library_track_genres ADD INDEX idx_genre_id (genre_id)',
                    'ALTER TABLE library_track_labels ADD INDEX idx_label_id (label_id)',
                    'ALTER TABLE library_tracks ADD INDEX idx_created_at (created_at)',
                    # Every join from a listen, a stat or a feed to an artist goes through
                    # primary_artist_id, and without this each one scans library_tracks.
                    # See migrate_v34_primary_artist_and_listen_track_indexes.sql.
                    'ALTER TABLE library_tracks ADD INDEX IF NOT EXISTS idx_tracks_primary_artist (primary_artist_id)',
                    # The tagger looks a download's info dict up by the absolute path it is
                    # holding -- it never learns a video id. The two archive tables keep that
                    # path in differently named columns; without these it is a full scan per
                    # file. See migrate_v23_download_archive_path_index.sql and
                    # services/tagger/download_info.py.
                    'ALTER TABLE downloads_soundcloud_archive ADD INDEX idx_filename (filename(255))',
                    'ALTER TABLE downloads_youtube_archive ADD INDEX idx_path (path)',
                ):
                    try:
                        cursor.execute(index_sql)
                    except Exception as e:
                        logging.debug('Index already present or not applicable: %s', e)
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logging.warning('Failed to ensure DB tables exist: %s', exc)
