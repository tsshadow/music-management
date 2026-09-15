-- Een statistiek per genre: waar het ligt tussen zacht en hard, 0-100.
--
-- Teun vroeg om vijf daily mixes die niet allemaal hetzelfde zijn -- zacht, midden,
-- hard, en twee vrije -- en daarvoor moet "zacht" en "hard" een getal zijn, geen
-- gevoel. Deze kolom is dat getal. Hij wordt gevuld door
-- services/music_manager/feeds/hardness.py:seed_genre_hardness(), die bij elke
-- opstart draait (main.py) en alleen een rij aanraakt die nog NULL is -- een eigen
-- aanpassing van een curator op de genre-edit-pagina wordt dus nooit overschreven.
-- Deze migratie voegt alleen de kolom toe; het vullen gebeurt in code, niet hier,
-- omdat de overerving via rules_subgenre_hierarchy (welke subgenre erft van welke
-- ouder) een graafwandeling is die in platte SQL niet leesbaar te schrijven is.
--
-- De ankers zelf (Deep House 10, Hardstyle 45, Terror 95, ...) zijn voorgestelde
-- standaardwaarden, niet gemeten -- zie docs/designs/feeds/functional.md,
-- "Daily mixes v2". De band-edges die uit deze kolom worden afgeleid (p33/p67 van
-- iemands eigen luistergeschiedenis) zijn dat evenmin.
--
-- Safe to re-run.

ALTER TABLE rules_genres ADD COLUMN IF NOT EXISTS hardness TINYINT UNSIGNED NULL;
