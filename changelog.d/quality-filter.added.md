- **Filteren op geluidskwaliteit: alleen flac, of alles vanaf 320 kbps.** De bibliotheek houdt
  16.500 flac- en 1.100 wav-bestanden naast 61.000 mp3's op 320 en ruim twee keer zoveel
  daaronder, en niets kon ze uit elkaar houden. De scanner zet elk nummer nu in een `QUALITY`-cluster --
  `lossless`, `320`, `aac`, `192`, `low`, dezelfde vijf lagen waarmee muma de canonieke versie
  van een nummer kiest -- uit codec en bitrate, niet uit de extensie: een ALAC in een `.m4a` is
  lossless. De bestaande bibliotheek is in de migratie (V118) uit de al opgeslagen bitrate en
  het pad gevuld, zonder rescan; de scanner corrigeert dat per bestand zodra hij het toch leest.
  In Bladeren staat een chip Kwaliteit naast Rating (`getSpotifyTracks` neemt `minQuality`, een
  ondergrens: `320` is 320 én lossless), een preset onthoudt hem als `minQuality`, en de auto
  speelt zo'n preset ook echt met dat filter. Een lossless-vraag op een bibliotheek die de
  cluster nog niet heeft, geeft niets terug in plaats van alles; de scan-naar-luisteren-keten
  pint dat vast met de 33 kbps-fixture.

<!-- release notes -->

- **Filteren op geluidskwaliteit.** In Bladeren staat een chip Kwaliteit: alleen lossless, of
  alles vanaf 320 kbps. Sla hem op als preset en hij werkt ook in de auto.
