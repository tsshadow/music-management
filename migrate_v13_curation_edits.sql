-- Storage behind the artist, label and genre edit pages.
--
-- Artists already have everything these pages need: `library_artists.mbid`,
-- `artist_external_ids`, `library_artist_aliases` and `rules_artist_genres`. Labels
-- have almost none of it -- `library_labels` is (id, name) and nothing else -- so the
-- asymmetry is what this file removes.
--
-- Safe to re-run: scripts/deploy.sh applies every migrate_*.sql on every deploy.

-- 1. A label can be identified the way an artist can.

ALTER TABLE library_labels
    ADD COLUMN IF NOT EXISTS mbid VARCHAR(36) NULL,
    ADD COLUMN IF NOT EXISTS parent_label_id INT NULL;

-- Sublabels. Nothing reads this yet: the tagger rule that lets a sublabel inherit its
-- parent's genres is later work, and the model lands first so the data can be entered.
-- ON DELETE SET NULL rather than CASCADE -- removing a parent label must not delete
-- the releases filed under its sublabels.
ALTER TABLE library_labels
    ADD CONSTRAINT fk_labels_parent FOREIGN KEY IF NOT EXISTS (parent_label_id)
        REFERENCES library_labels(id) ON DELETE SET NULL;

-- 2. External ids for labels, mirroring artist_external_ids.
--
--    Deliberately a second table rather than one polymorphic table keyed by
--    (entity_type, entity_id): that shape cannot carry a real foreign key, and
--    artist_external_ids is already populated by the image fetcher and would have had
--    to be rewritten to adopt it.

CREATE TABLE IF NOT EXISTS label_external_ids (
    id INT AUTO_INCREMENT PRIMARY KEY,
    label_id INT NOT NULL,
    source VARCHAR(50) NOT NULL,
    external_id VARCHAR(255) NOT NULL,
    external_url TEXT NULL,
    verified TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_label_source (label_id, source),
    CONSTRAINT fk_label_external_ids FOREIGN KEY (label_id)
        REFERENCES library_labels(id) ON DELETE CASCADE
);

-- 3. Who wrote a rule.
--
--    rules_genres has carried `decided_by` since migrate_v3, which is what stops the
--    tagger from overwriting a human's decision. The artist and label rule tables never
--    got the equivalent, so a hand-made rule and a generated one are indistinguishable.

ALTER TABLE rules_artist_genres ADD COLUMN IF NOT EXISTS created_by VARCHAR(64) NULL;
ALTER TABLE rules_label_genres  ADD COLUMN IF NOT EXISTS created_by VARCHAR(64) NULL;

-- 4. rules_subgenre_hierarchy keeps its (subgenre, genre) name columns on purpose.
--    InferGenreFromSubgenreRule reads it through a name-keyed LookupTableHelper, so
--    moving to genre ids means changing the helper, the rule and every caller in one
--    step. The edit page validates both sides against white genres instead, which buys
--    the integrity without the migration. migrate_v3_genre_states.sql is 162 lines of
--    evidence for what that conversion costs.
--
--    It does need its primary key, though: db_init.py declares PRIMARY KEY
--    (subgenre, genre) but databases created before that never got one, so the same
--    pair can sit in the table twice. An edit page that deletes "the" parent would
--    then leave a copy behind and the parent would come back on the next page load.
--
--    The table has no id column, so duplicates cannot be told apart by a self-join.
--    Rebuilding from a DISTINCT copy is the way to collapse them. The rebuild only
--    runs when the primary key is actually missing: once it exists, duplicates cannot
--    have been inserted, and re-running must not truncate a live table for nothing.

SET @has_pk = (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE table_schema = DATABASE()
      AND table_name = 'rules_subgenre_hierarchy'
      AND index_name = 'PRIMARY'
);

CREATE TEMPORARY TABLE IF NOT EXISTS subgenre_hierarchy_distinct AS
SELECT DISTINCT subgenre, genre
FROM rules_subgenre_hierarchy
WHERE subgenre IS NOT NULL AND genre IS NOT NULL
  AND TRIM(subgenre) <> '' AND TRIM(genre) <> '';

SET @ddl = IF(@has_pk = 0, 'DELETE FROM rules_subgenre_hierarchy', 'DO 0');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl = IF(@has_pk = 0,
    'INSERT INTO rules_subgenre_hierarchy (subgenre, genre) SELECT subgenre, genre FROM subgenre_hierarchy_distinct',
    'DO 0');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

DROP TEMPORARY TABLE IF EXISTS subgenre_hierarchy_distinct;

ALTER TABLE rules_subgenre_hierarchy
    MODIFY COLUMN subgenre VARCHAR(255) NOT NULL,
    MODIFY COLUMN genre VARCHAR(255) NOT NULL;

SET @ddl = IF(@has_pk = 0,
    'ALTER TABLE rules_subgenre_hierarchy ADD PRIMARY KEY (subgenre, genre)',
    'DO 0');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 5. artist_external_ids catches up with what the code reads.
--
--    Production has `external_url` and `verified`; the CREATE TABLE in
--    artist_images.py never did, so a database built from the bootstrap had a
--    narrower table than every query against it assumed. Adding them here covers the
--    databases already built that way -- on production both are no-ops.

ALTER TABLE artist_external_ids
    ADD COLUMN IF NOT EXISTS external_url TEXT NULL,
    ADD COLUMN IF NOT EXISTS verified TINYINT(1) NOT NULL DEFAULT 0;
