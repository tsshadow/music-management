import logging

from services.common.Helpers.DatabaseConnector import DatabaseConnector

REQUIRED_TABLES = [
    'downloads_soundcloud_accounts', 'downloads_soundcloud_archive', 
    'downloads_youtube_accounts', 'downloads_youtube_archive', 
    'library_artists', 'library_labels', 'library_tracks', 'library_media_files',
    'library_track_artists', 'library_track_labels',
    # rules_genres must precede library_track_genres: the latter carries a foreign
    # key to it, and MariaDB rejects a CREATE naming a table that does not exist
    # yet. The failure was swallowed by the debug-level except below, so on a fresh
    # database library_track_genres was silently never created.
    'rules_genres', 'library_track_genres',
    'rules_artist_genres', 'rules_label_genres',
    'rules_artist_genre', 'rules_label_genre', 'rules_catid_label', 
    'rules_festival_data',
    # rules_festivals must precede its two children: both carry a foreign key to it.
    'rules_festivals', 'rules_festival_aliases', 'rules_festival_editions',
    'rules_ignored_artists', 'rules_ignored_genres',
    'rules_subgenre_hierarchy', 'rules_genre_backlog', 'rules_genre_expansions',
    'rules_scene_group_date_format',
    'library_track_audio_features', 'library_track_ml_labels'
]

