-- migrate_v40_artist_curation_wired.sql
--
-- Wires the artist curation queue to the tagger (docs/designs/artist-curation/technical.md,
-- "Wiring the queue"). Until now the tagger matched titles against every name in
-- library_artists, and the scanner inserts every artist string it reads, so a name a rule
-- guessed became a trusted artist one scan later. From this release the tagger trusts a
-- name only when rules_artists approves it (white), or when it is listed here: the names
-- that were already in library_artists before the change and were trusted then. Anything
-- the scanner inserts after this migration is pending until a curator (or the
-- auto-external evidence run) approves it.
--
-- The seed runs once. It is guarded twice, because a re-run would grandfather every name
-- that arrived since and undo the point of the table:
--   * the table must still be empty, and
--   * the deploy ledger must not yet record this file (tools/apply_migrations.py writes
--     that row after the first successful apply, so emptying the table on purpose later
--     -- to make the tagger trust approved names only -- is not undone by a re-run
--     after an edit to this file).
-- Re-runnable: CREATE TABLE IF NOT EXISTS, and INSERT IGNORE behind the guards above.

CREATE TABLE IF NOT EXISTS rules_artist_legacy_trust (
    name VARCHAR(255) NOT NULL PRIMARY KEY,
    trusted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT IGNORE INTO rules_artist_legacy_trust (name)
SELECT a.name
FROM library_artists a
WHERE NOT EXISTS (SELECT 1 FROM rules_artist_legacy_trust)
  AND NOT EXISTS (
      SELECT 1 FROM schema_migrations WHERE filename = 'migrate_v40_artist_curation_wired.sql'
  );
