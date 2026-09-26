-- migrate_v44_song_version_ranking.sql
--
-- The ranking Teun decided on 2026-09-26 (docs/designs/song-versions/): format first, driven by
-- the prefer_lossless setting, then the version kind, then bitrate, then official release.
--
-- library_works.ranking_signature: which ranking the work's stored scores were computed under
-- ("v2-lossless", "v2-lossy"). NULL on every existing row, which is what makes the worker in
-- services/music_manager/song_version_worker.py rescore the whole library once after this
-- deploy, in 500-work batches that each commit on their own -- no row is touched here. A later
-- ranking change bumps RANKING_VERSION and the same mechanism runs again.
--
-- library_works.previous_canonical_track_id / canonical_changed_at: set by that rescore when it
-- replaces an existing canonical, so the Versions page in Beheer can flag the works whose
-- automatic choice changed and a curator can pin the old choice back. Cleared by a pin, a reset
-- or a dismiss.
--
-- Mirrors services/common/db_init.py. Re-runnable: IF NOT EXISTS. Nullable columns are an instant
-- ADD COLUMN in MariaDB.
ALTER TABLE library_works ADD COLUMN IF NOT EXISTS ranking_signature VARCHAR(32) NULL;

ALTER TABLE library_works ADD COLUMN IF NOT EXISTS previous_canonical_track_id INT NULL;

ALTER TABLE library_works ADD COLUMN IF NOT EXISTS canonical_changed_at TIMESTAMP NULL DEFAULT NULL;

ALTER TABLE library_works ADD INDEX IF NOT EXISTS idx_works_canonical_changed_at (canonical_changed_at);
