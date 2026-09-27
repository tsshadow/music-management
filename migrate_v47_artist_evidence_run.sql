-- migrate_v47_artist_evidence_run.sql
--
-- The scheduled artist evidence run (docs/designs/artist-curation/technical.md,
-- "Scheduled evidence run"; services/music_manager/artist_auto_approve_worker.py).
-- tools/artist_auto_approve.py kept its verdicts and its ledger in a local sqlite file;
-- the loop inside music-manager keeps them here, so a restart or a deploy neither
-- repeats a round nor asks the external catalogues about a name it already judged.
--
--   rules_artist_evidence_runs -- one row per round: when, dry run or not, and its counts.
--   rules_artist_evidence      -- per name, the last verdict, its rule and evidence, the
--                                 round that produced it and when it was applied. A
--                                 verdict is not a decision; the decision stays in
--                                 rules_artists (signed auto-external when applied).
--
-- Re-runnable: CREATE TABLE IF NOT EXISTS only, nothing is seeded.

CREATE TABLE IF NOT EXISTS rules_artist_evidence_runs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP NULL,
    dry_run TINYINT(1) NOT NULL DEFAULT 1,
    new_names INT NOT NULL DEFAULT 0,
    backlog_names INT NOT NULL DEFAULT 0,
    approved INT NOT NULL DEFAULT 0,
    applied INT NOT NULL DEFAULT 0,
    unresolved INT NOT NULL DEFAULT 0,
    skipped INT NOT NULL DEFAULT 0,
    incomplete INT NOT NULL DEFAULT 0,
    requests INT NOT NULL DEFAULT 0,
    failed_requests INT NOT NULL DEFAULT 0,
    stopped_early TINYINT(1) NOT NULL DEFAULT 0,
    INDEX(started_at)
);

CREATE TABLE IF NOT EXISTS rules_artist_evidence (
    name VARCHAR(255) NOT NULL PRIMARY KEY,
    policy VARCHAR(16) NOT NULL,
    titles_hash CHAR(16) NOT NULL,
    verdict ENUM('approve', 'unresolved', 'skipped', 'incomplete') NOT NULL,
    rule VARCHAR(64) NULL,
    evidence MEDIUMTEXT NULL,
    run_id INT NULL,
    checked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    applied_at TIMESTAMP NULL,
    INDEX(verdict),
    INDEX(run_id),
    INDEX(checked_at)
);
