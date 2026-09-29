-- migrate_v49_artist_popular_tracks.sql
--
-- The "Oude hitjes" feed (docs/designs/old-hits-feed/). The popular-tracks loop
-- (services/music_manager/popular_tracks/worker.py) asks Deezer, and Last.fm when a key is
-- configured, for the top tracks of the artists that matter to somebody's profile, and
-- keeps them here matched to the library so the feed never calls out itself.
--
--   artist_popularity_fetches -- per artist (normalized name) and source: when it was last
--                                fetched, whether the artist was found, how many tracks came
--                                back and how many matched a library track.
--   artist_popular_tracks     -- the top list as the source reported it: position, the
--                                source's popularity number (Deezer rank, Last.fm listeners)
--                                and the library track it matched. matched_track_uid is the
--                                join key -- track_uid survives a library rebuild, track and
--                                work ids do not; matched_work_id is informational.
--
-- Keyed by artist name rather than library_artists.id for the same reason: a rebuild
-- renumbers artists. Re-runnable: CREATE TABLE IF NOT EXISTS only, nothing is seeded.

CREATE TABLE IF NOT EXISTS artist_popularity_fetches (
    artist_key VARCHAR(191) NOT NULL,
    source VARCHAR(16) NOT NULL,
    artist_name VARCHAR(255) NULL,
    external_artist_id VARCHAR(64) NULL,
    status ENUM('ok', 'not_found', 'error') NOT NULL,
    track_count INT NOT NULL DEFAULT 0,
    matched_count INT NOT NULL DEFAULT 0,
    fetched_at DATETIME NOT NULL,
    PRIMARY KEY (artist_key, source),
    INDEX idx_popularity_fetches_fetched_at (fetched_at)
);

CREATE TABLE IF NOT EXISTS artist_popular_tracks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    artist_key VARCHAR(191) NOT NULL,
    source VARCHAR(16) NOT NULL,
    external_track_id VARCHAR(64) NOT NULL,
    title VARCHAR(512) NULL,
    normalized_title VARCHAR(191) NULL,
    popularity INT NULL,
    position INT NOT NULL,
    matched_track_uid VARCHAR(255) NULL,
    matched_work_id INT NULL,
    fetched_at DATETIME NOT NULL,
    UNIQUE KEY uniq_popular_track (artist_key, source, external_track_id),
    INDEX idx_popular_tracks_matched (matched_track_uid)
);
