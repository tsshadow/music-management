- **`MumaSystem` beantwoordt nu `appVersion()` en `releaseNotes()`.** `appVersion()` geeft de
  `versionName` van de APK terug, voor de webspeler die net-na-een-upgrade "wat is er nieuw" moet
  tonen — iets anders dan de bundle-versie die `platform.diagnostics.identify()` al kreeg, want die
  is een git-hash zonder relatie tot `CHANGELOG.md`. `releaseNotes()` geeft de tekst van
  muma-mobile's eigen `CHANGELOG.md` terug, gelezen uit hetzelfde asset-bestand dat `copyChangelog`
  al voor `Util.showChangelog` klaarzet: de webspeler kan dat bestand niet zelf inbundelen, want
  `frontend:bundle` draait in een Docker-context die alleen `services/frontend` ziet. Beide lezen
  via `context`, niet `activity`: dezelfde reden waarom `setKeepScreenOn` dat al deed.

<!-- release notes -->

- De webspeler in de app weet nu welke versie er draait en kan de eigen release notes lezen, voor
  het "wat is er nieuw"-scherm na een update.
