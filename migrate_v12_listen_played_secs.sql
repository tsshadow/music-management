-- migrate_v12_listen_played_secs.sql
--
-- Adds the number of seconds a track was actually played to both listen tables.
--
-- Until now a listen recorded only that something was played, never for how long. LMS already
-- receives the played duration from the player and discarded it before building its payload, so
-- "minutes listened" was not answerable. It matters here more than it would elsewhere: the average
-- track in this library is 939 seconds, because most of it is DJ sets and radio shows, so
-- multiplying plays by track length overstates listening time by a wide and unpredictable margin.
--
-- NULL is the honest value for every existing row and for any client that does not report it. It
-- must not be read as zero.
--
-- Idempotent: re-running is a no-op. `music_manager.routers.scrobbler.init_db` performs the same
-- two additions at startup, so a stack that never runs this file still converges.
--
-- Usage:
--   mysql -h <host> -u <user> -p <database> < migrate_v12_listen_played_secs.sql

SET @ddl := (
    SELECT IF(
        COUNT(*) = 0,
        'ALTER TABLE scrobble_listens ADD COLUMN played_secs INT UNSIGNED NULL',
        'SELECT "scrobble_listens.played_secs already present"'
    )
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'scrobble_listens'
      AND column_name = 'played_secs'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl := (
    SELECT IF(
        COUNT(*) = 0,
        'ALTER TABLE scrobble_unmatched_listens ADD COLUMN played_secs INT UNSIGNED NULL',
        'SELECT "scrobble_unmatched_listens.played_secs already present"'
    )
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'scrobble_unmatched_listens'
      AND column_name = 'played_secs'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
