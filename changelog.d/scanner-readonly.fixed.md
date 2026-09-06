- **Een enkele rescan wiste de genres van de track die hij opnieuw inlas.** `ScannerManager` bouwt
  zijn `GenreRulesHelper` zonder cache en alleen `run_full` laadde die; `scan_single` niet. De
  genre-resolutie kwam daardoor leeg terug, en `_write_genres` doet zijn `DELETE` ook als er niets
  in te voegen valt. Dat raakte elke "rescan deze track" uit de webinterface en elke
  `/tracks/rerun-parse-path` die LMS stuurt. `ensure_loaded()` laadt de regels nu eenmalig op dat
  pad, zonder een query per bestand.
- **De scanner kon bestanden verwijderen en herschrijven terwijl hij ze alleen las.**
  `ReadonlySong` erft `BaseSong.__init__`, en die doet `os.remove()` op een m4a die mutagen niet
  kan openen en draait `NormalizeFlacTagsRule`, die een FLAC met kleine letters in de tagsleutels
  meteen opslaat. Alleen het indexeren van de collectie muteerde dus bestanden; een grote rescan
  concentreert dat. Lezen kost niets: `TagCollection._parse_flac` maakt de sleutels bij het lezen
  toch al hoofdletters.

<!-- release notes -->
- Een track opnieuw laten inlezen raakt zijn genres niet meer kwijt.
- De scanner laat muziekbestanden nu met rust: hij leest ze alleen nog, en verwijdert of
  herschrijft er geen meer.
