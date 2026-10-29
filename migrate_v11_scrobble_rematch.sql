-- Scrobble rematching: normalized keys to match on, and a record of how.
--
-- A listen was linked to a track by exact equality on two strings. Measured on
-- production 2026-08-17 that left 16.830 matched against 35.761 unmatched, and
-- the loss is almost entirely in imported history: live LMS loses 6%, the
-- ListenBrainz import 73%. Same music, different system's spelling.
--
-- Design: docs/superpowers/specs/2026-08-21-scrobble-rematching-design.md

-- Normalized keys, indexed, so the middle tiers are lookups rather than scans.
-- 191 is the indexable VARCHAR length under utf8mb4; rules_festivals uses the
-- same. The worker fills these -- see the "columns heal themselves" section of
-- the spec -- so nothing here depends on every writer remembering to.
ALTER TABLE library_artists
    ADD COLUMN IF NOT EXISTS normalized_name VARCHAR(191);
ALTER TABLE library_artists
    ADD INDEX IF NOT EXISTS idx_artists_normalized_name (normalized_name);

ALTER TABLE library_tracks
    ADD COLUMN IF NOT EXISTS normalized_title VARCHAR(191);
ALTER TABLE library_tracks
    ADD COLUMN IF NOT EXISTS normalized_base_title VARCHAR(191);
ALTER TABLE library_tracks
    ADD INDEX IF NOT EXISTS idx_tracks_normalized_title (normalized_title);
ALTER TABLE library_tracks
    ADD INDEX IF NOT EXISTS idx_tracks_normalized_base_title (normalized_base_title);

-- How a listen came to be linked. Existing rows are exact matches, which is what
-- the default says. A tier that turns out to be wrong is removable with one
-- DELETE on this column without touching anything the other tiers found.
ALTER TABLE scrobble_listens
    ADD COLUMN IF NOT EXISTS match_method
    ENUM('exact', 'normalized', 'base_title', 'fuzzy') NOT NULL DEFAULT 'exact';
ALTER TABLE scrobble_listens
    ADD COLUMN IF NOT EXISTS match_score TINYINT UNSIGNED NULL;
ALTER TABLE scrobble_listens
    ADD INDEX IF NOT EXISTS idx_listens_match_method (match_method);

-- Without these the worker re-runs the whole fuzzy pass over the same hopeless
-- rows every cycle, forever, for music that was never downloaded.
ALTER TABLE scrobble_unmatched_listens
    ADD COLUMN IF NOT EXISTS attempts INT NOT NULL DEFAULT 0;
ALTER TABLE scrobble_unmatched_listens
    ADD COLUMN IF NOT EXISTS last_attempt_at TIMESTAMP NULL;
ALTER TABLE scrobble_unmatched_listens
    ADD INDEX IF NOT EXISTS idx_unmatched_retry (last_attempt_at, attempts);
