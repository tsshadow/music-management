-- Event- en logbeheer: één stroom met severity in plaats van losse meldingen.
--
-- De notifications-tabel kende alleen title, message en topic. Die rijen komen
-- als INFO-events terug, met de bron afgeleid van het topic. Daarna kan de
-- oude tabel weg: de ntfy-terugstroom die hem vulde bestaat niet meer.
--
-- Veilig om opnieuw te draaien.

-- 1. De nieuwe tabel.

CREATE TABLE IF NOT EXISTS events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    created_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
    level VARCHAR(10) NOT NULL,
    source VARCHAR(50) NOT NULL,
    logger VARCHAR(120),
    title VARCHAR(255),
    message TEXT,
    context JSON NULL,
    KEY idx_created (created_at),
    KEY idx_level_created (level, created_at),
    KEY idx_source_created (source, created_at)
);

-- 2. De bestaande meldingen overzetten.
--    Alleen wanneer notifications nog bestaat en events nog leeg is, zodat een
--    tweede run geen duplicaten oplevert.

SET @notifications_exists := (
    SELECT COUNT(*) FROM information_schema.tables
    WHERE table_schema = DATABASE() AND table_name = 'notifications'
);
SET @events_empty := (SELECT COUNT(*) = 0 FROM events);

SET @copy := IF(@notifications_exists > 0 AND @events_empty,
    'INSERT INTO events (created_at, level, source, logger, title, message, context)
     SELECT created_at, ''INFO'',
            CASE
                WHEN topic LIKE ''%soundcloud%'' OR topic LIKE ''%youtube%'' THEN ''downloader''
                WHEN topic LIKE ''%import%'' THEN ''importer''
                ELSE ''music-manager''
            END,
            NULL, title, message, NULL
     FROM notifications',
    'SELECT ''overslaan: notifications ontbreekt of events is al gevuld''');
PREPARE stmt FROM @copy;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 3. De oude tabel opruimen.

DROP TABLE IF EXISTS notifications;
