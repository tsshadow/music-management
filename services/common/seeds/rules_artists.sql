-- rules_artists: the promo markers recorded as decisions, so artist curation shows them under
-- "Afgekeurd" instead of offering them for a decision.
--
-- From migrate_v26_artist_curation.sql, which copied every row of rules_ignored_artists into
-- rules_artists as a black 'legacy-redirect' decision. On a new database the only rows there are
-- the eleven markers from rules_ignored_artists.sql, so this seed copies those eleven and nothing
-- else. Not verbatim: the migration's unbounded SELECT, run on every start, would also turn each
-- name a curator or a tool adds to rules_ignored_artists later into a 'legacy-redirect' decision.
-- Runs after rules_ignored_artists.sql. INSERT IGNORE on the primary key name, so a decision
-- taken through the page since stays as it is.
INSERT IGNORE INTO rules_artists (name, state, canonical_name, decided_by)
SELECT name, 'black', NULLIF(TRIM(corrected_name), ''), 'legacy-redirect'
FROM rules_ignored_artists
WHERE name IN (
    'Premiere', 'Premier', 'Free Download', 'Free DL', 'Preview', 'Out Now', 'Available Now',
    'Teaser', 'Livestream', 'Video', 'Free'
);
