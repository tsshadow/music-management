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

-- 2b. Merge rows that collide on the normalized key.
--
--     Real data has them: production aborted here on 'hardcore frenchcore
--     hardmusic', where several rows differing only in punctuation had been
--     stored as separate genres. The unique index below cannot be created while
--     they exist, and this file runs unattended on every deploy, so it resolves
--     the collision itself rather than requiring a manual pre-step.
--
--     The lowest id survives; the others are deleted after everything pointing
--     at them is repointed. Nothing is lost that the new schema can express:
--     the duplicates were the same genre spelled differently.

DROP TEMPORARY TABLE IF EXISTS genre_dupes;
CREATE TEMPORARY TABLE genre_dupes (
    dup_id INT PRIMARY KEY,
    keep_id INT NOT NULL,
    KEY (keep_id)
);

INSERT INTO genre_dupes (dup_id, keep_id)
SELECT g.id, s.keep_id
FROM rules_genres g
JOIN (
    SELECT normalized_name, MIN(id) AS keep_id
    FROM rules_genres
    GROUP BY normalized_name
    HAVING COUNT(*) > 1
) s ON s.normalized_name = g.normalized_name
WHERE g.id <> s.keep_id;

-- Visible in the deploy log, so a merge is never silent.
SELECT CONCAT('Merging ', COUNT(*), ' genre rows that collide on the normalized name') AS migration_note
FROM genre_dupes;

-- Repoint references. The DELETEs drop rows that would violate the child
-- table's own unique key once repointed (the survivor already has that pairing).
DELETE r FROM rules_artist_genres r
JOIN genre_dupes d ON r.genre_id = d.dup_id
JOIN rules_artist_genres k ON k.artist_name = r.artist_name AND k.genre_id = d.keep_id;
UPDATE rules_artist_genres r JOIN genre_dupes d ON r.genre_id = d.dup_id
SET r.genre_id = d.keep_id;

DELETE r FROM rules_label_genres r
JOIN genre_dupes d ON r.genre_id = d.dup_id
JOIN rules_label_genres k ON k.label_name = r.label_name AND k.genre_id = d.keep_id;
UPDATE rules_label_genres r JOIN genre_dupes d ON r.genre_id = d.dup_id
SET r.genre_id = d.keep_id;

DELETE t FROM library_track_genres t
JOIN genre_dupes d ON t.genre_id = d.dup_id
JOIN library_track_genres k ON k.track_id = t.track_id AND k.genre_id = d.keep_id;
UPDATE library_track_genres t JOIN genre_dupes d ON t.genre_id = d.dup_id
SET t.genre_id = d.keep_id;

UPDATE rules_genres g JOIN genre_dupes d ON g.canonical_id = d.dup_id
SET g.canonical_id = d.keep_id;

-- Keep a correction the survivor does not have but a duplicate does.
UPDATE rules_genres k
JOIN genre_dupes d ON k.id = d.keep_id
JOIN rules_genres g ON g.id = d.dup_id
SET k.corrected_genre = g.corrected_genre
WHERE (k.corrected_genre IS NULL OR TRIM(k.corrected_genre) = '')
  AND g.corrected_genre IS NOT NULL AND TRIM(g.corrected_genre) <> '';

DELETE g FROM rules_genres g JOIN genre_dupes d ON g.id = d.dup_id;
DROP TEMPORARY TABLE genre_dupes;

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
