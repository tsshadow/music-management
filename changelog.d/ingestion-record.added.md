- **Wat een bestand zei vóórdat de tagger het aanraakte, wordt nu vastgelegd.** De tagger
  herschrijft tags ter plekke en bewaarde geen kopie. `ORIGINAL_TITLE` en `ORIGINAL_ARTIST` zijn de
  twee velden waarvan iemand merkte dat ze verdwenen en waar toen met de hand een redding voor is
  gebouwd, elk in een eigen regel; van de rest was er geen antwoord op "waar kwam dit bestand mee
  binnen". En ook niet op "welke regel besliste dat", want de regels staan in de database en
  veranderen. Nieuwe tabel `library_ingestion_records` (`migrate_v22_ingestion_records.sql`) met per
  bestand de volledige tagset zoals gelezen, de versie van de code, en een vingerafdruk van de
  regeltabellen op dat moment.
- Eén rij per bestand, geschreven de eerste keer dat de tagger het opent en daarna nooit meer
  bijgewerkt: een latere ronde ziet een bestand dat deze tagger al herschreven heeft, dus zijn idee
  van "binnenkomst" is minder waard dan dat van de eerste. De vingerafdruk is één query per
  tagronde, niet per bestand.
- Bewust geen kopie van het bestand. De tagger verandert de audiostream niet, dus 5,3 TB audio
  dupliceren beantwoordt een vraag die niemand stelt; wat er op het spel staat is de metadata, en
  dat is een paar honderd bytes per track.

<!-- release notes -->

- **MuMa onthoudt nu wat een nummer zei toen het binnenkwam.** Tot nu toe overschreef de tagger de
  tags zonder iets te bewaren, dus een verkeerde regel was niet meer terug te zien.
