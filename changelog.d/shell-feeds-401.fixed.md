- **Release Radar en Daily Mix laadden niet in de shell (telefoon/tablet), wel op desktop.**
  `feeds.js` haalde `/api/feeds/release-radar` en `/api/feeds/daily-mix` op zonder de
  `X-API-Key`-header mee te sturen — elke andere `/api/*`-aanroep in de app (curatie,
  genre-regels, presets) doet dat wel. De server wijst een feed-aanvraag zonder key af met
  401, want een feed is per account: de systeemsleutel mag nooit iemands eigen aanbevelingen
  opvragen. Beide feeds sturen de sleutel nu net als de rest van de app.

<!-- release notes -->

- Release Radar en Daily Mix laden nu weer op alle apparaten.
