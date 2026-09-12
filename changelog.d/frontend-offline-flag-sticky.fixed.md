- **Management en Bibliotheek meldden "Not available without a connection" terwijl de telefoon
  gewoon online was.** `subsonicJson()` zette de `offline`-vlag op elke netwerkfout, ook een enkele
  time-out of een niet-JSON antwoord (een proxy-foutpagina gooit een `SyntaxError` uit
  `response.json()`, geen `TypeError` van `fetch` zelf, maar werd tot nu toe hetzelfde behandeld).
  Eenmaal gezet bleef de vlag staan tot het enige andere schrijfpunt, het Android
  connectivity-event, weer *veranderde* — schermen zonder eigen offline-bron (playlists, feeds,
  memories, listening, Management) lieten daarna hun "unavailable"-melding zien tot een herstart,
  terwijl Songs gewoon doorwerkte omdat die view wél een lokale bron heeft. Een mislukte aanvraag
  vraagt nu `storage.isOffline()` opnieuw voor de vlag omgaat; bevestigt het apparaat dat niet, dan
  reist de oorspronkelijke fout gewoon door naar de aanroeper, precies zoals in de browser. Staat de
  vlag nog van een eerdere blip, dan wordt diezelfde controle ook vóór het overslaan naar de
  lokale bibliotheek gedaan, zodat een herstelde verbinding meteen weer geprobeerd wordt in plaats
  van te wachten op een los connectivity-event.

<!-- release notes -->

- **Management en Bibliotheek toonden soms "geen verbinding" terwijl de telefoon online was.** Eén
  mislukte aanvraag zet de app niet meer blijvend offline.
