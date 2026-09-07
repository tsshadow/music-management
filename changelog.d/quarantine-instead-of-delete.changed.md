- **De importketen verwijdert niets meer definitief; wat hij weggooit gaat in quarantaine.** Vier
  plekken deden een onherroepelijke `os.remove` of `rmtree` op een beoordeling die fout kan zijn.
  `Extractor.run` gooide het bronarchief weg zodra uitpakken lukte — dus vóórdat de renamer en de
  mover de release geplaatst hadden, en voor een labelrip is dat archief de enige pristine kopie die
  er ooit van bestaat. `Mover.remove` en `Renamer._resolve_collision` verwijderden een bronmap die
  ze als duplicaat beoordeelden, en die beoordeling (`is_same_release`) vergelijkt relatieve
  bestandsnamen en groottes, niet inhoud. En `BaseSong.__init__` verwijderde een `.m4a` die mutagen
  niet kon lezen, terwijl "mutagen kan dit niet lezen" iets anders is dan "hier zit geen audio in".
  Alles gaat nu naar `<quarantine>/<datum>/<categorie>/`, en `Quarantine.sweep()` ruimt het op na
  `quarantine_retention_days` (standaard 30). Twee nieuwe instellingen onder Paden.
- **De ene mover-tak vergeleek wel, de andere niet.** `_resolve_conflict` draait `is_same_release`
  voordat hij iets weggooit; de `FileExistsError`/`shutil.Error`-tak deed dat niet en verwijderde de
  bron op de uitzondering alleen. Een release die toevallig tegelijk in dezelfde bestemming landde
  werd zo weggegooid zonder dat er ooit iemand naar gekeken had. Beide takken stellen nu dezelfde
  vraag.
- De scanner loopt verborgen mappen niet meer in. Zonder ingestelde quarantainemap landt die naast
  de muziekroot als `.quarantine`, en het indexeren daarvan zou precies de bestanden terugbrengen
  die de importer net besloot niet te houden. `@eaDir` van Synology gaat om dezelfde reden mee.

<!-- release notes -->

- **De importer gooit niets meer meteen weg.** Uitgepakte archieven, dubbele releases en
  onleesbare bestanden gaan een maand in quarantaine, zodat een verkeerde beoordeling terug te
  draaien is.
