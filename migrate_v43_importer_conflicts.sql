-- migrate_v43_importer_conflicts.sql
--
-- importer_conflicts: folder pairs the importer's renamer or mover left in place because the
-- name it wanted was taken by a folder holding a different release. The importer warns once
-- when a row is created, compares the pair again only when either folder changed on disk, and
-- deletes the row when the pair is no longer met. Beheer lists the rows next to the label
-- proposals. See docs/bug-reports/091-importer-conflict-warning-spam.md.
--
-- Kept identical to the CREATE TABLE in services/common/db_init.py. Re-runnable:
-- CREATE TABLE IF NOT EXISTS; the schema_migrations ledger (bug report 068) skips it once
-- applied, but it does not rely on that.
CREATE TABLE IF NOT EXISTS importer_conflicts (
    pair_key CHAR(64) NOT NULL PRIMARY KEY,
    step ENUM('renamer', 'mover') NOT NULL,
    source VARCHAR(1024) NOT NULL,
    target VARCHAR(1024) NOT NULL,
    fingerprint CHAR(64) NULL,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX(step)
);
