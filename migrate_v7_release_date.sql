-- migrate_v7_release_date.sql
--
-- Voegt de releasedatum met dag-precisie toe.
--
-- `rules_scene_group_date_format` is de overridetabel voor scene-groepen die
-- hun datums als M-D-Y schrijven in plaats van D-M-Y. Leeg is een geldige
-- toestand: zonder rij voor een groep geldt de positieregel uit
-- services/tagger/Song/NfoDate.py.
--
-- `library_track_audio_features.release_date` komt naast `release_year` te
-- staan, niet in plaats daarvan: de jaarfilters en het jaarhistogram in
-- services/music_manager/routers/analytics.py rekenen op die kolom.
--
-- Re-runnable: elke stap kijkt eerst naar de huidige vorm van het schema.

-- ---------------------------------------------------------------------------
-- 1. rules_scene_group_date_format
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS rules_scene_group_date_format (
    scene_group VARCHAR(64) NOT NULL PRIMARY KEY,
    date_format VARCHAR(8) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- 2. release_date naast release_year
-- ---------------------------------------------------------------------------
-- De waarde is een partiële datumstring: '2026', '2026-01' of '2026-01-16'.
-- De precisie zit in de lengte, dus er is geen aparte precisiekolom nodig.

SET @column_exists := (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'library_track_audio_features'
      AND column_name = 'release_date'
);
SET @statement := IF(@column_exists = 0,
    'ALTER TABLE library_track_audio_features ADD COLUMN release_date VARCHAR(10)',
    'DO 0');
PREPARE stmt FROM @statement;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
