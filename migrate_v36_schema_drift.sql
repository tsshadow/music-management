-- migrate_v36_schema_drift.sql
--
-- Brings a deployed database and a freshly created one to the same schema. Until
-- tests/integration/test_schema_drift.py compared the two, nothing did: a fresh stack gets its
-- tables from services/common/db_init.py and the routers' init_db, production from this
-- directory, and each had things the other did not. See
-- docs/bug-reports/047-schema-drift-invisible-to-the-integration-suite.md.
--
-- Every statement here is a no-op on a database that already has the shape, because
-- scripts/deploy.sh applies every migrate_*.sql on every deploy.

-- 1. rules_ignored_artists: UNIQUE on name.
--
-- Production has a unique key on `name`; db_init declared a plain INDEX(name), so a fresh stack
-- accepted a second row for the same name (migrate_v22 had to be written around that). db_init
-- now declares the unique key; this gives it to a database that was built from the old CREATE.
-- Duplicates are removed first, keeping the newest row of each name: the curation endpoints
-- update an existing row rather than insert a second one, so a duplicate can only be an older
-- copy. The comparison is the column's own collation, the same one the unique key uses.
DELETE older
FROM rules_ignored_artists older
JOIN rules_ignored_artists newer ON newer.name = older.name AND newer.id > older.id;

-- A unique key on name alone, under whatever name it was given.
SET @has_unique := (
    SELECT COUNT(*) FROM (
        SELECT index_name
        FROM information_schema.statistics
        WHERE table_schema = DATABASE() AND table_name = 'rules_ignored_artists'
        GROUP BY index_name
        HAVING COUNT(*) = 1 AND MAX(column_name) = 'name' AND MAX(non_unique) = 0
    ) AS unique_on_name
);
-- The plain INDEX(name) the old CREATE made, which MariaDB named after the column.
SET @has_plain := (
    SELECT COUNT(*)
    FROM information_schema.statistics
    WHERE table_schema = DATABASE() AND table_name = 'rules_ignored_artists' AND index_name = 'name'
);
SET @ddl := IF(
    @has_unique > 0,
    'SELECT "rules_ignored_artists.name is already unique"',
    IF(
        @has_plain > 0,
        'ALTER TABLE rules_ignored_artists DROP INDEX name, ADD UNIQUE KEY name (name)',
        'ALTER TABLE rules_ignored_artists ADD UNIQUE KEY name (name)'
    )
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 2. library_track_audio_features: the five columns production never had.
--
-- db_init listed musical_key, energy, danceability, valence and popularity in its CREATE TABLE,
-- which is a no-op against production's existing table, so only fresh stacks ever had them.
-- Dropped rather than added to production: nothing writes them (the ml-analyzer fills tempo, the
-- spectral features and the MFCCs, never these) and nothing reads them since /library/advanced
-- stopped selecting them -- that query 500ed on production for exactly this reason. A column
-- nobody fills would only come back as a filter that always matches nothing.
--
-- Conditional, so that production -- which has none of them -- never rebuilds the table.
SET @ddl := (
    SELECT IF(
        COUNT(*) > 0,
        CONCAT('ALTER TABLE library_track_audio_features ', GROUP_CONCAT(CONCAT('DROP COLUMN ', column_name) SEPARATOR ', ')),
        'SELECT "library_track_audio_features has none of the unused columns"'
    )
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'library_track_audio_features'
      AND column_name IN ('musical_key', 'energy', 'danceability', 'valence', 'popularity')
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 3. Indexes db_init adds on every start and no migration ever declared.
--
-- ensure_tables_exist() runs these ALTERs at start-up, so a running stack already has them; this
-- makes the migrations say so too, which is the rule for a schema change (AGENTS.md).
ALTER TABLE library_track_genres ADD INDEX IF NOT EXISTS idx_genre_id (genre_id);
ALTER TABLE library_track_labels ADD INDEX IF NOT EXISTS idx_label_id (label_id);
ALTER TABLE library_tracks ADD INDEX IF NOT EXISTS idx_created_at (created_at);

-- 4. library_artists: the portrait columns routers/artist_images.py init_db adds.
--
-- No migration declared them: migrate_v30 and migrate_v32 update them on the strength of that
-- init_db having run at some earlier start-up. Production has them for the same reason.
ALTER TABLE library_artists ADD COLUMN IF NOT EXISTS primary_image_id INT NULL;
ALTER TABLE library_artists ADD COLUMN IF NOT EXISTS image_updated_at DATETIME NULL;
ALTER TABLE library_artists ADD COLUMN IF NOT EXISTS image_status VARCHAR(50) NULL;
