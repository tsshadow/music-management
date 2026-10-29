-- rules_genres: YouTube video categories, decided black so they never reach genre curation.
--
-- From migrate_v7_youtube_category_genres.sql, step 1, verbatim. yt-dlp writes a YouTube video's
-- category ('Music', 'Film & Animation') as its genre; the downloader strips it now, and these
-- rows make ResolveGenreRule drop it from files tagged before that. The halves are listed too,
-- because CleanTagsRule once split a genre on ' & '.
--
-- Left out, because they repair rows a new database never has: step 2 (a category already
-- waiting in curation becomes black) and step 3 (mark the YouTube tree for a rescan).
-- migrate_v3_genre_states.sql and migrate_v4_genre_expansions.sql insert rules_genres rows too,
-- but only from legacy tables and composite names, which are empty on a new database.
--
-- The scratch table is TEMPORARY and lives only on this connection. INSERT IGNORE on the unique
-- normalized_name, so a re-run adds nothing and a genre a curator changed keeps its state.

DROP TEMPORARY TABLE IF EXISTS tmp_youtube_categories;
CREATE TEMPORARY TABLE IF NOT EXISTS tmp_youtube_categories (
    name VARCHAR(255) NOT NULL,
    normalized_name VARCHAR(191) NOT NULL PRIMARY KEY
) DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

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

INSERT IGNORE INTO rules_genres (name, normalized_name, state, decided_by, decided_at)
SELECT name, normalized_name, 'black', 'migration', NOW()
FROM tmp_youtube_categories;

DROP TEMPORARY TABLE IF EXISTS tmp_youtube_categories;
