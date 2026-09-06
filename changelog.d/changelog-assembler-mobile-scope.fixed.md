- **Een release met een mobiel changelog-fragment maakte `services/muma-mobile/RELEASE_NOTES.md`
  leeg.** Het samenstellen opende elk bestand om te schrijven vóórdat het wist dat het er iets in
  kon zetten, en de eerste die geen bruikbare kop had bleef als leeg bestand achter -- 47 KB weg,
  op een release-branch, waar het eruitziet als een merge-ongeluk in plaats van een script dat
  halverwege opgaf. De kop was overigens gewoon aanwezig: `CHANGELOG.md` schrijft
  `## [Unreleased]` en de root-`RELEASE_NOTES.md` `## Unreleased`, terwijl de kopieën van de app
  het in beide bestanden tussen haken zetten. Beide spellingen worden nu geaccepteerd, en niets
  wordt geschreven tot alle bestanden van die scope samengesteld zijn.
- **De app-versie werd stilzwijgend gelijkgesteld aan de serverversie.** `versionName` van
  muma-mobile loopt bewust een minor voor, dus een mobiel fragment belandde onder een versie die
  de app nooit gehad heeft. `--mobile-version` is er nu voor, en zonder die vlag weigert het
  script te draaien zodra er fragmenten in `changelog.d/mobile/` staan.

<!-- release notes -->

- **Het samenstellen van de release notes kon een bestand leegmaken.** Dat kan niet meer, en de
  app-versie wordt niet langer verward met die van de server.
