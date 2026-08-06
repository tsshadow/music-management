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
--    De kopie draait zolang notifications nog bestaat -- verder niets. Een gate op
--    een lege events-tabel is bewust weggelaten: de applicatie maakt events al bij
--    het opstarten aan en vult hem meteen (zie events.init_db en EventService), dus
--    zo'n gate zou de oude rijen stilletjes weggooien zodra de app draait vóórdat
--    deze migratie gedraaid is -- en dat is bij een gewone compose-deploy eerder
--    regel dan uitzondering. Herhaald draaien is alsnog veilig: na een geslaagde
--    run is notifications weg (stap 3), dus een tweede run neemt de no-op-tak en
--    de DROP hieronder is zelf ook idempotent.

SET @notifications_exists := (
    SELECT COUNT(*) FROM information_schema.tables
    WHERE table_schema = DATABASE() AND table_name = 'notifications'
);

SET @copy := IF(@notifications_exists > 0,
    'INSERT INTO events (created_at, level, source, logger, title, message, context)
     SELECT created_at, ''INFO'',
            CASE
                WHEN topic LIKE ''%soundcloud%'' OR topic LIKE ''%youtube%'' THEN ''downloader''
                WHEN topic LIKE ''%import%'' THEN ''importer''
                ELSE ''music-manager''
            END,
            NULL, title, message, NULL
     FROM notifications',
    'SELECT ''overslaan: notifications ontbreekt''');
PREPARE stmt FROM @copy;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 3. De oude tabel opruimen.

DROP TABLE IF EXISTS notifications;
