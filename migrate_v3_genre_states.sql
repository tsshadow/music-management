-- Genre curation states.
--
-- Folds rules_genres (whitelist), rules_ignored_genres (blacklist) and
-- rules_genre_backlog (undecided) into a single rules_genres table carrying an
-- explicit state per genre. corrected_genre becomes a canonical_id pointing at a
-- real row, so a correction ('uptempo' -> 'Uptempo Hardcore') and a rejection
-- ('Arts') can no longer be confused with each other.
--
-- Safe to re-run. The legacy tables and the corrected_genre column are left in
-- place so tools/process_genres.py and tools/check_backlog.py keep working; they
-- are no longer read by the tagger and can be dropped in a later change.
--
-- Pre-check for genre names that only differ in casing or punctuation. These
-- collide on the new unique key and must be merged by hand first:
--
--   SELECT TRIM(REGEXP_REPLACE(LOWER(name), '[^a-z0-9]+', ' ')) AS k,
--          GROUP_CONCAT(name), COUNT(*) c
--   FROM rules_genres GROUP BY k HAVING c > 1;

-- 1. New columns.

ALTER TABLE rules_genres
    ADD COLUMN IF NOT EXISTS normalized_name VARCHAR(191) NULL AFTER name,
    ADD COLUMN IF NOT EXISTS state ENUM('white', 'black', 'unknown') NOT NULL DEFAULT 'unknown' AFTER normalized_name,
    ADD COLUMN IF NOT EXISTS canonical_id INT NULL AFTER state,
    ADD COLUMN IF NOT EXISTS occurrences INT NOT NULL DEFAULT 0 AFTER canonical_id,
    ADD COLUMN IF NOT EXISTS detected_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN IF NOT EXISTS decided_at TIMESTAMP NULL,
    ADD COLUMN IF NOT EXISTS decided_by VARCHAR(64) NULL;

ALTER TABLE rules_genres MODIFY COLUMN name VARCHAR(255) NOT NULL;

-- 2. Everything already in rules_genres was curated, so it is white.
--    Keyed on the empty normalized_name, which only legacy rows have: every row
--    inserted below carries one, so re-running this file never re-whitens a genre
--    that is waiting for curation.

UPDATE rules_genres
SET normalized_name = TRIM(REGEXP_REPLACE(LOWER(name), '[^a-z0-9]+', ' ')),
    state = 'white',
    decided_by = 'migration',
    decided_at = NOW()
WHERE normalized_name IS NULL OR normalized_name = '';

ALTER TABLE rules_genres MODIFY COLUMN normalized_name VARCHAR(191) NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_rules_genres_normalized_name ON rules_genres (normalized_name);
CREATE INDEX IF NOT EXISTS idx_rules_genres_state ON rules_genres (state);

-- The old unique key on name blocks aliases that share a display name; the
-- normalized key replaces it.
ALTER TABLE rules_genres DROP INDEX IF EXISTS name;

-- 3. Correction targets that do not exist as their own row yet.

INSERT IGNORE INTO rules_genres (name, normalized_name, state, decided_by, decided_at)
SELECT DISTINCT TRIM(corrected_genre),
       TRIM(REGEXP_REPLACE(LOWER(corrected_genre), '[^a-z0-9]+', ' ')),
       'white', 'migration', NOW()
FROM (SELECT corrected_genre FROM rules_genres WHERE corrected_genre IS NOT NULL AND TRIM(corrected_genre) <> '') AS targets;

-- 4. corrected_genre becomes canonical_id.

UPDATE rules_genres g
JOIN rules_genres c
  ON c.normalized_name = TRIM(REGEXP_REPLACE(LOWER(g.corrected_genre), '[^a-z0-9]+', ' '))
SET g.canonical_id = c.id
WHERE g.corrected_genre IS NOT NULL
  AND TRIM(g.corrected_genre) <> ''
  AND c.id <> g.id
  AND g.canonical_id IS NULL;

-- 5. rules_ignored_genres becomes state 'black'. Ignored won over whitelisted in
--    the old CleanAndFilterGenreRule, so it still wins here.

INSERT IGNORE INTO rules_genres (name, normalized_name, state, decided_by, decided_at)
SELECT TRIM(name), TRIM(REGEXP_REPLACE(LOWER(name), '[^a-z0-9]+', ' ')), 'black', 'migration', NOW()
FROM rules_ignored_genres
WHERE TRIM(name) <> '';

UPDATE rules_genres g
JOIN rules_ignored_genres i
  ON g.normalized_name = TRIM(REGEXP_REPLACE(LOWER(i.name), '[^a-z0-9]+', ' '))
SET g.state = 'black',
    g.decided_by = COALESCE(g.decided_by, 'migration'),
    g.decided_at = COALESCE(g.decided_at, NOW());

-- 6. rules_genre_backlog becomes state 'unknown', keeping its detection date.
--    Genres already decided are left alone.

INSERT IGNORE INTO rules_genres (name, normalized_name, state, detected_at)
SELECT TRIM(genre), TRIM(REGEXP_REPLACE(LOWER(genre), '[^a-z0-9]+', ' ')), 'unknown', detected_at
FROM rules_genre_backlog
WHERE genre IS NOT NULL AND TRIM(genre) <> '';
