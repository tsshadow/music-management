-- YouTube video categories are not genres.
--
-- yt-dlp's FFmpegMetadataPP resolves the genre tag as
-- `genre -> genres -> categories -> tags`. The YouTube extractor sets neither of
-- the first two and always sets `categories`, so every downloaded music video
-- arrived tagged `genre=Music`, and anything without a category got the video's
-- keyword list instead. SoundCloud never hit this: its extractor supplies a real
-- genre, so the fallback chain stops before `categories`.
--
-- The downloader now strips both fields before the metadata is written
-- (services/downloader/youtube/DropCategoryGenre.py), which fixes new downloads.
-- This file deals with what is already on disk: marking the categories black
-- makes ResolveGenreRule drop them the next time the tagger walks the library,
-- instead of leaving one curation entry per category for a human to reject.
--
-- Both the full category names and their halves are listed. CleanTagsRule used to run
-- ARTIST_REGEX over the genre tag, which splits on ' & ': 'Film & Animation' reached
-- curation as 'Film' and 'Animation', never as itself, and files tagged back then still
-- carry the halves. Since bug report 045 genres are no longer split on ' & ', so a new
-- tag arrives whole and meets the full name's row.
--
-- A category that somebody has already ruled on is left alone -- only rows still
-- sitting at 'unknown' are decided here.
--
-- Safe to re-run, and since 0.68.1 cheap to re-run: scripts/deploy.sh applies every
-- migrate_*.sql on every deploy, and step 3 used to mark the whole YouTube tree for a
-- rescan each time -- 32.000 files, over an hour of tagging, on every deploy since this
-- file shipped. With the 0.67.0 queue model the tagger works that queue at full speed
-- right after start-up, and on 2026-09-19 that starved the API of the GIL until logins
-- timed out. Step 3 now only fires on the run that actually changed a category row.

CREATE TEMPORARY TABLE IF NOT EXISTS tmp_youtube_categories (
    name VARCHAR(255) NOT NULL,
    normalized_name VARCHAR(191) NOT NULL PRIMARY KEY
);

INSERT IGNORE INTO tmp_youtube_categories (name, normalized_name) VALUES
    ('Film & Animation',      'film animation'),
    ('Autos & Vehicles',      'autos vehicles'),
    ('Music',                 'music'),
    ('Pets & Animals',        'pets animals'),
    ('Sports',                'sports'),
    ('Travel & Events',       'travel events'),
    ('Gaming',                'gaming'),
    ('People & Blogs',        'people blogs'),
    ('Comedy',                'comedy'),
    ('Entertainment',         'entertainment'),
    ('News & Politics',       'news politics'),
    ('Howto & Style',         'howto style'),
    ('Education',             'education'),
    ('Science & Technology',  'science technology'),
    ('Nonprofits & Activism', 'nonprofits activism'),
    -- The halves ' & ' leaves behind.
    ('Film',        'film'),
    ('Animation',   'animation'),
    ('Autos',       'autos'),
    ('Vehicles',    'vehicles'),
    ('Pets',        'pets'),
    ('Animals',     'animals'),
    ('Travel',      'travel'),
    ('Events',      'events'),
    ('People',      'people'),
    ('Blogs',       'blogs'),
    ('News',        'news'),
    ('Politics',    'politics'),
    ('Howto',       'howto'),
    ('Style',       'style'),
    ('Science',     'science'),
    ('Technology',  'technology'),
    ('Nonprofits',  'nonprofits'),
    ('Activism',    'activism');

-- 1. Categories nobody has seen yet, so a later download cannot re-open them.

INSERT IGNORE INTO rules_genres (name, normalized_name, state, decided_by, decided_at)
SELECT name, normalized_name, 'black', 'migration', NOW()
FROM tmp_youtube_categories;

-- Rows this run really inserted. INSERT IGNORE reports only the ones that were new, so
-- on every deploy after the first this is 0.
SET @youtube_categories_inserted = ROW_COUNT();

-- 2. Categories already in the curation queue.

UPDATE rules_genres g
JOIN tmp_youtube_categories c ON c.normalized_name = g.normalized_name
SET g.state = 'black',
    g.decided_by = COALESCE(g.decided_by, 'migration'),
    g.decided_at = COALESCE(g.decided_at, NOW())
WHERE g.state = 'unknown';

SET @youtube_categories_decided = ROW_COUNT();

DROP TEMPORARY TABLE IF EXISTS tmp_youtube_categories;

-- 3. Ask the tagger to look at the YouTube tree again.
--
-- Steps 1 and 2 only change what the tagger would write; they do not make it
-- write anything. It skips a file whose mtime has not moved since the last run
-- (ProcessedFilesHelper.needs_processing), so without this every track already
-- on disk would keep both its category genre and its unsplit title, and the fix
-- would apply to new downloads only.
--
-- Scoped to the YouTube tree rather than using the 'rescan everything' button in
-- management, because nothing outside it changed. And only on a run in which step 1
-- or 2 decided a category: a deploy that changed no row has given the tagger nothing
-- new to write, so re-reading the tree would only cost the hour.
--
-- The table is normally created by Tagger.__init__ rather than db_init, so it is
-- ensured here first: on a database where the tagger has never run the UPDATE
-- would otherwise be an error rather than a no-op. The definition is the one in
-- ProcessedFilesHelper.

CREATE TABLE IF NOT EXISTS tagger_processed_files (
    filepath VARCHAR(767) PRIMARY KEY,
    mtime FLOAT,
    last_processed TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    needs_rescan BOOLEAN DEFAULT FALSE
);

UPDATE tagger_processed_files
SET needs_rescan = TRUE
WHERE filepath LIKE '%/Youtube/%'
  AND (@youtube_categories_inserted > 0 OR @youtube_categories_decided > 0);
