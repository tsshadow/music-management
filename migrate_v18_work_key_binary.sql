-- migrate_v18_work_key_binary.sql
--
-- Makes `library_works.work_key` compare byte for byte.
--
-- The column was created with the table default, `utf8mb4_general_ci`, which gives every character
-- outside the Basic Multilingual Plane the same collation weight. Two keys built from such
-- characters therefore compare equal whenever they are the same length, and the UNIQUE key on
-- work_key then merges two unrelated songs into one work without erroring -- the same trap
-- migrate_v13 fixed for channels.normalized_name.
--
-- The key is already normalized in Python (`song_versions.work_key`, which lowercases, folds
-- accents and strips punctuation), so case folding by the database adds nothing and binary equality
-- is exactly the question being asked.
--
-- Tightening a collation can only split rows that used to compare equal; it can never create a new
-- UNIQUE collision, so this runs without a preparatory cleanup.
--
-- Run `python3 scripts/repair_song_works.py --dry-run` afterwards, then without the flag. That repairs the other half of the same
-- bug: a title that normalizes to nothing produced the key ':::' for every such track, which on
-- production collected 117 unrelated recordings into one work.
--
-- Idempotent: re-running is a no-op.
--
-- Usage:
--   mysql -h <host> -u <user> -p <database> < migrate_v18_work_key_binary.sql

SET @ddl := (
    SELECT IF(
        COUNT(*) = 0,
        'ALTER TABLE library_works MODIFY work_key VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL',
        'SELECT "library_works.work_key is already utf8mb4_bin"'
    )
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'library_works'
      AND column_name = 'work_key'
      AND collation_name = 'utf8mb4_bin'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
