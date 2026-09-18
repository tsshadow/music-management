- **Een tagger-ronde zonder werk kostte ruim een uur aan databaseverbindingen.** De mapwalk
  vroeg per bestand op een verse verbinding of het al getagd was: gemeten op prod 14 ms per
  bestand, waarvan 0,1 ms de query zelf, over 327k bestanden. Dezelfde 327k rijen komen in
  één SELECT in 1,4 s terug en passen in ~100 MB. Een ronde laadt de tabel nu één keer, na
  de wachtrij-pass en alleen voor de duur van de walk; `mark_processed` houdt het snapshot
  bij, en als de tabel niet te lezen is valt de ronde terug op de oude query per bestand.
  Een bestand dat ná het laden gemarkeerd wordt, mist deze walk en pakt de volgende ronde
  in de wachtrij-pass op.

<!-- release notes -->

- **Een tagger-ronde zonder werk kostte ruim een uur aan databaseverbindingen.** De tagger
  leest zijn eigen administratie nu één keer per ronde in plaats van per bestand.
