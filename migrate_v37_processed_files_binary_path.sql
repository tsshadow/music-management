-- migrate_v37_processed_files_binary_path.sql
--
-- Two changes to the tagger's bookkeeping table, tagger_processed_files. See
-- docs/bug-reports/051-a-failing-file-is-retried-every-round-forever.md.
--
-- 1. filepath compares byte for byte.
--
-- The primary key was created with the table default, utf8mb4_general_ci. That collation
-- folds case and accents and gives every character outside the Basic Multilingual Plane
-- (the emoji YouTube titles are full of) the same weight, so two files whose paths differ
-- only in such a character shared one row. The tagger's in-memory snapshot matches paths
-- exactly, so on every walk one of the pair was "not in the table" and was retagged, and
-- each mark_processed overwrote the other file's mtime. utf8mb4_bin is the question the
-- tagger actually asks: is *this* path known.
--
-- Going from a case-insensitive collation to a binary one can never make two existing
-- keys equal -- binary equality is strictly finer, and both collations pad trailing
-- spaces the same way -- so no row has to be removed before the MODIFY. What the merge
-- did cost is a row that stands for two files: it carries one file's name and possibly
-- the other's mtime. Before the collation changes, while the join below can still see
-- the pair, those rows are queued for a retag. The twin that has no row of its own is
-- picked up by the tagger's own anti-join against library_media_files, which is binary
-- from here on. After the MODIFY the join finds nothing, so a re-run is a no-op.
--
-- To measure the pairs first (read-only):
--
--   SELECT t.filepath AS stored, m.file_path AS twin
--   FROM tagger_processed_files t
--   JOIN library_media_files m ON m.file_path = t.filepath AND BINARY t.filepath <> m.file_path;
--
-- (on a server where the two columns carry different _ci collations, add
-- `COLLATE <filepath's collation>` to m.file_path, as the UPDATE below does)
--
-- 2. A failing file backs off and is eventually parked.
--
-- A queued file that raised in the tagger kept needs_rescan = TRUE and was handed out
-- again every five-minute round, forever, logging an ERROR each time. `attempts` counts
-- the failures since the file was last tagged or re-queued on purpose, `last_attempt`
-- says when the last one was; the pending pass skips a row until
-- last_attempt + 2^attempts * 300 s has passed, and after five failures the row is
-- parked with reason `failed`. Both are plain additions the running release ignores.
--
-- Re-runnable: the UPDATE only runs while the column is not binary yet, ADD COLUMN IF NOT
-- EXISTS is a no-op the second time, and the MODIFY is conditional on
-- information_schema.

ALTER TABLE tagger_processed_files
    ADD COLUMN IF NOT EXISTS attempts INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_attempt TIMESTAMP NULL DEFAULT NULL;

-- Only while the column is not binary yet, and compared under the column's own collation --
-- the one that merged the pair. library_media_files may have been created under another
-- default (utf8mb4_uca1400_ai_ci on a new server) and MariaDB refuses to compare two
-- different _ci collations implicitly, so the join names it explicitly.
SET @filepath_collation := COALESCE((
    SELECT collation_name
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'tagger_processed_files'
      AND column_name = 'filepath'
), 'utf8mb4_bin');
SET @dml := IF(
    @filepath_collation = 'utf8mb4_bin',
    'SELECT "tagger_processed_files.filepath is already utf8mb4_bin, nothing to requeue"',
    CONCAT(
        'UPDATE tagger_processed_files t ',
        'JOIN library_media_files m ON m.file_path COLLATE ', @filepath_collation, ' = t.filepath ',
        'AND BINARY t.filepath <> BINARY m.file_path ',
        'SET t.needs_rescan = TRUE, t.rescan_reason = "binary_path", t.attempts = 0, t.last_attempt = NULL ',
        'WHERE t.needs_rescan = FALSE'
    )
);
PREPARE stmt FROM @dml;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl := (
    SELECT IF(
        COUNT(*) = 0,
        'ALTER TABLE tagger_processed_files MODIFY filepath VARCHAR(767) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL',
        'SELECT "tagger_processed_files.filepath is already utf8mb4_bin"'
    )
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'tagger_processed_files'
      AND column_name = 'filepath'
      AND collation_name = 'utf8mb4_bin'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
