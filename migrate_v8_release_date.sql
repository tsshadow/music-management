-- Releasedatum met dag-precisie.
--
-- Label-rips kwamen binnen met alleen een jaartal, wat te grof is om op
-- releasedatum te sorteren of een verjaardag tegen te matchen. De tagger leest de
-- exacte datum nu uit de scene-NFO die naast de audio staat
-- (services/tagger/Song/NfoDate.py) en schrijft die naar ORIGINALDATE.
--
-- `rules_scene_group_date_format` is de overridetabel voor scene-groepen die hun
-- datums als M-D-Y schrijven in plaats van D-M-Y. Leeg is een geldige toestand:
-- zonder rij voor een groep geldt de positieregel (jaar vooraan is Y-M-D, jaar
-- achteraan is D-M-Y). Vullen gebeurt door een meting over de bibliotheek zelf,
-- met scripts/seed_scene_group_date_formats.py.
--
-- De collatie van scene_group is case-insensitief, en dat is bewust: dezelfde
-- groep schrijft zich soms NBD en soms Nbd, en die horen één verdict te delen.
--
-- `library_track_audio_features.release_date` komt naast `release_year` te staan,
-- niet in plaats daarvan: de jaarfilters en het jaarhistogram in
-- services/music_manager/routers/analytics.py rekenen op die kolom. De waarde is
-- een partiële datumstring ('2026', '2026-01' of '2026-01-16'), dus de precisie
-- zit in de lengte en een aparte precisiekolom is niet nodig.
--
-- Elke statement is los idempotent en het bestand blijft splitsbaar op
-- puntkomma's, zoals migrate_v7_youtube_category_genres.sql.
--
-- Safe to re-run.

CREATE TABLE IF NOT EXISTS rules_scene_group_date_format (
    scene_group VARCHAR(64) NOT NULL PRIMARY KEY,
    date_format VARCHAR(8) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE library_track_audio_features ADD COLUMN IF NOT EXISTS release_date VARCHAR(10);
