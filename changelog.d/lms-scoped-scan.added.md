- **LMS kan voortaan één map scannen in plaats van de hele bibliotheek.** `startScan` accepteert een
  herhaalbare `path`-parameter, bibliotheek-relatief, en doet daar seconden over waar een volledige
  incrementele scan hier bijna een uur kost -- en pas een uur ná de vorige begint, dus een
  wijziging wachtte tot twee uur voordat je hem zag, met het oude pad al die tijd nog in de index.
  Een pad dat niet meer bestaat is expres geldig: dat is hoe de rijen onder een verplaatste map
  worden opgeruimd. De verwijderstap kreeg daarvoor een query met een half-open bytebereik in
  plaats van `LIKE`, want die is in SQLite hoofdletterongevoelig en matcht bovendien een buurmap
  waarvan de naam toevallig hetzelfde begint. Samen met `fullScan` betekent het "lees alles onder
  dit pad opnieuw". Overgeslagen worden alleen `Optimize` en het duplicatenrapport; het opruimen
  van wezen en het herberekenen van de clustertellingen blijven staan -- dat laatste overslaan is
  ooit de reden geweest dat elke genretelling op 0 stond. En een scoped scan schrijft zijn cijfers
  niet weg als `lastScan`, zodat de beheerpagina de laatste volledige scan blijft beschrijven.

<!-- release notes -->

- **De muziekserver kan nu één map opnieuw inlezen in plaats van de hele bibliotheek.** Dat is de
  basis om wijzigingen binnen seconden zichtbaar te maken in plaats van na uren.
