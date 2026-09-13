- **De oude bookmarks-knop stond los van het nieuwe hervatten van sets.** Bookmarks werden nooit
  lokaal opgeslagen — `createBookmark`/`deleteBookmark` gingen altijd al rechtstreeks naar de
  Subsonic-server — dus een eenmalige `BookmarkMigration` leest die server-lijst nu bij het opstarten
  van de schil en zet elke bookmark op een set (dezelfde tien-minuten-grens als de rest van de app)
  om naar de webs `setResume`-sleutel in de account-instellingen, met dezelfde `work:<id>`/
  `track:<id>`-sleutel als `getDeduplicateKey`. Draait maar één keer per account
  (`Settings.bookmarksMigratedToSetResume`); een mislukte poging (offline, geen MuMa-account) laat
  de vlag ongezet zodat de volgende start het opnieuw probeert.

<!-- release notes -->

- Bestaande bookmarks worden bij de eerste start van de nieuwe schil automatisch omgezet naar het
  nieuwe "hervat een set"-onthouden, zodat er niets verloren gaat.
