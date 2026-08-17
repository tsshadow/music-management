-- Radioshows en podcastseries: één tabel met shows, één met schrijfwijzen.
--
-- De tagger labelt festivals al, maar shows zoals Isaac's Hardstyle Sessions,
-- Hard With Style en The Uptempo Tribe Podcast waren niet van een gewone lange
-- mix te onderscheiden. Deze twee tabellen zijn de curatiekant daarvan: de
-- detector (tools/detect_podcasts.py) zet wat hij vindt op 'unknown', en alleen
-- een show die op 'white' staat wordt ooit in een bestand geschreven.
--
-- De aliassen zitten er vanaf het begin in, omdat één show meerdere namen heeft:
-- "Isaac's Hardstyle Sessions", "DJ ISAAC - HARDSTYLE SESSIONS" en "Q-Dance:
-- Isaac's Hardstyle Sessions" zijn dezelfde serie. rules_festival_data heeft dat
-- probleem ook en heeft daardoor 158 rijen voor 15 festivals nodig.
--
-- Veilig om opnieuw te draaien.

-- 1. De shows zelf. `host` en `station` zijn beschrijvend; nog niets leest ze,
--    maar een zender als Toxic Sickness heeft tientallen residencies en dat is
--    het veld dat die later groepeert.

CREATE TABLE IF NOT EXISTS rules_podcasts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    normalized_name VARCHAR(191) NOT NULL UNIQUE,
    state ENUM('white', 'black', 'unknown') NOT NULL DEFAULT 'unknown',
    host VARCHAR(255) NULL,
    station VARCHAR(255) NULL,
    occurrences INT NOT NULL DEFAULT 0,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    decided_at TIMESTAMP NULL,
    decided_by VARCHAR(64),
    INDEX(state)
);

-- 2. De schrijfwijzen. De eigen naam van een show telt ook als alias, zodat een
--    net goedgekeurde show matcht voordat iemand een variant heeft vastgelegd.

CREATE TABLE IF NOT EXISTS rules_podcast_aliases (
    id INT AUTO_INCREMENT PRIMARY KEY,
    podcast_id INT NOT NULL,
    alias VARCHAR(255) NOT NULL,
    normalized_alias VARCHAR(191) NOT NULL UNIQUE,
    occurrences INT NOT NULL DEFAULT 0,
    INDEX(podcast_id),
    FOREIGN KEY (podcast_id) REFERENCES rules_podcasts(id) ON DELETE CASCADE
);

-- 3. Na deze migratie:
--
--    tools/detect_podcasts.py --apply           vult de wachtrij
--    Beheer > Podcasts in de webui              keurt shows goed of af
--
--    Daarna moet PODCAST nog bij de LMS-scaninstellingen als extra tag, anders
--    levert getTags niets op en blijven de browsepagina's leeg. En bestanden die
--    de tagger al gezien heeft worden overgeslagen tot needs_rescan gezet is.
