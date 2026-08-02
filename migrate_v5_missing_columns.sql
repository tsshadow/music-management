-- migrate_v5_missing_columns.sql
--
-- Adds three columns the running code selects but that CREATE TABLE IF NOT
-- EXISTS never added to databases where the table already existed. Both gaps
-- were found by tests/integration/test_router_sql.py, which runs every
-- endpoint's SQL against a freshly built schema:
--
--   * GET /api/youtube          -> Unknown column 'channel_id'
--                                  (services/music_manager/routers/management.py)
--     POST /api/youtube writes download_type, which was missing for the same reason.
--   * GET /api/system/activity  -> Unknown column 'ml.updated_at'
--
-- services/common/db_init.py applies the same ALTERs on start-up; this file is
-- what brings an already-deployed database up to date, since scripts/deploy.sh
-- runs every migrate_*.sql on each deploy.
--
-- Re-runnable: ADD COLUMN IF NOT EXISTS is a no-op the second time.

ALTER TABLE downloads_youtube_accounts
    ADD COLUMN IF NOT EXISTS channel_id VARCHAR(255);

ALTER TABLE downloads_youtube_accounts
    ADD COLUMN IF NOT EXISTS download_type VARCHAR(50) DEFAULT 'audio';

ALTER TABLE library_track_ml_labels
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;
