-- migrate_v34_primary_artist_and_listen_track_indexes.sql
--
-- Two join columns that were never indexed.
--
-- library_tracks.primary_artist_id: every tier of scrobble_rematch.find_track joins
-- `library_artists a ON t.primary_artist_id = a.id`, and so do the analytics artist filter, the
-- top-artists statistic and the feed candidates. With no index each of those scans library_tracks
-- from the artist side. The column has no foreign key either, so InnoDB
-- never created one implicitly.
--
-- scrobble_listens.track_id: migrate_v20 claimed an index on it already existed "from the rematch
-- migration"; migrate_v11 only ever added idx_listens_match_method. The UNIQUE key leads on
-- username, so per-track questions (play counts, a track's history) scanned the table. Ending
-- with username lets the per-user variant of the same question stay inside the index.
--
-- Mirrors services/common/db_init.py and scrobbler.init_db. Re-runnable: IF NOT EXISTS.
ALTER TABLE library_tracks
    ADD INDEX IF NOT EXISTS idx_tracks_primary_artist (primary_artist_id);

ALTER TABLE scrobble_listens
    ADD INDEX IF NOT EXISTS idx_listens_track_user (track_id, username);
