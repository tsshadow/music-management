- **De tagger doet de retag-wachtrij nu eerst, rechtstreeks uit de tabel.** Een ronde liep de
  mappen af in de volgorde EPs, Soundcloud, Youtube, Telegram, overig en begon bij elke herstart
  bovenaan; met vijf deploys in één nacht en 213.789 gemarkeerde bestanden was Youtube (50.384
  in de wachtrij, 0 klaar) in zestien dagen niet bereikt en stonden de genrebeslissingen van die
  ochtend achter alles. `Tagger._process_pending` leest de rijen met `needs_rescan` per 500 op
  primaire sleutel, tagt ze met het brontype dat hun pad geeft, en gooit de rij weg van een
  bestand dat niet meer bestaat. Wat klaar is blijft klaar over een herstart heen. Nieuwe index
  `(needs_rescan, filepath)` via `migrate_v28`; de mapwalk daarna vindt alleen nog nieuwe en
  gewijzigde bestanden.

<!-- release notes -->

- **Een regelwijziging wordt nu eerst verwerkt, niet pas als de tagger toevallig langs die map
  komt.** Een herstart of deploy zet de wachtrij niet meer terug naar het begin.
