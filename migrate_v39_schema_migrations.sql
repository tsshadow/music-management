-- migrate_v39_schema_migrations.sql
--
-- schema_migrations: the deploy's ledger of applied migrations. One row per migrate_*.sql,
-- keyed by file name, with the sha256 of the content that applied. tools/apply_migrations.py
-- (called by scripts/deploy.sh) skips a file whose name and hash are recorded, and runs a
-- changed or unrecorded one. See
-- docs/bug-reports/068-deploy-hangs-on-no-op-alter-metadata-lock.md.
--
-- tools/apply_migrations.py creates the same table before it reads the ledger, because the
-- first deploy after this change reads it before any migration has run; this file keeps the
-- schema-change rule (db_init, a migration, the expected tables) whole. Re-runnable:
-- CREATE TABLE IF NOT EXISTS.
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename VARCHAR(255) NOT NULL PRIMARY KEY,
    sha256 CHAR(64) NOT NULL,
    applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
