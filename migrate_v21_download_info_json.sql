-- Keep what yt-dlp knew about a download, instead of throwing it away.
--
-- The postprocessors hand a full info dict to the tagger, which copies four fields out
-- of it (artist, title, genre, upload_date -- see BaseSong._apply_extra_info) and lets
-- the rest go when the process moves on. Nothing writes it down. So SoundCloud's
-- `genre`, `tags` and `description`, YouTube's music-credit `artists`/`track`/`album`/
-- `release_year`, and the chapter list of a two-hour set are gone the moment the
-- download finishes -- across 53.295 YouTube and 157.387 SoundCloud rows.
--
-- Getting it back afterwards is not free: SoundCloud would need one
-- `yt-dlp --dump-single-json` per track, and that side answers a burst with 403.
-- So this is forward-only. Every existing row stays NULL.
--
-- LONGTEXT rather than a JSON column: MariaDB's JSON is an alias for LONGTEXT with a
-- validity CHECK, and a strict check would turn one malformed blob from an extractor
-- into a failed insert -- which would lose the archive row, not just its metadata.
-- JSON_EXTRACT reads a LONGTEXT column perfectly well.
--
-- The stored blob is pruned first (services/downloader/info_json.py): formats,
-- thumbnails and automatic_captions are transport detail that expires within hours and
-- account for nearly all of the 100-800 KB a raw YouTube dict weighs. What is left runs
-- 5-15 KB, with a hard ceiling in that module.
--
-- Mirrors the ALTERs in services/common/db_init.py, which is what a fresh stack runs;
-- this file is what production runs.
ALTER TABLE downloads_soundcloud_archive
    ADD COLUMN IF NOT EXISTS info_json LONGTEXT NULL;

ALTER TABLE downloads_youtube_archive
    ADD COLUMN IF NOT EXISTS info_json LONGTEXT NULL;
