-- Extra festivals en spellingen voor de tagger.
--
-- Gemeten op 24-08-2026 over 58.152 bestanden in Livesets, Warm Up Mixes, Podcasts,
-- Top 100 en Youtube: 11.170 daarvan noemen een festival dat de tagger al kent. De
-- namen hieronder komen uit de rest -- events waarvan wél sets in de bibliotheek staan
-- maar die in geen enkele spelling in rules_festivals voorkwamen.
--
-- Alles wat de regel labelt is minstens tien minuten lang (MIN_SET_SECONDS), dus een
-- naam die óók een tracktitel is raakt losse nummers niet. Dat is waarom eendelige
-- namen als 'Loudness' en 'Euphoria' hier veilig kunnen staan.
--
-- Bewust níét toegevoegd, omdat ze in deze bibliotheek iets anders aanduiden dan een
-- evenement: 'Gearbox' kaal (2.066 labeluploads tegen 94 sets, dus alleen de events
-- zelf), 'Bass Events' (organisator-kanaal), 'Hardstyle Top 100' (chart), 'Wildstylez'
-- (artiest), 'Wasteland' kaal (tracktitel; de volledige naam staat al in de tabel),
-- 'Rampage' en 'Mayday' (elk één set, en beide gangbare tracktitels).
--
-- De bestaande bestanden komen hier vanzelf langs zodra de deep run van de tagger
-- (tagger_deep_run_days) ze opnieuw aanbiedt; daar is geen apart backfill-script voor
-- nodig.

-- 1. Nieuwe namen.

DROP TABLE IF EXISTS _festival_seed_v14;
CREATE TABLE _festival_seed_v14 (name VARCHAR(255) NOT NULL, alias VARCHAR(255) NOT NULL);

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

DROP TABLE _festival_seed_v14;

-- 2. Een spelling erbij op een festival dat al bestaat.
--
--    Flashback (Bass Events) stond alleen als 'Flashback Festival' in de tabel, en zo
--    heet het in geen enkele bestandsnaam. De korte vorm mag er nu bij: een titel als
--    "Reverze 2024 - Reverze Flashback" levert sinds deze uitgave twee namen op --
--    Flashback én Reverze -- in plaats van dat de langste alias de andere wegdrukt.

INSERT IGNORE INTO rules_festival_aliases (festival_id, alias, normalized_alias)
SELECT f.id, 'Flashback', 'flashback'
FROM rules_festivals f
WHERE f.normalized_name = 'flashback festival';

-- 3. Wat er nu staat.
--
--    SELECT f.name, COUNT(DISTINCT a.normalized_alias) AS aliases
--    FROM rules_festivals f
--    LEFT JOIN rules_festival_aliases a ON a.festival_id = f.id
--    GROUP BY f.id ORDER BY f.name;
