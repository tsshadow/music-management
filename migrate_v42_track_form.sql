-- migrate_v42_track_form.sql
--
-- What a file is, and when a live set was played. docs/designs/track-form/.
--
-- library_tracks.form: track / set / liveset / podcast, NULL while a track is not classified
-- (its length is unknown). SongTypeEnum records where a file came from, never what it is; before
-- this nothing did, and no filter could ask for live sets and leave the podcasts out.
--
-- library_tracks.performance_date: 'YYYY-MM-DD', only ever set on a live set whose festival
-- edition is known (rules_festival_editions). VARCHAR(10) like release_date (migrate_v24), so the
-- year filter can COALESCE the two without a cast. docs/product-goal.md, section on the year axis.
--
-- Columns and an index only; no row is touched here. The values are filled by the scanner for
-- every file it reads and, for the existing library, by the hourly pass in
-- services/music_manager/track_form_sync.py, which writes 5,000-row windows and only the rows that
-- differ -- a 330k-row UPDATE at deploy would hold library_tracks while the old containers run
-- (bug report 068). Both nullable columns are an instant ADD COLUMN in MariaDB.
--
-- Mirrors services/common/db_init.py. Re-runnable: IF NOT EXISTS. Recorded in schema_migrations,
-- so a deploy runs it once.
ALTER TABLE library_tracks ADD COLUMN IF NOT EXISTS form VARCHAR(16) NULL;

ALTER TABLE library_tracks ADD COLUMN IF NOT EXISTS performance_date VARCHAR(10) NULL;

ALTER TABLE library_tracks ADD INDEX IF NOT EXISTS idx_tracks_form (form);
