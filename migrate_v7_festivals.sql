-- Festivalherkenning: van één tabel met een rij per editie naar naam, alias en editie.
--
-- rules_festival_data had PRIMARY KEY (festival, year), dus je moest elk jaar apart
-- invoeren voordat een festival überhaupt herkend werd. Daardoor stond de tabel al
-- tijden op vijftien namen. Na deze migratie is één rij in rules_festivals genoeg om
-- te labelen; een editie voegt alleen de datum toe.
--
-- De oude tabel blijft staan. Hij wordt niet meer gelezen, maar is de enige plek waar
-- de oorspronkelijke data vandaan komt, dus weggooien kan later met de hand.
--
-- Veilig om opnieuw te draaien.

-- 1. De nieuwe tabellen.
--
--    normalized_name en normalized_alias zijn hier alleen om dubbele rijen tegen te
--    houden; het echte matchen doet FestivalHelper.normalize() in Python, die ook
--    accenten en leestekens wegwerkt.

CREATE TABLE IF NOT EXISTS rules_festivals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    normalized_name VARCHAR(191) NOT NULL UNIQUE,
    active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rules_festival_aliases (
    festival_id INT NOT NULL,
    alias VARCHAR(255) NOT NULL,
    normalized_alias VARCHAR(191) NOT NULL,
    PRIMARY KEY (festival_id, normalized_alias),
    INDEX idx_normalized_alias (normalized_alias),
    FOREIGN KEY (festival_id) REFERENCES rules_festivals(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS rules_festival_editions (
    festival_id INT NOT NULL,
    year INT NOT NULL,
    date DATE NOT NULL,
    PRIMARY KEY (festival_id, year),
    FOREIGN KEY (festival_id) REFERENCES rules_festivals(id) ON DELETE CASCADE
);

-- 2. De bestaande vijftien overzetten.
--
--    TRIM haalt meteen de spatie weg die achter 'REBELLiON ' stond. Die viel in SQL
--    niet op -- MySQL negeert trailing spaces bij vergelijken -- maar de match gebeurt
--    in Python, en daar telt hij wel mee.

INSERT IGNORE INTO rules_festivals (name, normalized_name)
SELECT DISTINCT TRIM(festival), LOWER(TRIM(festival))
FROM rules_festival_data
WHERE festival IS NOT NULL AND TRIM(festival) <> '';

INSERT IGNORE INTO rules_festival_editions (festival_id, year, date)
SELECT f.id, d.year, d.date
FROM rules_festival_data d
JOIN rules_festivals f ON f.normalized_name = LOWER(TRIM(d.festival))
WHERE d.year IS NOT NULL AND d.date IS NOT NULL;

-- 3. De namen en spellingen.
--
--    Eerst in een werktabel, zodat de lijst als lijst leesbaar blijft. Kolom 1 is de
--    naam die op het kaartje in de app komt, kolom 2 een spelling die in titels en
--    mapnamen voorkomt. De langste alias die past wint, dus 'Supremacy Germany' gaat
--    voor 'Supremacy' en 'Karnaval Festival' voor 'Intents'.

DROP TABLE IF EXISTS _festival_seed;
CREATE TABLE _festival_seed (name VARCHAR(255) NOT NULL, alias VARCHAR(255) NOT NULL);

INSERT INTO _festival_seed (name, alias) VALUES
    -- Al bekend, maar zonder alternatieve spellingen
    ('Defqon', 'Defqon'), ('Defqon', 'Defqon.1'), ('Defqon', 'Defqon 1'),
    ('Decibel', 'Decibel'), ('Decibel', 'Decibel Outdoor'), ('Decibel', 'Décibel'),
    ('Dominator', 'Dominator'), ('Dominator', 'Dominator Festival'),
    ('Hard Bass', 'Hard Bass'), ('Hard Bass', 'Hardbass'),
    ('Intents Festival', 'Intents'), ('Intents Festival', 'Intents Festival'),
    ('Karnaval Festival', 'Karnaval Festival'), ('Karnaval Festival', 'Intents Karnaval'),
    ('REBiRTH Festival', 'Rebirth'), ('REBiRTH Festival', 'Rebirth Festival'),
    ('REBELLiON', 'Rebellion'),
    ('REACTiVATE', 'Reactivate'),
    ('Supersized Kingsday', 'Supersized'), ('Supersized Kingsday', 'Supersized Kingsday'),
    ('Supremacy', 'Supremacy'),
    ('Supremacy Germany', 'Supremacy Germany'),
    ('Snakepit', 'Snakepit'),
    ('Syndicate', 'Syndicate'),
    ('Melodic Madness', 'Melodic Madness'),

    -- Q-dance
    ('Qlimax', 'Qlimax'),
    ('Q-BASE', 'Q-BASE'), ('Q-BASE', 'Qbase'), ('Q-BASE', 'Q Base'),
    ('QAPITAL', 'QAPITAL'),
    ('X-Qlusive', 'X-Qlusive'), ('X-Qlusive', 'XQlusive'),
    ('The Qontinent', 'The Qontinent'), ('The Qontinent', 'Qontinent'),
    ('Impaqt', 'Impaqt'),
    ('EPIQ', 'EPIQ'),
    ('Freaqshow', 'Freaqshow'),
    ('Qonnect', 'Qonnect'),

    -- b2s
    ('Ground Zero', 'Ground Zero'), ('Ground Zero', 'Ground Zero Festival'),
    ('Pussy Lounge', 'Pussy Lounge'),
    ('Harmony of Hardcore', 'Harmony of Hardcore'),
    ('Emporium', 'Emporium'), ('Emporium', 'Emporium Festival'),
    -- Alleen de volledige naam: 'Wasteland' op zichzelf is ook een tracktitel.
    ('Wasteland', 'Wasteland Festival'),
    ('Shockerz', 'Shockerz'),
    -- Loudness staat er bewust niet in: in deze bibliotheek is het vrijwel altijd de
    -- artiest System of Loudness of de gelijknamige track, niet het b2s-evenement.

    -- Art of Dance
    ('Thunderdome', 'Thunderdome'),
    ('Masters of Hardcore', 'Masters of Hardcore'),

    -- Bass Events
    ('Reverze', 'Reverze'),
    ('Fusion of Fear', 'Fusion of Fear'),
    ('No Mercy Festival', 'No Mercy Festival'),

    -- Overig harder styles
    ('Bassleader', 'Bassleader'),
    ('Free Festival', 'Free Festival'),
    ('Knockout Outdoor', 'Knockout Outdoor'),
    ('Elektrum Festival', 'Elektrum Festival'), ('Elektrum Festival', 'Elektrum'),
    ('HTID', 'HTID'),
    ('Flashback Festival', 'Flashback Festival'),
    ('Nightmare Festival', 'Nightmare Festival'),
    ('Hardshock Festival', 'Hardshock Festival'), ('Hardshock Festival', 'Hardshock'),
    ('Hardmission Festival', 'Hardmission Festival'), ('Hardmission Festival', 'Hardmission'),
    ('Toxicator', 'Toxicator'),
    ('E-Mission', 'E-Mission'),
    ('Sundown Festival', 'Sundown Festival'),
    ('Indian Summer Festival', 'Indian Summer Festival'),

    -- Breder dance, waar ook sets van in de bibliotheek staan
    ('Tomorrowland', 'Tomorrowland'),
    ('Mysteryland', 'Mysteryland'),
    ('Rotterdam Rave', 'Rotterdam Rave'),
    ('Awakenings', 'Awakenings'),
    ('Verknipt', 'Verknipt'),
    ('Milkshake Festival', 'Milkshake Festival'),
    ('Dance Valley', 'Dance Valley'),
    ('Nature One', 'Nature One'),
    ('Airbeat One', 'Airbeat One'),
    ('Wish Outdoor', 'Wish Outdoor'),
    ('Dreamfields', 'Dreamfields'),
    ('Solar Weekend', 'Solar Weekend'),
    ('Extrema Outdoor', 'Extrema Outdoor'),
    ('Paaspop', 'Paaspop'),
    ('Zwarte Cross', 'Zwarte Cross');

INSERT IGNORE INTO rules_festivals (name, normalized_name)
SELECT DISTINCT name, LOWER(TRIM(name)) FROM _festival_seed;

INSERT IGNORE INTO rules_festival_aliases (festival_id, alias, normalized_alias)
SELECT f.id, s.alias, LOWER(TRIM(s.alias))
FROM _festival_seed s
JOIN rules_festivals f ON f.normalized_name = LOWER(TRIM(s.name));

DROP TABLE _festival_seed;

-- 4. Een festival zonder alias zou onvindbaar zijn. Zijn eigen naam is er altijd één.

INSERT IGNORE INTO rules_festival_aliases (festival_id, alias, normalized_alias)
SELECT f.id, f.name, f.normalized_name
FROM rules_festivals f
LEFT JOIN rules_festival_aliases a ON a.festival_id = f.id
WHERE a.festival_id IS NULL;

-- 5. Wat er nu staat.
--
--    SELECT f.name, COUNT(DISTINCT a.normalized_alias) AS aliases,
--           COUNT(DISTINCT e.year) AS editions
--    FROM rules_festivals f
--    LEFT JOIN rules_festival_aliases a ON a.festival_id = f.id
--    LEFT JOIN rules_festival_editions e ON e.festival_id = f.id
--    GROUP BY f.id ORDER BY f.name;
--
--    Nieuwe labels landen pas in de app nadat de bestanden opnieuw langs de tagger
--    zijn geweest. Zie tools/retag_festivals.py voor het zetten van needs_rescan.
