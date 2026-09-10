- **Productie wordt elke nacht om 02:00 nagelopen, en een fout die niemand had gezien wordt
  een fix-MR in plaats van een regel in een log.** `scripts/nightly-prod-check/` op de
  runnerhost leest `/health`, de containers, alle ERROR/CRITICAL-events van de laatste 24
  uur en de logstaarten via de API, vouwt ze tot vingerafdrukken en vergelijkt met een
  grootboek van eerdere oordelen. Alleen wat nieuw is, piekt of terugkomt gaat naar één
  Claude-run (`claude-opus-5`) met de skill `muma-nightly-prod-check`, die per punt een
  oordeel velt en bij een eenduidige codefout een MR naar `develop` opent met label
  `claude-nightly-fix` — maximaal twee per nacht, nooit gemerged zonder approval. Elke
  nacht eindigt in één ntfy-bericht op `music-management-claude`, verstuurd door de
  shell-supervisor uit een gevalideerd resultaat, dus ook een vastgelopen run meldt
  zichzelf. De MR-watcher merget nu alleen op approval van `muma` en een groene
  pipeline voor exact de te mergen revisie, en de drie automaten delen één lock op de
  clone.

<!-- release notes -->

- **Productie wordt elke nacht om 02:00 nagelopen.** Nieuwe fouten worden beoordeeld en,
  als de oorzaak eenduidig is, als fix-MR klaargezet; elke nacht komt er één
  ntfy-bericht, ook als er niets was.
