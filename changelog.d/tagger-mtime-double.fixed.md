- **70 % van de bieb gold élke tagger-ronde als "gewijzigd".** `tagger_processed_files.mtime`
  was een `FLOAT`: bij de huidige epoch ligt er 128 s tussen twee opeenvolgende waarden, dus
  de tagger schreef een afgeronde mtime terug en las bij de volgende walk `mtime > opgeslagen`
  voor elk bestand dat naar beneden was afgerond. Gemeten op 1.200 prod-bestanden: 841 elke
  ronde opnieuw getagd, 359 met een verborgen wijziging, 0 exact. De kolom is nu `DOUBLE`
  (`migrate_v29`), de tagger slaat de mtime van ná zijn eigen schrijfactie op in plaats van
  die van ervoor, en een opgeslagen waarde die nog float32-afgerond is en binnen één stap
  van het bestand ligt telt niet als wijziging -- die rijen genezen zodra het bestand om een
  andere reden wordt getagd.

<!-- release notes -->

- **De tagger dacht elke ronde dat 70 % van de bieb was gewijzigd.** Afrondingsfout in de
  opgeslagen bestandstijd; een walk zonder werk is nu ook echt een walk zonder werk.
