- **Een feed starten in de auto deed niets na een herstart van de afspeeldienst.** Android Auto
  bewaart de items die het al getoond heeft, dus een tik kon binnenkomen zonder dat er iets geladen
  was — en de netwerkcall gebeurde dan op de session-callback-thread. Dat is de main thread, wat
  `NetworkOnMainThreadException` oplevert, wat de app opving als "lege feed": een knop die stil
  niets doet. Loopt nu via dezelfde achtergrond-scope als de sterren- en random-lijsten.
- **Na middernacht speelde "alles afspelen" de ranglijst van gisteren**, en na het wisselen van
  server of account die van de vorige gebruiker, met de track-ids van de vorige server. Er stonden
  twee caches naast elkaar en de tweede kende dag noch server. Die is weg; wat overblijft is
  gesleuteld op feed, dag en server. Een feed die maar half opgelost kon worden — de server was
  bijvoorbeeld midden in een scan — wordt niet meer voor de rest van de dag onthouden.

<!-- release notes -->

- **Een feed starten in de auto deed niets meer na een herstart, en speelde na middernacht de lijst
  van gisteren.** Allebei verholpen.
