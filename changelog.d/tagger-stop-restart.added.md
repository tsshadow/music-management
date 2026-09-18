- **De tagger is vanaf Beheer › Tagger te stoppen en opnieuw van voren te starten.** Een ronde
  doet sinds 0.66.1 eerst de retag-wachtrij en loopt daarna uren door de mappen; wie in de
  tussentijd genres of artiesten besliste, zag de teller staan en `NU RETAGGEN` een 409 geven.
  De pagina pollt nu elke vijf seconden `GET /api/tagger/retag/pending`, dat naast de teller
  `busy` en `stopping` meegeeft. Zolang de tagger loopt staan er `STOP` (`POST /tag/stop`) en
  `OPNIEUW VAN VOREN` (`POST /api/tagger/retag/restart`, nieuw): die laatste breekt de lopende
  ronde af, wacht tot het slot vrij is en start een verse ronde die de wachtrij als eerste
  wegwerkt. De teller blijft staan en zakt terwijl dat gebeurt; hij verdween eerder bij het
  indrukken van de knop, wat een tagger die niets deed onzichtbaar maakte.

<!-- release notes -->

- **De tagger is vanaf Beheer › Tagger te stoppen en opnieuw van voren te starten.** De teller
  van wachtende bestanden blijft in beeld en zakt terwijl de wachtrij wordt weggewerkt.
