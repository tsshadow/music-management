- **Advies bij Genre Curatie.** De wachtrij stond op 821 genres, en het meeste daarvan is
  mechanisch te herkennen: twee genres met een schuine streep ertussen (`Frenchcore/Terror`,
  ook `\` en `,`), aan elkaar geplakt (`Jungleterror`), samengetrokken (`Upterror` is het begin
  van `Uptempo Hardcore` plus heel `Terror`; `Frenchtempo`), verkeerd gespeld (`Harddcore`,
  `Oldksool Rave`), met ruis erbij (`Hardstyle 2018`, `Happy Hardcore Classics`, `Add "uptempo"`),
  of helemaal geen genre — een artiest, een label, een woord (`Tafelpoot`). Naast elke naam in de
  wachtrij staat nu een **advies** met de redenering en een zekerheid: "vervangen door Uptempo
  Hardcore + Terror", "verwijderen", of niets, want `Energycore` leest als een genre en matcht
  nergens op, en dat blijft mensenwerk. Het woordenboek is je eigen eerdere werk: de goedgekeurde
  genres, elke correctie die al gemaakt is (`Vocal Trance → Trance` leert dat `vocal` een
  bijvoeglijk woord is dat je weglaat), de afgekeurde namen, en de artiest- en labelkoppelingen
  van de taggerpagina — `Dr Peacock` in het genreveld is een artiest die aan Frenchcore hangt,
  dus dat is het advies; een artiest zonder koppeling wordt "verwijderen, koppel hem op de
  taggerpagina". "Overnemen" per rij, "Advies opvolgen" per pagina voor alles met minstens 60%
  zekerheid; een advies doet nooit iets uit zichzelf, en een analyse raakt geen enkele beslissing.
  Droog gedraaid op de echte wachtrij: 126 vervangingen, 172 splitsingen, 372 verwijderingen,
  151 zonder advies. `POST /api/rules/genres/analyze`, `GET /api/rules/genres/summary`,
  `rules_genre_proposals` (`migrate_v27`), drempels onder `genre_curation_analyzer` in de config.
- **De genrelijst op de taggerpagina toont alleen goedgekeurde genres.** `GET /api/rules` gaf
  de hele `rules_genres`-tabel terug, dus het Genre Overzicht telde 1.767 rijen en de keuzelijst
  bij "artiest/label koppelen aan genre" bood ook afgekeurde en nog te beoordelen genres aan.
  Nu alleen `white`; de playlist-genrefilter gebruikt dezelfde lijst en gaat mee.
