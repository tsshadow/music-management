-- The retag queue is served per reason now, decisions before bulk.
--
-- `Tagger._process_pending` asks for the queued reasons, orders them (a genre or artist
-- decision, a rule, a hand-picked file; then files the scanner found that the tagger never
-- saw; then "rescan all" and the deep run; then rows from before reasons were recorded) and
-- pages through each one by primary key: `WHERE needs_rescan = TRUE AND rescan_reason = ?
-- AND filepath > ? ORDER BY filepath LIMIT n`. The index from migrate_v28 leads with the
-- flag and ends with the path, so that page had to filter every queued row on the reason --
-- 70k rows per page, one page per 500 files. Leading with the reason as well makes it a
-- single range read again. The old index is a strict prefix of this one and is dropped.
--
-- `ProcessedFilesHelper.create_table` creates the same index on start-up, so a database
-- that never ran this file ends up identical; this exists so the schema test builds it too.
CREATE INDEX IF NOT EXISTS idx_tagger_processed_files_pending_reason
    ON tagger_processed_files (needs_rescan, rescan_reason, filepath);
DROP INDEX IF EXISTS idx_tagger_processed_files_pending ON tagger_processed_files;
