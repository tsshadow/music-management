-- Genre rewrites with more than one target.
--
-- `rules_genres.canonical_id` can only express 'this genre becomes that genre'.
-- Contractions need more: 'Upterror' is 'Uptempo Hardcore' plus 'Terror'. Targets
-- therefore move into their own table, and canonical_id joins corrected_genre as a
-- legacy column that the tagger no longer reads.
--
-- Safe to re-run.

-- 1. The target list.

CREATE TABLE IF NOT EXISTS rules_genre_expansions (
    genre_id INT NOT NULL,
    target_id INT NOT NULL,
    position INT NOT NULL DEFAULT 0,
    PRIMARY KEY (genre_id, target_id),
    KEY idx_rules_genre_expansions_target (target_id),
    CONSTRAINT fk_genre_expansions_genre FOREIGN KEY (genre_id) REFERENCES rules_genres(id) ON DELETE CASCADE,
    CONSTRAINT fk_genre_expansions_target FOREIGN KEY (target_id) REFERENCES rules_genres(id) ON DELETE CASCADE
);

-- 2. Existing single corrections become one-entry expansions, so there is one
--    place to read a rewrite from instead of two that can disagree.
--    A row pointing at itself is not a rewrite and is skipped.

INSERT IGNORE INTO rules_genre_expansions (genre_id, target_id, position)
SELECT id, canonical_id, 0
FROM rules_genres
WHERE canonical_id IS NOT NULL
  AND canonical_id <> id;

-- 3. Slash composites that nobody ever actually reviewed.
--
--    'Hardstyle/Hardcore' is two genres, but migrate_v3 whitened every row that
--    already existed, so these now count as decided and the tagger will not split
--    them. Only rows still marked decided_by = 'migration' are rewritten here: a
--    row a human has ruled on is left exactly as they left it.
--
--    The composite becomes a rejected genre that expands into its parts, which is
--    the same thing the tagger would have produced had it split the string.

DROP TEMPORARY TABLE IF EXISTS genre_slash_parts;
CREATE TEMPORARY TABLE genre_slash_parts (
    genre_id INT NOT NULL,
    position INT NOT NULL,
    part VARCHAR(255) NOT NULL,
    normalized_part VARCHAR(191) NOT NULL,
    PRIMARY KEY (genre_id, position),
    KEY (normalized_part)
);

-- Five is the practical ceiling for how many genres get crammed into one string;
-- anything longer stays untouched and shows up for curation instead.
INSERT INTO genre_slash_parts (genre_id, position, part, normalized_part)
SELECT g.id,
       n.n - 1,
       TRIM(SUBSTRING_INDEX(SUBSTRING_INDEX(g.name, '/', n.n), '/', -1)),
       TRIM(REGEXP_REPLACE(LOWER(SUBSTRING_INDEX(SUBSTRING_INDEX(g.name, '/', n.n), '/', -1)), '[^a-z0-9]+', ' '))
FROM rules_genres g
JOIN (SELECT 1 AS n UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5) n
  ON n.n <= 1 + LENGTH(g.name) - LENGTH(REPLACE(g.name, '/', ''))
WHERE g.name LIKE '%/%'
  AND g.decided_by = 'migration'
  AND 1 + LENGTH(g.name) - LENGTH(REPLACE(g.name, '/', '')) <= 5
  AND TRIM(REGEXP_REPLACE(LOWER(SUBSTRING_INDEX(SUBSTRING_INDEX(g.name, '/', n.n), '/', -1)), '[^a-z0-9]+', ' ')) <> '';

SELECT CONCAT('Splitting ', COUNT(DISTINCT genre_id), ' slash-separated genres into ', COUNT(*), ' parts') AS migration_note
FROM genre_slash_parts;

-- Each part becomes a genre in its own right, approved because the composite was.
INSERT IGNORE INTO rules_genres (name, normalized_name, state, decided_by, decided_at)
SELECT part, normalized_part, 'white', 'migration', NOW()
FROM genre_slash_parts;

-- A part that was already sitting in the queue is approved by the same reasoning:
-- the composite it came from was whitelisted, so the genre inside it was too.
-- Only rows nobody has ever ruled on are touched.
UPDATE rules_genres t
JOIN genre_slash_parts p ON p.normalized_part = t.normalized_name
SET t.state = 'white', t.decided_by = 'migration', t.decided_at = NOW()
WHERE t.state = 'unknown'
  AND t.decided_by IS NULL
  AND t.id <> p.genre_id;

INSERT IGNORE INTO rules_genre_expansions (genre_id, target_id, position)
SELECT p.genre_id, t.id, p.position
FROM genre_slash_parts p
JOIN rules_genres t ON t.normalized_name = p.normalized_part
WHERE t.id <> p.genre_id;

UPDATE rules_genres g
SET g.state = 'black'
WHERE g.id IN (SELECT genre_id FROM genre_slash_parts)
  AND g.decided_by = 'migration';

DROP TEMPORARY TABLE genre_slash_parts;

SELECT CONCAT('Genre rewrites now stored as expansions: ', COUNT(*)) AS migration_note
FROM rules_genre_expansions;
