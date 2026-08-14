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
-- Both the full category names and their halves are listed, because CleanTagsRule
-- runs ARTIST_REGEX over the genre tag and that splits on ' & ': 'Film & Animation'
-- reaches curation as 'Film' and 'Animation', never as itself.
--
-- A category that somebody has already ruled on is left alone -- only rows still
-- sitting at 'unknown' are decided here.
--
-- Safe to re-run.

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

-- 2. Categories already in the curation queue.

UPDATE rules_genres g
JOIN tmp_youtube_categories c ON c.normalized_name = g.normalized_name
SET g.state = 'black',
    g.decided_by = COALESCE(g.decided_by, 'migration'),
    g.decided_at = COALESCE(g.decided_at, NOW())
WHERE g.state = 'unknown';

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
-- management, because nothing outside it changed.
--
-- Guarded on the table existing: it is created by Tagger.__init__, so a database
-- where the tagger has never run does not have it yet and does not need this.

SET @rescan := IF(
    (SELECT COUNT(*) FROM information_schema.tables
     WHERE table_schema = DATABASE() AND table_name = 'tagger_processed_files') > 0,
    'UPDATE tagger_processed_files SET needs_rescan = TRUE WHERE filepath LIKE ''%/Youtube/%''',
    'SELECT ''tagger_processed_files does not exist yet; nothing to rescan''');

PREPARE stmt FROM @rescan;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
