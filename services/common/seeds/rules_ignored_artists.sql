-- rules_ignored_artists: promo markers in SoundCloud titles that are not artists.
--
-- From migrate_v22_promo_marker_artists.sql, verbatim. A row without a corrected_name means
-- "remove this name". InferArtistFromTitleRule subtracts the uncorrected names from the names it
-- may match, so "PREMIERE | TARS - Rumble" cannot be filed under "Premiere".
--
-- The anti-join rather than INSERT IGNORE: production has a unique index on `name`, but a schema
-- with a plain INDEX(name) would take a second copy of every row from IGNORE. This form inserts
-- nothing on a second run on either schema, and leaves a row a curator changed as it is.
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
