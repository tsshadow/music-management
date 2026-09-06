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

- **Een direct scanverzoek pauzeert de periodieke scan en die gaat daarna verder waar hij was.**
  Voorheen brak zo'n verzoek de lopende scan af en verschoof het bovendien het volgende
  scanmoment naar "over een uur" -- bij een uurschema en een scan die bijna een uur duurt,
  betekende dat: altijd bezig, altijd afgebroken, en de klok altijd teruggezet, dus de
  bibliotheek-brede scan kwam nooit meer door zijn eigen stappen heen. De pauze hergebruikt de
  vlag die elke scanstap al op elke batchgrens controleert; de scanner onthoudt daarnaast
  alleen nog *waarom* die vlag omhoog ging. Bij hervatten begint de onderbroken stap opnieuw,
  de stappen ervoor niet, en hun cijfers blijven staan. Binnenkomende paden worden vijf
  seconden lang verzameld en samengevoegd, en vertrekken hoe dan ook binnen een minuut: een
  taggerronde die honderden mappen aanraakt kost de scan zo één stap-herstart per minuut in
  plaats van honderden.

- **Naast het incrementele schema staat nu een wekelijkse volledige herlezing.** Dezelfde
  bibliotheek-brede scan met `fullScan` aan, op een instelbare weekdag, standaard uit. Vallen
  beide momenten samen, dan wint de volledige: die doet alles wat de incrementele doet.
  music-manager stuurt sinds deze versie bij elke verplaatsing de betrokken mappen mee -- oude
  én nieuwe, want het oude pad is hoe de rijen onder een verdwenen map worden opgeruimd -- en
  doet dat vanaf een eigen thread, zodat een trage muziekserver een import nooit ophoudt.

<!-- release notes -->

- **De muziekserver kan nu één map opnieuw inlezen in plaats van de hele bibliotheek.** Een
  verplaatste of hertagde map is binnen seconden zichtbaar in plaats van na uren, en de grote
  scan die daarvoor liep wordt gepauzeerd in plaats van afgebroken.
