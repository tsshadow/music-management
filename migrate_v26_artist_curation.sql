-- Artist curation (Beheer -> Artiestcuratie, routers/artist_curation.py).
--
-- `rules_artists` records the human decision per name: white keeps it, black drops it
-- from tags, black with canonical_name rewrites it. The tagger keeps reading
-- rules_ignored_artists; the API mirrors every decision into it. `rules_artist_proposals`
-- holds what the last analysis run suggested for each undecided name and is rewritten
-- whole on every run -- a decision never lives there.
--
-- Safe to re-run: scripts/deploy.sh applies every migrate_*.sql on every deploy.

CREATE TABLE IF NOT EXISTS rules_artists (
    name VARCHAR(255) NOT NULL PRIMARY KEY,
    state ENUM('white', 'black') NOT NULL,
    canonical_name VARCHAR(255) NULL,
    decided_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    decided_by VARCHAR(64) NULL,
    INDEX(state)
);

CREATE TABLE IF NOT EXISTS rules_artist_proposals (
    name VARCHAR(255) NOT NULL PRIMARY KEY,
    kind ENUM('keep', 'rewrite', 'split', 'reject', 'unknown') NOT NULL,
    target VARCHAR(512) NULL,
    evidence TEXT NULL,
    confidence INT NOT NULL DEFAULT 0,
    junk_score INT NOT NULL DEFAULT 0,
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX(kind)
);

-- The 2.658 hand-written redirects are decisions already made: a name with a correction
-- is a rewrite, one without is a rejection. Record them once so the page shows them under
-- "Afgekeurd" rather than offering them for a second decision. INSERT IGNORE so a re-run
-- never overwrites a decision taken through the page since.
INSERT IGNORE INTO rules_artists (name, state, canonical_name, decided_by)
SELECT name, 'black', NULLIF(TRIM(corrected_name), ''), 'legacy-redirect'
FROM rules_ignored_artists;
