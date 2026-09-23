- **Het wachtwoord en de MuMa-API-key gingen mee met elk diagnostiekrapport.** Bij het opstarten
  schreef de app alle instellingen naar het logboek, `staticPassword` en `mumaApiKey` in leesbare
  tekst, en dat logboek wordt met elk rapport geüpload; rapporten 34 en 35 staan zo op de server.
  Die waarden worden nu gemaskeerd bij het loggen, en de tekst wordt bij het uploaden nog eens
  opgeschoond, omdat een vorige sessie van een oudere build nog steeds wordt meegestuurd.
<!-- release notes -->
- **Diagnostiekrapporten bevatten geen wachtwoord of API-key meer.**
