- Een losse bestandsscan wachtte onbeperkt op een lopende volledige scan, en dat legde de API alsnog
  plat nadat de retag-wachtrij leeg was. `scan_single` nam dezelfde lock die `run_full` urenlang
  vasthoudt; elke `announce()` van de tagger vroeg via `/api/scanner/scan/file` zo'n scan aan,
  gaf het na 10 s op, maar de serverthread bleef wachten tot de volledige scan klaar was. Na
  veertig van die aanvragen had geen enkel sync-endpoint -- `/health` incluis -- nog een thread,
  terwijl de CPU vrijwel niets deed en de async endpoints in milliseconden antwoordden (prod,
  2026-09-19: `/api/scanner/health` zei `busy: true`, `/health` bleef 60 s stil). Een losse scan
  wacht nu hooguit 5 s (`SCANNER_SINGLE_LOCK_TIMEOUT`) en geeft anders op; het bestand is niet
  kwijt, want zijn mtime is veranderd en de volgende volledige scan leest het sowieso. Het
  antwoord van `/api/scanner/scan/file` meldt met `scanned` of de scan is uitgevoerd.
