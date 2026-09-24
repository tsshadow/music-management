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
-- No index on track_id is added here. This comment used to say `scrobble_listens`
-- already had one "from the rematch migration"; it did not -- migrate_v11 only adds
-- idx_listens_match_method. migrate_v34 adds (track_id, username).
--
-- Note too that the UNIQUE key on scrobble_unmatched_listens is past the index length
-- limit and is therefore a HASH key: it enforces uniqueness but cannot serve a range
-- seek on (username, listened_at). idx_unmatched_listened_at below is the only index
-- a date range on that table can use.
--
-- Mirrors the ALTERs in services/music_manager/routers/scrobbler.py init_db, which is
-- what a fresh stack runs; this file is what production runs.
ALTER TABLE scrobble_listens
    ADD INDEX IF NOT EXISTS idx_listens_listened_at (listened_at);

ALTER TABLE scrobble_unmatched_listens
    ADD INDEX IF NOT EXISTS idx_unmatched_listened_at (listened_at);
