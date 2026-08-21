-- Relink library_track_audio_features to library_tracks.
--
-- The features table carries two identifiers and neither is what the readers
-- assumed. `track_id` is its primary key and holds a
-- `library_media_files.file_path_hash` -- not a track uid -- which
-- services/ml-analyzer/migrate_paths.py states outright by joining
-- `f.track_id = m.file_path_hash`. The consumers in
-- routers/analytics_filters.py and routers/library.py joined it as
-- `t.track_uid = af.track_id`, comparing a uid against a path hash, which
-- matches almost nothing by construction.
--
-- Some rows did match, which is what hid this: ml-analyzer inserts its own
-- library_tracks rows with `track_uid = path_hash` (analyzer.py:235,241), so
-- analyzer-created tracks joined and scanner-created tracks -- the ones that
-- actually get played -- did not. Hence a features table that "joins fine" and
-- yet covers 0% of the listened library.
--
-- `internal_track_id` is the real foreign key to library_tracks(id) and is what
-- the readers should use. migrate_paths.py already populates it, but only
-- `WHERE f.file_path IS NULL OR f.internal_track_id IS NULL`, so a row holding a
-- wrong value is never repaired. This migration fills it unconditionally, by
-- both routes that can still resolve.

-- The path join below is over TEXT columns, which without these is a full
-- cross-product on 90k x 300k rows. A prefix index is enough: paths differ well
-- before 255 characters.
ALTER TABLE library_track_audio_features
    ADD INDEX IF NOT EXISTS idx_af_file_path (file_path(255));
ALTER TABLE library_media_files
    ADD INDEX IF NOT EXISTS idx_media_file_path (file_path(255));
ALTER TABLE library_track_audio_features
    ADD INDEX IF NOT EXISTS idx_af_internal_track_id (internal_track_id);

-- Route 1: the primary key really is a path hash for most rows.
UPDATE library_track_audio_features f
JOIN library_media_files m ON m.file_path_hash = f.track_id
SET f.internal_track_id = m.track_id,
    f.file_path = COALESCE(f.file_path, m.file_path)
WHERE m.track_id IS NOT NULL
  AND (f.internal_track_id IS NULL OR f.internal_track_id <> m.track_id);

-- Route 2: rows whose key is not a hash the library knows, but whose stored
-- path still is. This is the route that was measured to resolve on production
-- where the other two identifiers did not.
UPDATE library_track_audio_features f
JOIN library_media_files m ON m.file_path = f.file_path
SET f.internal_track_id = m.track_id
WHERE f.internal_track_id IS NULL
  AND f.file_path IS NOT NULL
  AND m.track_id IS NOT NULL;
