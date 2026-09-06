- **De app-versie werd stilzwijgend gelijkgesteld aan de serverversie.** `versionName` van
  muma-mobile loopt bewust een minor voor op de root-`VERSION`, dus een fragment in
  `changelog.d/mobile/` belandde onder een versie die de app nooit gehad heeft. Daar is nu
  `--mobile-version` voor, en zonder die vlag weigert het script te draaien zodra er mobiele
  fragmenten liggen -- liever een release die stilstaat dan een changelog die liegt.

<!-- release notes -->

- **De release notes van de app worden niet langer onder de serverversie gezet.**
