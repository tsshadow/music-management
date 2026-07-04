-- Database migratie naar v2 design gebaseerd op docs/database-design.md

-- 1. Tracks & Files
CREATE TABLE IF NOT EXISTS library_artists (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    sort_name VARCHAR(255),
    mbid VARCHAR(36),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS library_labels (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rules_genres (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    corrected_genre VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS library_tracks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    track_uid VARCHAR(255) UNIQUE,
    title VARCHAR(512),
    duration_secs FLOAT,
    primary_artist_id INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS library_media_files (
    id INT AUTO_INCREMENT PRIMARY KEY,
    file_path TEXT NOT NULL,
    file_path_hash VARCHAR(64) UNIQUE NOT NULL,
    audio_hash VARCHAR(64),
    duration_secs FLOAT,
    track_id INT,
    file_size BIGINT,
    file_mtime DOUBLE,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (track_id) REFERENCES library_tracks(id) ON DELETE SET NULL
);

-- Migreer data van library_tagged_files naar library_media_files
-- We gebruiken een standalone PREPARE/EXECUTE om CREATE PROCEDURE permissie-fouten te voorkomen
SET @sql = IF(
    EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'library_tagged_files'),
    'INSERT IGNORE INTO library_media_files (file_path, file_path_hash, file_size, file_mtime) SELECT path, SHA2(path, 256), file_size, file_mtime FROM library_tagged_files',
    'DO 0'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 2. Artists & Aliases
ALTER TABLE library_artists ADD COLUMN IF NOT EXISTS sort_name VARCHAR(255);
ALTER TABLE library_artists ADD COLUMN IF NOT EXISTS mbid VARCHAR(36);

CREATE TABLE IF NOT EXISTS library_artist_aliases (
    id INT AUTO_INCREMENT PRIMARY KEY,
    artist_id INT NOT NULL,
    alias VARCHAR(255) NOT NULL,
    UNIQUE KEY (artist_id, alias),
    FOREIGN KEY (artist_id) REFERENCES library_artists(id) ON DELETE CASCADE
);

-- 3. Genres
-- De tabel rules_genres wordt nu aan het begin gedefinieerd en gebruikt.
-- We zorgen dat de kolommen correct zijn als ze al bestonden (hernoem 'genre' naar 'name' indien nodig).
SET @sql = IF(
    EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'rules_genres' AND column_name = 'genre'),
    'ALTER TABLE rules_genres CHANGE genre name VARCHAR(100) NOT NULL UNIQUE',
    'DO 0'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

ALTER TABLE rules_genres MODIFY COLUMN name VARCHAR(100) NOT NULL UNIQUE;
ALTER TABLE rules_genres ADD COLUMN IF NOT EXISTS corrected_genre VARCHAR(255);

-- 4. Junction tables
CREATE TABLE IF NOT EXISTS library_track_artists (
    track_id INT NOT NULL,
    artist_id INT NOT NULL,
    role ENUM('primary', 'featuring', 'remixer', 'producer', 'composer') DEFAULT 'primary',
    position INT DEFAULT 0,
    PRIMARY KEY (track_id, artist_id, role),
    FOREIGN KEY (track_id) REFERENCES library_tracks(id) ON DELETE CASCADE,
    FOREIGN KEY (artist_id) REFERENCES library_artists(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS library_track_genres (
    track_id INT NOT NULL,
    genre_id INT NOT NULL,
    weight FLOAT DEFAULT 1.0,
    PRIMARY KEY (track_id, genre_id),
    FOREIGN KEY (track_id) REFERENCES library_tracks(id) ON DELETE CASCADE,
    FOREIGN KEY (genre_id) REFERENCES rules_genres(id) ON DELETE CASCADE
);

-- 5. ML Tabellen (al deels aanwezig, maar check relaties)
-- Zorg dat track_id in ML tabellen eventueel naar de nieuwe library_tracks.id kan wijzen.
-- Momenteel is track_id in ML tabellen een VARCHAR(255) (vaak de hash).
-- We laten dit even zo voor compatibiliteit met de huidige analyzer code, 
-- maar we voegen een kolom toe voor de numerieke track_id.

CREATE TABLE IF NOT EXISTS library_track_audio_features (
    track_id VARCHAR(255) PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS library_track_ml_labels (
    track_id VARCHAR(255) PRIMARY KEY
);

ALTER TABLE library_track_audio_features ADD COLUMN IF NOT EXISTS internal_track_id INT;
ALTER TABLE library_track_audio_features ADD CONSTRAINT fk_audio_features_internal_track_id FOREIGN KEY IF NOT EXISTS (internal_track_id) REFERENCES library_tracks(id) ON DELETE SET NULL;

ALTER TABLE library_track_ml_labels ADD COLUMN IF NOT EXISTS internal_track_id INT;
ALTER TABLE library_track_ml_labels ADD CONSTRAINT fk_ml_labels_internal_track_id FOREIGN KEY IF NOT EXISTS (internal_track_id) REFERENCES library_tracks(id) ON DELETE SET NULL;

-- 6. Labels
-- library_labels is nu bovenaan gedefinieerd

CREATE TABLE IF NOT EXISTS library_track_labels (
    track_id INT NOT NULL,
    label_id INT NOT NULL,
    PRIMARY KEY (track_id, label_id),
    FOREIGN KEY (track_id) REFERENCES library_tracks(id) ON DELETE CASCADE,
    FOREIGN KEY (label_id) REFERENCES library_labels(id) ON DELETE CASCADE
);
