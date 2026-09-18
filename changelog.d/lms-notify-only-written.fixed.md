- **De tagger meldt een map alleen nog aan LMS als er echt een bestand in geschreven is.** Een
  volledige ronde loopt elke map af en laat vrijwel alles zoals het was, maar meldde elke map
  toch: LMS logde op 2026-09-18 13.798 scanverzoeken in drie uur tegenover 7 opgeslagen
  bestanden, en las per verzoek ~1.000 bestanden van de NAS opnieuw, urenlang achter elkaar.
  `BaseSong.save_file()` zegt nu of het geschreven heeft, `_parse_worker` geeft `SAVED` naast
  `OK` en `SKIPPED` terug, en zowel de mapwalk als de retag-wachtrij melden alleen mappen met
  een geschreven bestand. Wat wel geschreven is komt net zo snel in de app als eerst.

<!-- release notes -->

- **LMS scant niet meer de hele nacht door achter een tagger-ronde aan** die niets veranderde.
  Een map komt alleen nog bij LMS terecht als er echt een tag in is herschreven.
