- **Een debug-installatie hoorde niets over een nieuwe release.** De update-check vroeg alleen
  naar zijn eigen reeks op apk-hoster, en de debug-reeks beweegt alleen als iemand het handmatige
  `mobile:build-debug` start: een telefoon bleef zo drie releases lang op 7.0.0 (316) staan
  terwijl 7.3.0 (320) klaarstond, en toonde Release Radar en Daily Mix nog met de 401-fout die
  7.1.0 verhielp. Een debug-build vraagt nu ook naar de release-reeks en meldt de nieuwste van de
  twee — met de download, en als "deze debug-build is ouder dan release x" in plaats van als
  update, want de release-APK installeert náást de debug-app. Een release-build vraagt nog steeds
  alleen naar de release-reeks.

<!-- release notes -->

- Een debug-installatie meldt nu ook wanneer een nieuwere release beschikbaar is.
