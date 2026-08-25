-- Why a file is waiting for a retag.
--
-- `tagger_processed_files.needs_rescan` already existed and stays the gate: it is what
-- `ProcessedFilesHelper.needs_processing` reads on the hot path, once per file per
-- tagging round, and nothing about that changes. This column sits beside it purely so
-- the web UI can say *what* queued the work -- a changed artist rule, a genre
-- decision, a redirect -- before someone presses the retag button.
--
-- No separate queue table, and no history: `mark_processed` clears the flag and the
-- reason together, so a row only ever carries the reason for the work still ahead of
-- it. A second table would add a join for an audit trail nobody is asking for.
--
-- VARCHAR(64) because the values are short internal identifiers written by the
-- invalidator (`artist_genre_rule`, `label_genre_rule`, `genre_decision`,
-- `artist_redirect`, `fallback`), not free text.
ALTER TABLE tagger_processed_files
    ADD COLUMN IF NOT EXISTS rescan_reason VARCHAR(64) NULL;
