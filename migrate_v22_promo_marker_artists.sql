-- Promo markers are not artists.
--
-- SoundCloud titles carry a marker in front of the actual credit -- "PREMIERE ｜ TARS - Rumble
-- [NNVA03]", "FREE DOWNLOAD - Exilles - Crude Definition". The artist rules read the title in
-- segments and pick the segment that best matches a name in library_artists. Once a marker has
-- won that contest a single time it *is* in library_artists, so from then on it matches itself
-- perfectly and wins every following title: measured on production, 9.188 tracks were filed under
-- "Premiere", 329 under "FREE DOWNLOAD", 43 under "PREVIEW". For 3.874 of those the real artist is
-- still sitting in the title where the rule left it.
--
-- Listing them here is the curation's own vocabulary for "this is not an artist": a row without a
-- corrected_name means remove. What made the list ineffective for these names is that the rules
-- only consulted it *after* library_artists, and every one of these names is in library_artists.
-- InferArtistFromTitleRule now subtracts the uncorrected ignore list from the names it is allowed
-- to match, so a marker can no longer be selected out of a title at all, and the segment holding
-- the real artist gets its turn.
--
-- Data only, and nothing is deleted. The library_artists rows stay where they are -- their tracks
-- keep the artist they have until the tagger's deep run re-reads each file and the corrected rules
-- pick the artist the title actually names. Removing an artist row here would also orphan
-- library_tracks.primary_artist_id and library_works.primary_artist_id, which no foreign key
-- protects.
--
-- The anti-join rather than INSERT IGNORE: production has a unique index on `name`, but the
-- CREATE TABLE in services/common/db_init.py -- what a fresh stack runs -- declares a plain
-- INDEX(name). IGNORE would silently insert a second copy of every row there, and the deploy
-- applies each migration twice. This form is idempotent on both schemas.
INSERT INTO rules_ignored_artists (name, corrected_name)
SELECT marker.name, NULL
FROM (
    -- One spelling per name. The column collates utf8mb4_general_ci and every lookup lowercases,
    -- so 'FREE DOWNLOAD' and 'Free Download' are the same row -- listing both makes the statement
    -- collide with itself on the unique index the first time it runs.
    SELECT 'Premiere' AS name
    UNION ALL SELECT 'Premier'
    UNION ALL SELECT 'Free Download'
    UNION ALL SELECT 'Free DL'
    UNION ALL SELECT 'Preview'
    UNION ALL SELECT 'Out Now'
    UNION ALL SELECT 'Available Now'
    UNION ALL SELECT 'Teaser'
    UNION ALL SELECT 'Livestream'
    UNION ALL SELECT 'Video'
    UNION ALL SELECT 'Free'
) AS marker
LEFT JOIN rules_ignored_artists existing ON existing.name = marker.name
WHERE existing.id IS NULL;
