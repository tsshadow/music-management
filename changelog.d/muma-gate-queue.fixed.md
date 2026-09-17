- **Het openen van de startpagina gaf 503's op vrijwel elke MuMa-aanroep.** Elke `/muma/api`-call
  loopt via de LMS-proxy, die niet meer dan de helft van zijn HTTP-threads aan MuMa laat wachten
  en de rest weigert met `Too many requests to MuMa in flight`. Op productie (8 cores) is die
  grens vier; de startpagina vuurde er een stuk of twaalf tegelijk af — sessiecheck,
  accountinstellingen, genretinten, feedlijst, release radar, drie daily mixes,
  artiestafbeeldingen — elk vanuit een eigen module met een eigen limiet, samen ruim erover. De
  weigeringen werden bovendien in de maat opnieuw geprobeerd, zodat ze elkaar opnieuw troffen.
  De web-UI houdt nu één wachtrij voor alle MuMa-aanroepen bij elkaar (drie tegelijk, zodat de
  speler zijn eigen plek houdt), probeert een weigering met jitter tot ruim vijf seconden opnieuw
  en vraagt de artiestafbeelding via diezelfde wachtrij op. Van de proxy hoort een gebruiker niets
  te merken, of het nu één of honderd aanroepen zijn. LMS krijgt daarnaast een vaste pool van
  zestien HTTP-threads in plaats van "aantal cores", wat de proxygrens op productie van vier naar
  acht brengt.
