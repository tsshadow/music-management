-- migrate_v46_importer_file_problems.sql
--
-- importer_conflicts also holds the files the importer's extract step leaves in place: a file
-- in the import folder that is not an archive (a video a browser download left behind, an
-- image, a document, a loose track) or an archive no backend can extract. The extractor warns
-- once when a row is created, skips the file on later cycles until its size or mtime changes,
-- and deletes the row when the file is gone. For those rows `step` is 'extractor', `target`
-- is empty or a short detail, and `reason` says why; `reason` stays NULL for a folder pair.
-- Beheer lists them next to the folder conflicts. See
-- docs/bug-reports/119-importer-retries-non-archives-every-cycle.md.
--
-- Kept identical to the CREATE TABLE in services/common/db_init.py. Re-runnable: MODIFY to the
-- same definition is a no-op, and ADD COLUMN IF NOT EXISTS skips a column that exists.
ALTER TABLE importer_conflicts MODIFY step ENUM('renamer', 'mover', 'extractor') NOT NULL;

ALTER TABLE importer_conflicts ADD COLUMN IF NOT EXISTS reason VARCHAR(32) NULL AFTER fingerprint;
