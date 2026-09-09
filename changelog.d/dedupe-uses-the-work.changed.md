- **"Eén regel per nummer" gebruikt nu het oordeel van de server in plaats van twee gokken.** De
  schakelaar in de web-UI deed twee dingen tegelijk: LMS kreeg `deduplicate=true` en klapte rijen
  samen op een genormaliseerde artiest plus titel, en de browser deed daarna hetzelfde nog een keer.
  Beide telden hun score op, en dat is precies de omkering die het versiemodel moest wegnemen — een
  320kbps SoundCloud-rip (+5200) versloeg een officiële 192kbps radio-edit (+2500).
- Allebei groeperen ze nu op `work_id` en houden ze de versie die muma als canonical aanwees. De
  score dient alleen nog als tie-break voor een werk waarvan de winnaar nog niet herberekend is, en
  die score is die van de server, niet een tweede berekening.
- **Wat de server niet heeft gegroepeerd blijft staan.** Een track zonder `workId` krijgt een sleutel
  van zichzelf en verdwijnt dus niet. Dat is geen randgeval: terwijl de worker zijn achterstand
  wegwerkt draagt ongeveer de helft van de bibliotheek geen werk, en die verbergen zou de lijst legen
  van muziek die er gewoon is. Hetzelfde geldt voor een antwoord van een server die migratie 118 nog
  niet heeft gedraaid: een ontbrekende `isCanonical` betekent "wel tonen".
- 106 regels heuristiek uit `Spotify.cpp` en de volledige inhoud van `deduplicate.js` zijn vervangen
  door het toepassen van wat er al besloten was.
- Nieuw: `getSpotifyTracks?workId=<id>` geeft alle versies van één nummer, met afspeelbare id's — dat
  is wat de versielijst achter een regel straks nodig heeft. muma's eigen `/api/songs/{id}` kent
  paden en muma-id's, en daar kan de speler niets mee. Een `workId` zet dedupliceren uit, want anders
  klapt het antwoord terug naar de ene versie waar je juist langs wilde kijken.
