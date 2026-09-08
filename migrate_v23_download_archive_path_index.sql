-- Let the tagger find a download's info dict by the path it is holding.
--
-- migrate_v21 gave both archive tables an `info_json` column, and nothing read it: the
-- downloader wrote the blob and the tagger still retagged blind. The lookup it needs is
-- "what did yt-dlp say about the file at this absolute path", because the tagger walks
-- the filesystem and never learns a video id -- and neither table is indexed on the
-- column holding that path. Without an index that is a full scan of 157.393 SoundCloud
-- or 53.366 YouTube rows per file, in a round that touches hundreds of files.
--
-- The two tables disagree about which column that is: SoundCloud writes the absolute
-- path into `filename`, YouTube into `path` and the basename into `filename`. Indexing
-- what each one actually holds is cheaper than migrating a column that 210.759 rows and
-- two writers already agree on.
--
-- `filename` is TEXT on the SoundCloud side, so the index takes a 255-byte prefix. That
-- narrows the candidate set, it does not decide the match -- the `=` comparison still
-- reads the full column, so two paths sharing their first 255 bytes stay distinguishable.
--
-- Mirrors the index step in services/common/db_init.py, which is what a fresh stack runs;
-- this file is what production runs.
ALTER TABLE downloads_soundcloud_archive
    ADD INDEX IF NOT EXISTS idx_filename (filename(255));

ALTER TABLE downloads_youtube_archive
    ADD INDEX IF NOT EXISTS idx_path (path);
