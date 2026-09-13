- **`MumaSystem` beantwoordt nu `appVersion()`.** Geeft de `versionName` van de APK terug, voor de
  webspeler die net-na-een-upgrade "wat is er nieuw" moet tonen — iets anders dan de bundle-versie
  die `platform.diagnostics.identify()` al kreeg, want die is een git-hash zonder relatie tot
  `CHANGELOG.md`. Leest via `context`, niet `activity`: dezelfde reden waarom `setKeepScreenOn`
  dat al deed.

<!-- release notes -->

- De webspeler in de app weet nu welke versie er draait, voor het "wat is er nieuw"-scherm na een
  update.
