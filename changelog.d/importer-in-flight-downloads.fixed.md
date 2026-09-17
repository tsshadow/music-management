- **De importer pakte downloads uit die de browser nog aan het schrijven was.** De extractiestap
  gaf elk bestand in de importmap aan patool, ook de `.crdownload` die Firefox nog vasthield.
  patool kijkt naar de inhoud en niet naar de extensie, dus een half geschreven `.rar.crdownload`
  met een al leesbare RAR-header werd afgekapt uitgepakt en het bronbestand daarna onder de
  schrijver vandaan gequarantainiseerd. Op 16-09 liep het zichtbaar mis: de ronde die om 15:00:08
  `HC-2026-WEEK-37-FLAC.rar.crdownload` in de lijst zette, was om 15:03:09 bij dat bestand
  aanbeland en toen had de browser het al hernoemd — alle drie de backends meldden `was not
  found`. Vijf archieven, zes ERROR-regels, en geen ervan was een echt probleem: alle vier de
  voltooide archieven kwamen een ronde later gewoon binnen. Bestanden met een `.crdownload`,
  `.part`, `.partial` of `.tmp` worden nu overgeslagen tot ze hun definitieve naam hebben, de
  conventie die `news.py` intern al volgde.

<!-- release notes -->

- **De importer blijft van downloads af die nog bezig zijn.** Een bestand dat de browser nog
  schrijft wordt overgeslagen tot het af is, in plaats van half uitgepakt te worden.
