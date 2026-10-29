-- Proposals for releases the importer could not place. See
-- docs/superpowers/specs/2026-08-19-label-proposals-design.md
--
-- `folder` is unique so a later import cycle refreshes the row instead of adding a
-- second one. `catid` is nullable because "no catalogue number in the name at all" is
-- one of the two ways a release ends up here, and that case can never produce a
-- rules_catid_label rule.
CREATE TABLE IF NOT EXISTS rules_label_proposals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    folder VARCHAR(255) NOT NULL UNIQUE,
    catid VARCHAR(255) NULL,
    proposed_label VARCHAR(255) NULL,
    source VARCHAR(64) NOT NULL DEFAULT 'none',
    confidence INT NOT NULL DEFAULT 0,
    status ENUM('new', 'confirmed', 'rejected', 'stale') NOT NULL DEFAULT 'new',
    decided_label VARCHAR(255) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    decided_at TIMESTAMP NULL,
    INDEX(status),
    INDEX(catid)
);
