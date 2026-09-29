-- migrate_v50_track_bpm.sql
--
-- Browse by BPM (docs/designs/bpm-browse/). One row per track the BPM analysis worker has
-- measured -- or tried to: the tempo at 0.01 BPM, how sure the estimator was, and which file
-- it measured, so a replaced file is measured again.
--
--   track_uid         -- the join key. track_uid survives a library rebuild and a file move;
--                        library_tracks.id does not (the ratings learned that the hard way).
--   status            -- 'ok' with a bpm, or 'failed' with the error, so a file that cannot be
--                        decoded is not retried on every round.
--   bpm               -- the tempo after octave folding into the genre's band; NULL on failure.
--   raw_bpm           -- what the estimator measured before folding.
--   confidence        -- 0..1, the estimator's own (pulse strength, halves agreeing).
--   method            -- estimator and version, e.g. 'acf-comb-v1'; a new version can re-queue
--                        what an older one measured.
--   octave_corrected  -- 1 when folding changed the raw value.
--   file_mtime/size   -- the file as it was measured; a different file is measured again.
--
-- The browse API (services/music_manager/bpm/effective.py) reads this first and falls back to
-- library_track_audio_features.bpm_tag, then .tempo, while the table fills. Re-runnable:
-- CREATE TABLE IF NOT EXISTS only, nothing is seeded.

CREATE TABLE IF NOT EXISTS library_track_bpm (
    track_uid VARCHAR(255) NOT NULL PRIMARY KEY,
    status ENUM('ok', 'failed') NOT NULL DEFAULT 'ok',
    bpm DECIMAL(5,2) NULL,
    raw_bpm DECIMAL(5,2) NULL,
    confidence DECIMAL(4,3) NULL,
    method VARCHAR(32) NOT NULL,
    octave_corrected TINYINT(1) NOT NULL DEFAULT 0,
    file_mtime DOUBLE NULL,
    file_size BIGINT NULL,
    attempts INT NOT NULL DEFAULT 1,
    error VARCHAR(255) NULL,
    analyzed_at DATETIME NOT NULL,
    INDEX idx_track_bpm_bpm (bpm),
    INDEX idx_track_bpm_status (status, analyzed_at)
);
