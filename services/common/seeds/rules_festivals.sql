-- rules_festivals and rules_festival_aliases: the festivals the tagger recognises in set titles.
--
-- From migrate_v7_festivals.sql (step 3) and migrate_v14_festivals_extra.sql (steps 1 and 2).
-- The lists and the INSERTs are verbatim. Column 1 is the name on the card in the app, column 2
-- a spelling that occurs in titles and folder names; the longest alias that fits wins.
--
-- Not verbatim:
-- * The scratch tables are TEMPORARY instead of real tables. They live only on this connection,
--   so two services that start at the same time cannot drop each other's list.
-- * Left out: migrate_v7 step 2 copies rules_festival_data, a legacy table that is empty on a new
--   database, and step 4 gives a festival without an alias its own name as one. Step 4 is a
--   repair: every festival below has at least one alias.
--
-- INSERT IGNORE on rules_festivals.normalized_name and on the alias primary key
-- (festival_id, normalized_alias), so a re-run adds nothing and an edited row stays as it is.

-- 1. migrate_v7_festivals.sql

DROP TEMPORARY TABLE IF EXISTS _festival_seed;
CREATE TEMPORARY TABLE _festival_seed (name VARCHAR(255) NOT NULL, alias VARCHAR(255) NOT NULL)
    DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

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

DROP TEMPORARY TABLE _festival_seed;

-- 2. migrate_v14_festivals_extra.sql

DROP TEMPORARY TABLE IF EXISTS _festival_seed_v14;
CREATE TEMPORARY TABLE _festival_seed_v14 (name VARCHAR(255) NOT NULL, alias VARCHAR(255) NOT NULL)
    DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO _festival_seed_v14 (name, alias) VALUES
    -- Harder styles
    ('Loudness', 'Loudness'),
    ('I AM HARDSTYLE', 'I AM HARDSTYLE'), ('I AM HARDSTYLE', 'IAMHARDSTYLE'),
    ('Live For This', 'Live For This'),
    ('Vroeger Was Alles Beter', 'Vroeger Was Alles Beter'),
    ('Night of the Infected', 'Night of the Infected'),
    ('Faceless Halloween Festival', 'Faceless Halloween Festival'),
    ('Faceless Halloween Festival', 'Faceless Halloween'),
    ('Euphoria', 'Euphoria'),
    ('Hardcore4Life', 'Hardcore4Life'),
    ('Pandemonium', 'Pandemonium'),
    ('Sunrise Festival', 'Sunrise Festival'),
    -- Alleen de volledige naam: 'Sunrise' op zichzelf zit in tientallen tracktitels.

    -- Gearbox draait meerdere events onder één merk. De losse edities krijgen hun
    -- eigen kaartje, want 'Gearbox' alleen is hier vooral het label.
    ('Gearbox Pole Position', 'Gearbox Pole Position'),
    ('Gearbox Hot Pursuit', 'Gearbox Hot Pursuit'),
    ('Gearbox Twin Turbo', 'Gearbox Twin Turbo'),
    ('Gearbox Overdrive', 'Gearbox Overdrive'),
    ('Gearbox Full Throttle', 'Gearbox Full Throttle'),

    -- Revealed (Hardwell) draait twee terugkerende avonden
    ('Revealed Night', 'Revealed Night'),
    ('Revealed Kingsday', 'Revealed Kingsday'),

    -- Breder dance, waar sets van in de bibliotheek staan
    ('A State of Trance', 'A State of Trance'), ('A State of Trance', 'ASOT'),
    ('Creamfields', 'Creamfields'),
    ('EDC Las Vegas', 'EDC Las Vegas'), ('EDC Las Vegas', 'Electric Daisy Carnival'),
    ('Ultra Music Festival', 'Ultra Music Festival'), ('Ultra Music Festival', 'Ultra Miami'),
    ('Electric Love Festival', 'Electric Love Festival'),
    ('Parookaville', 'Parookaville'),
    ('Snowbombing', 'Snowbombing'),
    ('Pukkelpop', 'Pukkelpop'),
    ('Let It Roll', 'Let It Roll'),
    ('Planet Love', 'Planet Love'),
    ('Kiddstock', 'Kiddstock'),
    ("We Love The 90's Festival", "We Love The 90's Festival"),
    ("We Love The 90's Festival", "We Love The 90's"),
    ("We Love The 90's Festival", 'We Love The 90s');

INSERT IGNORE INTO rules_festivals (name, normalized_name)
SELECT DISTINCT name, LOWER(TRIM(name)) FROM _festival_seed_v14;

INSERT IGNORE INTO rules_festival_aliases (festival_id, alias, normalized_alias)
SELECT f.id, s.alias, LOWER(TRIM(s.alias))
FROM _festival_seed_v14 s
JOIN rules_festivals f ON f.normalized_name = LOWER(TRIM(s.name));

DROP TEMPORARY TABLE _festival_seed_v14;

-- 3. A spelling on a festival from the first list: titles name 'Flashback', never
--    'Flashback Festival'.

INSERT IGNORE INTO rules_festival_aliases (festival_id, alias, normalized_alias)
SELECT f.id, 'Flashback', 'flashback'
FROM rules_festivals f
WHERE f.normalized_name = 'flashback festival';
