- **De SAST-baseline gooide de onderbouwing weg die iemand er met de hand in had gezet.** Het hele
  bestand wordt bij elke `SAST_WRITE_BASELINE=1` opnieuw opgebouwd uit `REASONS`, maar de redenen
  staan óók in dat bestand — en dat is waar je ze leest, dus daar werden ze bewerkt. Dat is twee keer
  misgegaan: één keer zo hard dat degene die het herstelde een waarschuwing voor de volgende lezer in
  het bestand achterliet, en op 2026-09-08 opnieuw, goed voor 36 regels audit-werk. Er stond geen
  enkele test op dit script, en dat is precies hoe hetzelfde ongeluk zich kon herhalen.
- Elke sectiekop draagt nu een stempel (`# --- <regel> --- [r:abc12345]`) van de tekst die de
  generator er zelf neerzette. Klopt de tekst nog bij dat stempel, dan mag hij vervangen worden — een
  reden bijwerken blijft dus een gewone bewerking. Klopt hij niet meer, dan heeft een mens er getypt
  en **weigert de generator te schrijven**: hij toont wat er verloren zou gaan en zegt dat het in
  `REASONS` thuishoort. `SAST_BASELINE_FORCE=1` overrulet dat en gooit het alsnog weg.
- Vergelijken met `REASONS` in plaats van met een stempel kan niet: dan is "iemand heeft hier getypt"
  niet te onderscheiden van "de reden is bijgewerkt", en zou elke normale bewerking de generator
  blokkeren.
- De vijf secties die alleen in het bestand stonden zijn naar `REASONS` verhuisd — de ntfy-URL, de
  LmsScanTrigger-noot, de audit van `SoundcloudArchive.py` en `events.py`, de geschiedenis van de
  tools-container van x3 naar x5, en de rechtenreden van de importer. Woord voor woord nagelopen: er
  is niets inhoudelijks verdwenen.
- `tests/ci/test_sast_baseline_rationale.py` pint het vast, inclusief een test die de baseline van
  déze repository leest en faalt zodra er weer een alinea in staat die een regeneratie niet kan
  reproduceren.
