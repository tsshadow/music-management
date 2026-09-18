-- The retag queue is read directly now, not found by walking every folder.
--
-- `Tagger._process_pending` pages through the rows with `needs_rescan = TRUE` in
-- primary-key order (`WHERE needs_rescan = TRUE AND filepath > ? ORDER BY filepath
-- LIMIT n`) before any folder walk starts. Without an index that leads with the flag
-- every page is a full scan of the table -- 264k rows on production -- and there is
-- one page per 500 queued files. Leading with `needs_rescan` and ending with
-- `filepath` makes the page a single range read.
--
-- `ProcessedFilesHelper.create_table` creates the same index on start-up, so a
-- database that never ran this file ends up identical; this exists so the schema
-- test builds it too.
CREATE INDEX IF NOT EXISTS idx_tagger_processed_files_pending
    ON tagger_processed_files (needs_rescan, filepath);
