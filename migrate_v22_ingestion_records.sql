-- Keep what a file said before the tagger first touched it.
--
-- The tagger rewrites tags in place and keeps no copy of what was there. `ORIGINAL_TITLE`
-- and `ORIGINAL_ARTIST` are the two fields somebody noticed losing and then hand-rolled a
-- rescue for, each in its own rule and each conditional on the specific path that loses
-- it. Nothing records the rest, so "what did this file arrive with" has no answer -- and
-- neither does "which rule decided that", because the rules live in this database and
-- change over time.
--
-- One row per file, written the first time the tagger opens it: the whole tag set as
-- read, the version of the code, and a fingerprint of the rule tables in force at that
-- moment. That pair -- arrival state plus ruleset -- is what makes a tagging decision
-- reviewable afterwards.
--
-- Deliberately not a copy of the file. The tagger does not change the audio stream, so
-- duplicating 5,3 TB of audio would answer a question nobody asked; what is at risk is
-- the metadata, and that is a few hundred bytes per track.
--
-- `file_path_hash` is UNIQUE so the INSERT IGNORE in services/tagger/ingestion.py keeps
-- the *earliest* answer: a later pass sees a file this tagger already rewrote, and its
-- idea of "arrival" is worth less than the first one's. A file that moves gets a second
-- row under its new path rather than losing the first one, which is the right trade for a
-- record of what happened.
--
-- Mirrors the CREATE in services/common/db_init.py, which is what a fresh stack runs;
-- this file is what production runs.
CREATE TABLE IF NOT EXISTS library_ingestion_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    file_path TEXT NOT NULL,
    file_path_hash VARCHAR(64) NOT NULL UNIQUE,
    file_size BIGINT NULL,
    source VARCHAR(32) NOT NULL,
    tags_json LONGTEXT NOT NULL,
    code_version VARCHAR(32) NULL,
    rules_fingerprint VARCHAR(32) NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_ingestion_recorded_at (recorded_at)
);
