-- migrate_v33_listened_at_no_on_update.sql
--
-- Stops `listened_at` from moving to "now" whenever a scrobble row is updated.
--
-- Both scrobble tables were created (2026-07-04, MariaDB 10.6) with `listened_at TIMESTAMP NOT
-- NULL` as their first TIMESTAMP column and no DEFAULT. Under explicit_defaults_for_timestamp=OFF,
-- the default before MariaDB 10.10, such a column silently becomes
--
--     DEFAULT current_timestamp() ON UPDATE current_timestamp()
--
-- and the attribute survives every later server upgrade. So every UPDATE of a row rewrote the
-- moment the listen happened:
--
--   * scrobble_rematch.rematch_once stamps each miss (`attempts = attempts + 1`), once per retry
--     window, for every unmatched listen;
--   * the ON DUPLICATE KEY UPDATE in routers/scrobbler.py and scrobble_rematch.record_match fires
--     it whenever played_secs or the match method changes;
--   * the account merge in routers/users.py repoints `username`.
--
-- Two unmatched listens of the same track by the same user that miss in the same second end up
-- with the same listened_at and collide on the UNIQUE key -- the 1062 "Duplicate entry
-- 'teun-2026-08-21 21:02:05-ISAB-...' for key 'username'" seen on the first rematch pass after
-- 0.23.0. See docs/bug-reports/039-listened-at-rewritten-on-every-rematch.md, which also says how
-- to estimate the damage already done. This file stops it; it does not repair values.
--
-- Conditional rather than a bare MODIFY: the UNIQUE key on scrobble_unmatched_listens is past the
-- index length limit and is therefore a HASH key, which rules out ALGORITHM=INSTANT/INPLACE, so an
-- unconditional MODIFY would copy the table on every deploy (scripts/deploy.sh applies every
-- migrate_*.sql each time). Once the attribute is gone this is a no-op.
--
-- Mirrors scrobbler.init_db, which does the same on start-up for stacks that never run this.

SET @ddl := (
    SELECT IF(
        COUNT(*) > 0,
        'ALTER TABLE scrobble_listens MODIFY listened_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP',
        'SELECT "scrobble_listens.listened_at has no ON UPDATE"'
    )
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'scrobble_listens'
      AND column_name = 'listened_at'
      AND LOWER(extra) LIKE '%on update%'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl := (
    SELECT IF(
        COUNT(*) > 0,
        'ALTER TABLE scrobble_unmatched_listens MODIFY listened_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP',
        'SELECT "scrobble_unmatched_listens.listened_at has no ON UPDATE"'
    )
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'scrobble_unmatched_listens'
      AND column_name = 'listened_at'
      AND LOWER(extra) LIKE '%on update%'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
