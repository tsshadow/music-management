- **Een nummer heeft nu een eigen pagina met al zijn versies.** Route `/song/<id>`, in dezelfde vorm
  als de album- en artiestpagina: de canonical bovenaan, daaronder elke versie, allemaal direct
  afspeelbaar. De knop ernaartoe staat naast de songtekst-knop en verschijnt alleen bij een nummer
  dat de server heeft gegroepeerd — een knop naar een lege pagina is erger dan geen knop, en terwijl
  de worker zijn achterstand wegwerkt draagt ongeveer de helft van de bibliotheek nog geen werk.
- De pagina haalt de versies zelf op en leidt ze niet af uit de lijst waar je vandaan kwam. Dat moet
  ook: de regel die je aanklikte ís de versie die de server koos, en de andere waren samengeklapt
  voordat de browser ze zag. `getSpotifyTracks?workId=<id>` levert ze mét afspeelbare id's, wat
  muma's eigen versie-API niet kan — die kent paden en muma-id's, en daar heeft de speler niets aan.
- Een nummer met maar één versie zegt dat, en een mislukte oproep zegt dát het mislukte in plaats van
  een lege pagina te tonen. Subsonic meldt zijn eigen fouten met HTTP 200 en een fout in de body, dus
  de status in die body is het enige dat vertelt of het werkte.