def ensure_tables_exist() -> None:
    """Ensure required database tables exist."""
    table_queries = {
        'downloads_soundcloud_accounts': '\n            CREATE TABLE IF NOT EXISTS downloads_soundcloud_accounts (\n                name VARCHAR(255),\n                soundcloud_id VARCHAR(255),\n                PRIMARY KEY (name)\n            )\n        ', 
        'downloads_soundcloud_archive': '\n            CREATE TABLE IF NOT EXISTS downloads_soundcloud_archive (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                account VARCHAR(255),\n                video_id VARCHAR(255),\n                filename TEXT,\n                url TEXT,\n                title TEXT,\n                added_at DATETIME DEFAULT CURRENT_TIMESTAMP,\n                INDEX(account),\n                INDEX(video_id)\n            )\n        ', 
        'downloads_youtube_accounts': '\n            CREATE TABLE IF NOT EXISTS downloads_youtube_accounts (\n                name VARCHAR(255) PRIMARY KEY\n            )\n        ', 
        'downloads_youtube_archive': '\n            CREATE TABLE IF NOT EXISTS downloads_youtube_archive (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                account VARCHAR(255),\n                video_id VARCHAR(255),\n                filename TEXT,\n                url TEXT,\n                title TEXT,\n                added_at DATETIME DEFAULT CURRENT_TIMESTAMP,\n                INDEX(account),\n                INDEX(video_id)\n            )\n        ', 
        'library_artists': '\n            CREATE TABLE IF NOT EXISTS library_artists (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                name VARCHAR(255) NOT NULL UNIQUE,\n                sort_name VARCHAR(255),\n                mbid VARCHAR(36),\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n            )\n        ',
        'library_labels': '\n            CREATE TABLE IF NOT EXISTS library_labels (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                name VARCHAR(255) NOT NULL UNIQUE,\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n            )\n        ',
        'library_tracks': '\n            CREATE TABLE IF NOT EXISTS library_tracks (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                track_uid VARCHAR(255) UNIQUE,\n                title VARCHAR(512),\n                duration_secs FLOAT,\n                primary_artist_id INT,\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n            )\n        ',
        'library_media_files': '\n            CREATE TABLE IF NOT EXISTS library_media_files (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                file_path TEXT NOT NULL,\n                file_path_hash VARCHAR(64) UNIQUE NOT NULL,\n                audio_hash VARCHAR(64),\n                duration_secs FLOAT,\n                track_id INT,\n                file_size BIGINT,\n                file_mtime DOUBLE,\n                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,\n                FOREIGN KEY (track_id) REFERENCES library_tracks(id) ON DELETE SET NULL\n            )\n        ',
        'library_track_artists': '\n            CREATE TABLE IF NOT EXISTS library_track_artists (\n                track_id INT NOT NULL,\n                artist_id INT NOT NULL,\n                role ENUM(\'primary\', \'featuring\', \'remixer\', \'producer\', \'composer\') DEFAULT \'primary\',\n                position INT DEFAULT 0,\n                PRIMARY KEY (track_id, artist_id, role),\n                FOREIGN KEY (track_id) REFERENCES library_tracks(id) ON DELETE CASCADE,\n                FOREIGN KEY (artist_id) REFERENCES library_artists(id) ON DELETE CASCADE\n            )\n        ',
        'library_track_genres': '\n            CREATE TABLE IF NOT EXISTS library_track_genres (\n                track_id INT NOT NULL,\n                genre_id INT NOT NULL,\n                weight FLOAT DEFAULT 1.0,\n                PRIMARY KEY (track_id, genre_id),\n                INDEX idx_genre_id (genre_id),\n                FOREIGN KEY (track_id) REFERENCES library_tracks(id) ON DELETE CASCADE,\n                FOREIGN KEY (genre_id) REFERENCES rules_genres(id) ON DELETE CASCADE\n            )\n        ',
        'library_track_labels': '\n            CREATE TABLE IF NOT EXISTS library_track_labels (\n                track_id INT NOT NULL,\n                label_id INT NOT NULL,\n                PRIMARY KEY (track_id, label_id),\n                FOREIGN KEY (track_id) REFERENCES library_tracks(id) ON DELETE CASCADE,\n                FOREIGN KEY (label_id) REFERENCES library_labels(id) ON DELETE CASCADE\n            )\n        ',
        'rules_artist_genre': '\n            CREATE VIEW IF NOT EXISTS rules_artist_genre AS\n            SELECT r.artist_name AS artist, g.name AS genre\n            FROM rules_artist_genres r\n            JOIN rules_genres g ON r.genre_id = g.id\n        ', 
        'rules_catid_label': '\n            CREATE TABLE IF NOT EXISTS rules_catid_label (\n                catid VARCHAR(255) PRIMARY KEY,\n                label VARCHAR(255) NOT NULL\n            )\n        ', 
        'rules_festival_data': '\n            CREATE TABLE IF NOT EXISTS rules_festival_data (\n                festival VARCHAR(255) NOT NULL,\n                year INT NOT NULL,\n                date DATE NOT NULL,\n                PRIMARY KEY (festival, year)\n            )\n        ',
        'rules_festivals': '\n            CREATE TABLE IF NOT EXISTS rules_festivals (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                name VARCHAR(255) NOT NULL,\n                normalized_name VARCHAR(191) NOT NULL UNIQUE,\n                active TINYINT(1) NOT NULL DEFAULT 1,\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n            )\n        ',
        'rules_festival_aliases': '\n            CREATE TABLE IF NOT EXISTS rules_festival_aliases (\n                festival_id INT NOT NULL,\n                alias VARCHAR(255) NOT NULL,\n                normalized_alias VARCHAR(191) NOT NULL,\n                PRIMARY KEY (festival_id, normalized_alias),\n                INDEX idx_normalized_alias (normalized_alias),\n                FOREIGN KEY (festival_id) REFERENCES rules_festivals(id) ON DELETE CASCADE\n            )\n        ',
        'rules_festival_editions': '\n            CREATE TABLE IF NOT EXISTS rules_festival_editions (\n                festival_id INT NOT NULL,\n                year INT NOT NULL,\n                date DATE NOT NULL,\n                PRIMARY KEY (festival_id, year),\n                FOREIGN KEY (festival_id) REFERENCES rules_festivals(id) ON DELETE CASCADE\n            )\n        ',
        'rules_genres': "\n            CREATE TABLE IF NOT EXISTS rules_genres (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                name VARCHAR(255) NOT NULL,\n                normalized_name VARCHAR(191) NOT NULL UNIQUE,\n                state ENUM('white', 'black', 'unknown') NOT NULL DEFAULT 'unknown',\n                canonical_id INT NULL,\n                occurrences INT NOT NULL DEFAULT 0,\n                corrected_genre VARCHAR(255),\n                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                decided_at TIMESTAMP NULL,\n                decided_by VARCHAR(64),\n                INDEX(state),\n                FOREIGN KEY (canonical_id) REFERENCES rules_genres(id) ON DELETE SET NULL\n            )\n        ",
        'rules_ignored_artists': '\n            CREATE TABLE IF NOT EXISTS rules_ignored_artists (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                name VARCHAR(255) NOT NULL,\n                corrected_name VARCHAR(255),\n                INDEX(name)\n            )\n        ', 
        'rules_ignored_genres': '\n            CREATE TABLE IF NOT EXISTS rules_ignored_genres (\n                name VARCHAR(255) PRIMARY KEY\n            )\n        ', 
        'rules_label_genre': '\n            CREATE VIEW IF NOT EXISTS rules_label_genre AS\n            SELECT r.label_name AS label, g.name AS genre\n            FROM rules_label_genres r\n            JOIN rules_genres g ON r.genre_id = g.id\n        ', 
        'rules_subgenre_hierarchy': '\n            CREATE TABLE IF NOT EXISTS rules_subgenre_hierarchy (\n                subgenre VARCHAR(255) NOT NULL,\n                genre VARCHAR(255) NOT NULL,\n                PRIMARY KEY (subgenre, genre)\n            )\n        ', 
        'rules_genre_backlog': '\n            CREATE TABLE IF NOT EXISTS rules_genre_backlog (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                genre VARCHAR(255) UNIQUE,\n                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n            )\n        ', 
        'rules_artist_genres': '\n            CREATE TABLE IF NOT EXISTS rules_artist_genres (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                artist_name VARCHAR(255) NOT NULL,\n                genre_id INT NOT NULL,\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                FOREIGN KEY (genre_id) REFERENCES rules_genres(id) ON DELETE CASCADE,\n                UNIQUE KEY (artist_name, genre_id)\n            )\n        ', 
        'rules_label_genres': '\n            CREATE TABLE IF NOT EXISTS rules_label_genres (\n                id INT AUTO_INCREMENT PRIMARY KEY,\n                label_name VARCHAR(255) NOT NULL,\n                genre_id INT NOT NULL,\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                FOREIGN KEY (genre_id) REFERENCES rules_genres(id) ON DELETE CASCADE,\n                UNIQUE KEY (label_name, genre_id)\n            )\n        ',
        'rules_genre_expansions': '\n            CREATE TABLE IF NOT EXISTS rules_genre_expansions (\n                genre_id INT NOT NULL,\n                target_id INT NOT NULL,\n                position INT NOT NULL DEFAULT 0,\n                PRIMARY KEY (genre_id, target_id),\n                KEY idx_rules_genre_expansions_target (target_id),\n                FOREIGN KEY (genre_id) REFERENCES rules_genres(id) ON DELETE CASCADE,\n                FOREIGN KEY (target_id) REFERENCES rules_genres(id) ON DELETE CASCADE\n            )\n        ',
        # Overrides for scene groups that write M-D-Y instead of the usual D-M-Y. Empty is a valid
        # state: with no row for a group, NfoDate falls back to its positional default.
        'rules_scene_group_date_format': '\n            CREATE TABLE IF NOT EXISTS rules_scene_group_date_format (\n                scene_group VARCHAR(64) NOT NULL PRIMARY KEY,\n                date_format VARCHAR(8) NOT NULL,\n                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n            )\n        ',
        'library_track_audio_features': '\n            CREATE TABLE IF NOT EXISTS library_track_audio_features (\n                track_id VARCHAR(255) PRIMARY KEY,\n                internal_track_id INT,\n                file_path TEXT,\n                tempo FLOAT,\n                duration FLOAT,\n                mean_spectral_centroid FLOAT,\n                std_spectral_centroid FLOAT,\n                mean_spectral_bandwidth FLOAT,\n                std_spectral_bandwidth FLOAT,\n                mean_spectral_rolloff FLOAT,\n                std_spectral_rolloff FLOAT,\n                mean_rms FLOAT,\n                std_rms FLOAT,\n                mean_zcr FLOAT,\n                std_zcr FLOAT,\n                mean_spectral_contrast FLOAT,\n                std_spectral_contrast FLOAT,\n                mfcc_1 FLOAT, mfcc_2 FLOAT, mfcc_3 FLOAT, mfcc_4 FLOAT, mfcc_5 FLOAT, mfcc_6 FLOAT, mfcc_7 FLOAT, mfcc_8 FLOAT, mfcc_9 FLOAT, mfcc_10 FLOAT, mfcc_11 FLOAT, mfcc_12 FLOAT, mfcc_13 FLOAT,\n                std_mfcc_1 FLOAT, std_mfcc_2 FLOAT, std_mfcc_3 FLOAT, std_mfcc_4 FLOAT, std_mfcc_5 FLOAT, std_mfcc_6 FLOAT, std_mfcc_7 FLOAT, std_mfcc_8 FLOAT, std_mfcc_9 FLOAT, std_mfcc_10 FLOAT, std_mfcc_11 FLOAT, std_mfcc_12 FLOAT, std_mfcc_13 FLOAT,\n                mean_chroma FLOAT,\n                std_chroma FLOAT,\n                artist_name VARCHAR(255),\n                label_name VARCHAR(255),\n                release_year INT,\n                release_date VARCHAR(10),\n                source_platform VARCHAR(50),\n                bpm_tag FLOAT,\n                genre_tag VARCHAR(100),\n                musical_key VARCHAR(20),\n                energy FLOAT,\n                danceability FLOAT,\n                valence FLOAT,\n                popularity INT,\n                FOREIGN KEY (internal_track_id) REFERENCES library_tracks(id) ON DELETE SET NULL\n            )\n        ',
        'library_track_ml_labels': '\n            CREATE TABLE IF NOT EXISTS library_track_ml_labels (\n                track_id VARCHAR(255) PRIMARY KEY,\n                ml_genre VARCHAR(100),\n                ml_review_status ENUM(\'unreviewed\', \'human_verified\', \'borderline\', \'do_not_train\') DEFAULT \'unreviewed\',\n                approved_for_training BOOLEAN DEFAULT FALSE,\n                internal_track_id INT,\n                FOREIGN KEY (internal_track_id) REFERENCES library_tracks(id) ON DELETE SET NULL\n            )\n        '
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
                    'ALTER TABLE downloads_youtube_accounts DROP PRIMARY KEY, '
                    'ADD PRIMARY KEY (name, download_type)',
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
                    'ALTER TABLE library_track_audio_features ADD COLUMN IF NOT EXISTS '
                    'release_date VARCHAR(10)',
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