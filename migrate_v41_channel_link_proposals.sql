-- migrate_v41_channel_link_proposals.sql
--
-- channel_link_proposals: a proposed link from a channel (SoundCloud/YouTube account folder) to
-- the label or artist it is, waiting for a curator to confirm or reject it. One row per
-- (channel, kind, target) whatever its status, so a rejected proposal stays rejected when the
-- search runs again. A confirmed row writes channels.label_id or channels.artist_id. See
-- docs/designs/channel-links/technical.md.
--
-- Kept identical to the CREATE TABLE in services/common/db_init.py. Re-runnable:
-- CREATE TABLE IF NOT EXISTS; the schema_migrations ledger (bug report 068) skips it once
-- applied, but it does not rely on that.
CREATE TABLE IF NOT EXISTS channel_link_proposals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    channel_id INT NOT NULL,
    kind ENUM('label', 'artist') NOT NULL,
    target_id INT NOT NULL,
    target_name VARCHAR(255) NOT NULL,
    source ENUM('name', 'alias', 'redirect') NOT NULL,
    status ENUM('new', 'confirmed', 'rejected', 'stale') NOT NULL DEFAULT 'new',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    decided_at TIMESTAMP NULL,
    decided_by VARCHAR(64) NULL,
    UNIQUE KEY uq_channel_link (channel_id, kind, target_id),
    INDEX idx_channel_link_status (status),
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE
);
