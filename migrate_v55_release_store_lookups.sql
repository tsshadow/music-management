-- migrate_v55_release_store_lookups.sql
--
-- Release info enrichment (docs/designs/release-info-enrichment/). A scene release's .nfo links
-- its album at a store far more often than it states a release date: 4.514 of the 6.546 .nfo
-- files in the import queue on 2026-10-02 link Deezer. The importer asks Deezer's public album
-- API once per album and keeps the answer here; the tagger only reads it, so a retag never goes
-- over the network.
--
--   status       -- 'ok' (the album exists) or 'not_found' (gone; asked again after 30 days).
--                   A transient failure is not stored at all.
--   release_date -- as the store gives it, `YYYY-MM-DD`; the tagger writes it to ORIGINALDATE
--                   with DATE_SOURCE=deezer when its year matches the release.
--   label        -- the store's label name; the importer maps it onto an existing label folder.
--   upc          -- the UPC/EAN; written to BARCODE, never used as a catalogue number.
--
-- Re-runnable and expand-only: CREATE TABLE IF NOT EXISTS, nothing is seeded, nothing the
-- running release reads is touched.

CREATE TABLE IF NOT EXISTS release_store_lookups (
    store VARCHAR(16) NOT NULL,
    album_id VARCHAR(64) NOT NULL,
    status ENUM('ok', 'not_found') NOT NULL,
    label VARCHAR(255) NULL,
    upc VARCHAR(32) NULL,
    release_date VARCHAR(10) NULL,
    title VARCHAR(255) NULL,
    fetched_at DATETIME NOT NULL,
    PRIMARY KEY (store, album_id)
);
