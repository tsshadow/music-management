-- Genre curation advice (Beheer -> Genre Curatie, routers/genre_curation.py).
--
-- `rules_genre_proposals` holds what the last analysis run suggested for each genre
-- still in the curation queue: the kind of advice, the approved genres it would be
-- rewritten to (JSON `[{id, name}]`), the reasoning in words and a confidence. It is
-- rewritten whole on every run. The decision itself stays where it was -- the state
-- on rules_genres plus rules_genre_expansions -- and a run never touches it.
--
-- Safe to re-run: scripts/deploy.sh applies every migrate_*.sql on every deploy.

CREATE TABLE IF NOT EXISTS rules_genre_proposals (
    genre_id INT NOT NULL PRIMARY KEY,
    kind ENUM('keep', 'rewrite', 'split', 'reject', 'unknown') NOT NULL,
    targets TEXT NULL,
    evidence TEXT NULL,
    confidence INT NOT NULL DEFAULT 0,
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX(kind),
    FOREIGN KEY (genre_id) REFERENCES rules_genres(id) ON DELETE CASCADE
);
