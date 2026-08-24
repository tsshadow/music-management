-- A song, above the version. library_tracks is already the version level -- track_uid
-- hashes title, duration and primary artist, so a radio edit and an extended mix are
-- two rows -- and library_media_files is the file. Only the song itself was missing.
--
-- The pin lives here rather than on the track because it has to survive a rescan.
-- Anything hanging off a value re-derived per scan is lost on the next one; the audio
-- features joined on file_path and sat at 0% coverage after a library rebuild.
CREATE TABLE IF NOT EXISTS library_works (
    id INT AUTO_INCREMENT PRIMARY KEY,
    work_key VARCHAR(191) UNIQUE NOT NULL,
    title VARCHAR(512),
    primary_artist_id INT,
    canonical_track_id INT NULL,
    pinned_track_id INT NULL,
    -- Reserved for the original-to-remix link, which is wanted for statistics later.
    -- Nothing reads it yet; a nullable column now is cheaper than a migration then.
    related_work_id INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE library_tracks
    ADD COLUMN IF NOT EXISTS work_id INT NULL;
ALTER TABLE library_tracks
    ADD INDEX IF NOT EXISTS idx_tracks_work_id (work_id);

-- radio, edit, original, none, extended, instrumental -- in ranking order. Whether a
-- file is a rip is provenance, decided a tier higher, so it is not a kind.
ALTER TABLE library_tracks
    ADD COLUMN IF NOT EXISTS version_kind VARCHAR(32) NULL;

-- The tiers packed into one integer, each weighted above the maximum of every tier
-- below it, so an integer comparison is a lexicographic one and ORDER BY works.
ALTER TABLE library_tracks
    ADD COLUMN IF NOT EXISTS version_score INT NULL;

-- Set when a track has been pulled out of its group by hand. The worker leaves those
-- alone, otherwise the next pass would put the track straight back.
ALTER TABLE library_tracks
    ADD COLUMN IF NOT EXISTS work_locked TINYINT NOT NULL DEFAULT 0;
