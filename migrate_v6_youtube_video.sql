-- migrate_v6_youtube_video.sql
--
-- Maakt de video-tak van de YouTube-downloader mogelijk.
--
-- `downloads_youtube_accounts.download_type` bestaat op productie al als
-- ENUM('audio','video') en is daar deel van de primaire sleutel, maar een
-- database die door services/common/db_init.py is opgebouwd heeft alleen
-- `name VARCHAR(255) PRIMARY KEY` en een losse VARCHAR-kolom. Die twee vormen
-- worden hier gelijkgetrokken.
--
-- `downloads_youtube_archive` heeft op productie `video_id` als enige primaire
-- sleutel. Eén video past er dus één keer in, terwijl zeven kanalen zowel een
-- audio- als een video-regel hebben: wie het eerst komt zou de ander permanent
-- blokkeren. De sleutel wordt daarom (video_id, download_type).
--
-- Re-runnable: elke stap kijkt eerst naar de huidige vorm van het schema.

-- ---------------------------------------------------------------------------
-- 1. downloads_youtube_accounts
-- ---------------------------------------------------------------------------

ALTER TABLE downloads_youtube_accounts
    ADD COLUMN IF NOT EXISTS channel_id VARCHAR(255);

ALTER TABLE downloads_youtube_accounts
    ADD COLUMN IF NOT EXISTS download_type VARCHAR(50) NOT NULL DEFAULT 'audio';

ALTER TABLE downloads_youtube_accounts
    ADD COLUMN IF NOT EXISTS active TINYINT(1) NOT NULL DEFAULT 1;

-- 60 seconden is de ondergrens die _match_filter tot nu toe hardcodeerde.
ALTER TABLE downloads_youtube_accounts
    ADD COLUMN IF NOT EXISTS min_duration INT DEFAULT 60;

ALTER TABLE downloads_youtube_accounts
    ADD COLUMN IF NOT EXISTS output_folder_override VARCHAR(255);

-- Een lege of NULL waarde is audio; anders faalt de MODIFY naar NOT NULL.
UPDATE downloads_youtube_accounts
SET download_type = 'audio'
WHERE download_type IS NULL OR download_type NOT IN ('audio', 'video');

ALTER TABLE downloads_youtube_accounts
    MODIFY COLUMN download_type ENUM('audio', 'video') NOT NULL DEFAULT 'audio';

-- Eén kanaal kan zowel audio als video zijn, dus de naam alleen is geen sleutel.
-- Alleen aanpassen wanneer de sleutel nog uit `name` alleen bestaat; op productie
-- is dit al gebeurd en blijft deze stap een no-op.
SET @accounts_pk := (
    SELECT GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX)
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'downloads_youtube_accounts'
      AND INDEX_NAME = 'PRIMARY'
);
SET @accounts_sql := IF(
    @accounts_pk = 'name',
    'ALTER TABLE downloads_youtube_accounts DROP PRIMARY KEY, ADD PRIMARY KEY (name, download_type)',
    'DO 0'
);
PREPARE stmt FROM @accounts_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ---------------------------------------------------------------------------
-- 2. downloads_youtube_archive
-- ---------------------------------------------------------------------------

ALTER TABLE downloads_youtube_archive
    ADD COLUMN IF NOT EXISTS download_type ENUM('audio', 'video') NOT NULL DEFAULT 'audio';

-- Alles wat er tot nu toe in staat is met FFmpegExtractAudio binnengekomen.
UPDATE downloads_youtube_archive
SET download_type = 'audio'
WHERE download_type IS NULL;

-- YoutubeArchive.insert schrijft `path`, maar db_init maakt die kolom niet aan.
ALTER TABLE downloads_youtube_archive
    ADD COLUMN IF NOT EXISTS path VARCHAR(255);

SET @archive_pk := (
    SELECT GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX)
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'downloads_youtube_archive'
      AND INDEX_NAME = 'PRIMARY'
);
SET @archive_sql := IF(
    @archive_pk = 'video_id',
    'ALTER TABLE downloads_youtube_archive DROP PRIMARY KEY, ADD PRIMARY KEY (video_id, download_type)',
    'DO 0'
);
PREPARE stmt FROM @archive_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Waar de tabel een eigen AUTO_INCREMENT-sleutel houdt (de db_init-vorm) doet een
-- unieke index hetzelfde werk: één video per type, niet één video totaal.
SET @archive_uniq := (
    SELECT COUNT(*)
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'downloads_youtube_archive'
      AND INDEX_NAME = 'uniq_video_id_download_type'
);
SET @archive_uniq_sql := IF(
    @archive_pk <> 'video_id' AND @archive_uniq = 0,
    'ALTER TABLE downloads_youtube_archive ADD UNIQUE KEY uniq_video_id_download_type (video_id, download_type)',
    'DO 0'
);
PREPARE stmt FROM @archive_uniq_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SELECT CONCAT(
    'YouTube-accounts: ',
    SUM(download_type = 'audio'), ' audio, ',
    SUM(download_type = 'video'), ' video'
) AS migration_note
FROM downloads_youtube_accounts;
