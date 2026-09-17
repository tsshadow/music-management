- **Een radiokanaal bewerken of verwijderen in Beheer gaf een 405.** De webkant praat via de
  LMS-proxy (`/muma/api/...`) met MuMa, en die proxy stuurde elke PUT en DELETE door als een
  POST — met een opmerking in de code erbij dat dat waarschijnlijk niet klopte. MuMa antwoordde
  dan netjes `405 Method Not Allowed` voor `PUT /api/radio/channels/main`, en de browser toonde
  een method-fout voor een verzoek dat hij nooit zo verstuurd had. Het zag eruit als een kapotte
  route in MuMa; de route was goed. De http-client van de server kent PUT en DELETE nu als eigen
  verzoeken (`sendPUTRequest`/`sendDELETERequest`, boven `Wt::Http::Client::put` en
  `deleteRequest`) en de proxy geeft het echte werkwoord door. Een unittest tegen een lokale
  server controleert per werkwoord wat er op de lijn staat, en de ketentest maakt, hernoemt en
  verwijdert een kanaal via de proxy. De artiestafbeeldingen-routes blijven POST-only: die zijn zo
  gebouwd toen dit nog niet kon.

<!-- release notes -->

- **Een radiokanaal bewerken of verwijderen in Beheer gaf een 405.** De proxy tussen de webkant
  en MuMa maakte van elke PUT en DELETE een POST. Hij stuurt nu het echte werkwoord door.
