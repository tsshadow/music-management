- **Elk Soundcloud-bestand kostte de tagger 2,2 s, waarvan 1,6 s het drie keer inlezen van
  `library_artists`.** De artiestregels bouwen per bestand een index van alle 57k namen, en
  `TableHelper.get_all_values()` ging daarvoor drie keer per bestand naar de database, terwijl
  de helper diezelfde namen al in het geheugen had. De helper levert nu zijn eigen snapshot
  (nooit gemuteerd, vervangen bij een wijziging, per minuut ververst zodat de download- en
  importcontainers een nieuwe artiest ook zien), `exists()` is een dict-lookup in plaats van
  een scan over 57k namen, en de vier plekken die alleen wilden weten óf er een lijkende
  artiest bestaat stoppen bij de eerste treffer in plaats van alle namen te scoren.

<!-- release notes -->

- **De tagger las per bestand drie keer de hele artiestenlijst uit de database.** Nu één
  keer per minuut; een Soundcloud-bestand kost een fractie van wat het kostte.
