-- downloads_youtube_archive never recorded when a video was archived.
--
-- The SoundCloud archive has carried `added_at` from the start; the YouTube table on
-- production predates the column that db_init.py now creates, so "when did this channel
-- last deliver anything" could not be answered for YouTube at all. The coverage page
-- (docs/designs/channel-coverage) reads MAX(added_at) per channel as "last download".
--
-- Two statements on purpose. `ADD COLUMN ... DEFAULT CURRENT_TIMESTAMP` fills every existing
-- row with the moment of the ALTER, and 53.658 videos would then read as downloaded on
-- deploy day -- a throughput spike that never happened. Added without a default, the rows
-- that predate the column stay NULL, which the page shows as "onbekend"; the default is
-- attached afterwards for every row inserted from now on. Both statements are re-runnable.
ALTER TABLE downloads_youtube_archive ADD COLUMN IF NOT EXISTS added_at DATETIME NULL;
ALTER TABLE downloads_youtube_archive ALTER COLUMN added_at SET DEFAULT CURRENT_TIMESTAMP;
