- **Elk verzoek aan de server loopt nu via één resolver, en er verandert niets zichtbaars.** Zo'n
  twintig bestanden deden zelf `fetch(\`/rest/...\`)` op basis van de pagina-origin — cover art,
  streams, playlists, scans — terwijl `/api/*`-aanroepen al via `apiBase()`/`mumaApiUrl` liepen.
  Binnen de komende Capacitor-schil is de pagina-origin `https://localhost`, dus zo'n relatieve
  `/rest/...` zou tegen de WebView praten in plaats van tegen de muziekserver. `restUrl()` in
  `src/lib/store.js` bouwt nu elke Subsonic-URL op `credentials.url`, met dezelfde terugval naar
  `window.location.origin` die er al was; op het web is dat exact dezelfde string als een relatieve
  fetch. De derde kopie van die terugval in `LoginPage.svelte` is vervangen door de helper. Fase 0
  van `docs/designs/universal-ui/`.

<!-- release notes -->

- Grondwerk voor de toekomstige app-schil: elk verzoek aan de server loopt nu via één plek in de
  code. Aan wat je ziet of hoort verandert niets.
