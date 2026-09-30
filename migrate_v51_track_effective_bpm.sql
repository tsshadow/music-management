-- migrate_v51_track_effective_bpm.sql
--
-- Browse by BPM, issue #141 (docs/designs/bpm-browse/technical.md, "Effective BPM in SQL").
-- The effective BPM of every track -- the one services/music_manager/bpm/effective.py resolves:
-- a measurement from library_track_bpm first, else the file's BPM tag, else the old analyzer's
-- tempo, the latter two folded into the band of the track's genres -- materialised so the library
-- table, its BPM filter and search term, the analytics and the feeds can join it instead of each
-- choosing between the sources in SQL. The bpm-analyzer worker writes it
-- (services/music_manager/bpm/effective_table.py): in full every 30 minutes, and right after
-- each batch of measurements for the tracks in it. Nothing else writes it.
--
--   track_id     -- library_tracks.id. A derived row, so it follows the track: a rebuilt library
--                   cascades it away and the next full sync writes it again.
--   bpm          -- the effective tempo, 40-500.
--   source       -- 'measured', 'tag' or 'analyzer'.
--   confidence   -- 'high', 'medium' or 'low' (effective.py says which is which).
--   approximate  -- 1 when the value is on the old analyzer's coarse grid (not measured):
--                   the clients show it as "≈152".
--   folded       -- 1 when an octave correction changed the value.
--
-- A track without any usable source has no row. Re-runnable: CREATE TABLE IF NOT EXISTS only,
-- nothing is seeded (the worker fills it on its first round after the deploy).

CREATE TABLE IF NOT EXISTS library_track_effective_bpm (
    track_id INT NOT NULL PRIMARY KEY,
    bpm DECIMAL(5,2) NOT NULL,
    source ENUM('measured', 'tag', 'analyzer') NOT NULL,
    confidence ENUM('low', 'medium', 'high') NOT NULL,
    approximate TINYINT(1) NOT NULL DEFAULT 0,
    folded TINYINT(1) NOT NULL DEFAULT 0,
    updated_at DATETIME NOT NULL,
    INDEX idx_effective_bpm_bpm (bpm),
    FOREIGN KEY (track_id) REFERENCES library_tracks(id) ON DELETE CASCADE
);
