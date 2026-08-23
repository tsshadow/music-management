-- migrate_v13_channels_binary_collation.sql
--
-- Makes `channels.normalized_name` compare byte for byte.
--
-- The column was created with the table default, `utf8mb4_general_ci`, which gives every character
-- outside the Basic Multilingual Plane the same collation weight. Two names made of such characters
-- therefore compare equal whenever they are the same length -- and SoundCloud accounts styled with
-- mathematical alphanumeric symbols are exactly that. On production this merged seven channels into
-- four unrelated ones:
--
--     '𝙁𝙍𝘼𝙉𝙏𝙄𝘾' (7)  ==  '𝗕𝗔𝗗𝗞𝗜𝗖𝗞' (7)
--     '𝙎𝙋𝘼𝙍𝙆𝙕'  (6)  ==  '𝐊𝐈𝐑𝐄𝐀𝐋'  (6)
--     '𝙹𝚞𝚔𝚜𝚜'   (5)  ==  '𝐀𝐌𝐈𝐆𝐎'   (5)
--
-- The unique key silently kept the first of each pair and `INSERT IGNORE` dropped the rest, so the
-- second channel's tracks were linked to the first channel's row. Nothing errored; the count was
-- simply seven short.
--
-- `utf8mb4_bin` is the right comparison for this column: the value is already lowercased and
-- whitespace-collapsed in Python (`channels.normalize_channel_name`), so case folding by the
-- database adds nothing, and binary equality is exactly the question being asked.
--
-- After running this, rebuild the links -- they are derived from file paths and cheap to recreate:
--
--     DELETE FROM library_track_channels;
--     python3 scripts/backfill_channels.py
--
-- Idempotent: re-running is a no-op.
--
-- Usage:
--   mysql -h <host> -u <user> -p <database> < migrate_v13_channels_binary_collation.sql

SET @ddl := (
    SELECT IF(
        COUNT(*) = 0,
        'SELECT "channels.normalized_name is already utf8mb4_bin"',
        'ALTER TABLE channels MODIFY normalized_name VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL'
    )
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'channels'
      AND column_name = 'normalized_name'
      AND collation_name = 'utf8mb4_bin'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
