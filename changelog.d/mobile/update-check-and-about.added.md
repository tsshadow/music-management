- **De app meldt weer dat er een nieuwe versie is, en je kunt het zelf controleren.** De
  updatecontrole verdween samen met het oude Kotlin-startscherm dat hem uitvoerde; een telefoon
  op build 312 hoorde daardoor niets over 313. De shell vraagt het apk-hoster nu weer
  (`MumaSystem.checkForUpdate`, dezelfde `/api/version`-vraag als vroeger, debug-builds volgen
  de debug-reeks), eens per dag bij het starten — stil tenzij er iets nieuws is, dan een
  melding met "Downloaden" — en op verzoek via "Controleren op updates" op de Over-pagina,
  die ook zegt dat je de nieuwste hebt en een onbereikbare hoster als fout meldt in plaats
  van als "up-to-date". De Over-pagina toont verder versie en build van de app, pakket,
  Android-versie en toestel, de MuMa API- en LMS-versie, het serveradres en de git-hash van
  de webinterface, en op de telefoon de changelog van de app zelf.

<!-- release notes -->

- **Updatemelding is terug**, plus "Controleren op updates" en een Over-pagina met alle
  versies (app, server, webinterface).
