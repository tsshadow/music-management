-- Indexes for reading listening history back, which nothing did until /api/listening.
--
-- Both tables already carry a unique key leading on `username`, which serves "my
-- listens between two dates" perfectly. It does nothing for the other question the
-- statistics page asks: "everybody's listens between two dates", where there is no
-- username to seek on and MariaDB falls back to a full scan of both tables.
--
-- At 20.299 + 33.461 rows a scan is cheap and this changes little today. It is here
-- because the page runs six of these queries per view and the tables only ever grow;
-- the write path is a handful of inserts per hour, so the extra index costs nothing
-- worth measuring on that side.
--
-- No index on track_id is added. `scrobble_listens` already has one from the rematch
-- migration, and a date-filtered GROUP BY track_id cannot use a filtering index and a
-- grouping index at the same time -- adding more would be guessing at a plan rather
-- than reading one.
--
-- Mirrors the ALTERs in services/music_manager/routers/scrobbler.py init_db, which is
-- what a fresh stack runs; this file is what production runs.
ALTER TABLE scrobble_listens
    ADD INDEX IF NOT EXISTS idx_listens_listened_at (listened_at);

ALTER TABLE scrobble_unmatched_listens
    ADD INDEX IF NOT EXISTS idx_unmatched_listened_at (listened_at);
