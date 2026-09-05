- **"Henk feat Kees" werd in de bibliotheek altijd "Henk, Kees" — het woordje dat de twee namen
  verbond, was onherstelbaar weg.** `CleanTagsRule` splitst het artiestentag op "feat"/"vs"/"b2b"/"&"
  in losse `library_track_artists`-rijen, en die stap gooide de scheidende tekst zelf weg: alleen
  de namen bleven over. Het tagbestand zelf raakte de tekst ook kwijt zodra het een tagronde kreeg,
  dus er was daarna geen plek meer waar "feat" nog stond. De tagger schrijft de originele
  artiestregel nu, vóór die split, weg als een `TXXX:ORIGINAL_ARTIST`-frame — alleen wanneer de
  split ook echt iets veranderde, dus een los-artiest-bestand krijgt er niets bij. De scanner leest
  dat frame terug in een nieuwe kolom `library_tracks.display_artist`, en Bibliotheekbeheer toont
  die tekst nu in plaats van de kale kommalijst zodra hij er is.
  Geen backfill: een bestand krijgt dit pas bij de eerstvolgende tagronde om een andere reden, want
  de rauwe tekst bestaat alleen nog kort tijdens het schrijven zelf. Beperkt tot Bibliotheekbeheer —
  LMS en de mobiele app hebben hun eigen, losstaande artiestenmodel en blijven de kommalijst tonen.

<!-- release notes -->

- **Bibliotheekbeheer toont voortaan "Henk feat Kees" in plaats van "Henk, Kees" waar dat bekend
  is.** Geldt voor nieuw getagde bestanden; bestaande bestanden krijgen het bij hun volgende
  tagronde.
