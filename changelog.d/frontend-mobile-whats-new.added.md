- **De setup-wizard opende na een update; de webspeler heeft geen wizard.** Voor
  muma-mobile 7.0.0 moet de app na een update op Home openen met bestaande downloads, niet op een
  carrousel — maar wat er veranderd is moet een luisteraar nog wel te weten komen. `MumaSystem`
  geeft nu `appVersion()` (de `versionName` van de APK, iets anders dan de bundle-versie die
  `platform.diagnostics` stuurt: dat is een git-hash zonder relatie tot `CHANGELOG.md`-koppen). Een
  nieuwe `mobileReleaseNotes.js` vergelijkt die met een in `localStorage` onthouden vorige versie
  en toont, alleen bij een echte upgrade en nooit bij een nieuwe installatie, wat er veranderd is —
  via dezelfde `ReleaseNotesModal.svelte` die `TopBar.svelte` al gebruikt voor de release notes van
  de LMS-server zelf. De tekst komt uit muma-mobile's eigen `CHANGELOG.md`, gelezen via een nieuwe
  `MumaSystem.releaseNotes()` uit hetzelfde asset-bestand dat `copyChangelog` al voor de oude
  "Wat is er nieuw"-knop klaarzet — niet gebundeld in de webspeler zelf, want die build draait in
  een Docker-context die alleen `services/frontend` ziet. Tonen kost nog steeds geen netwerkverzoek:
  de tekst zat al in de APK.

<!-- release notes -->

- De app toont na een update kort wat er veranderd is in plaats van de oude setup-wizard te
  openen; bij een nieuwe installatie verschijnt niets.
