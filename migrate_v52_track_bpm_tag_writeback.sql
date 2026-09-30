-- migrate_v52_track_bpm_tag_writeback.sql
--
-- Issue #139, docs/designs/bpm-tag-writeback/: the measured tempo is written into the files'
-- own BPM tag (ID3 TBPM, MP4 tmpo, Vorbis BPM) by a capped step of the tagger's round
-- (services/music_manager/bpm/tag_writeback.py). These columns are its bookkeeping:
--
--   tag_bpm         -- the measured bpm the file's tag was last reconciled with. The step's
--                      queue is every confident, current measurement where this differs from
--                      bpm, so a new measurement with a different value queues the file again.
--   tag_action      -- how: written, matches, kept, missing, unsupported, failed.
--   tag_checked_at  -- when.
--
-- Re-runnable: ADD COLUMN IF NOT EXISTS only. Nothing is marked or queued here -- a migration
-- runs on every deploy (see the notes on migrate_v7), and the step finds its own work.

ALTER TABLE library_track_bpm ADD COLUMN IF NOT EXISTS tag_bpm DECIMAL(5,2) NULL;
ALTER TABLE library_track_bpm ADD COLUMN IF NOT EXISTS tag_action VARCHAR(16) NULL;
ALTER TABLE library_track_bpm ADD COLUMN IF NOT EXISTS tag_checked_at DATETIME NULL;
