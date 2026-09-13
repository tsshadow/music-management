- **De playlists-tab en playlist-detailpagina omzeilden de offline-schakelaar volledig.** `Dashboard.svelte`
  haalde `getPlaylists` en `PlaylistView.svelte` haalde `getPlaylist` met een losse `fetch` op, terwijl
  elke andere lijst via `subsonicJson()` gaat -- die valt terug op `platform.storage.query` zodra de
  shell geen route naar de server heeft. Beide gaan nu via `subsonicJson()`, en `playlists`/
  `playlist-detail` staan in `viewHasOfflineSource` zodat de weergave dat ook weet. Zie het
  gelijktijdige mobile-fragment voor het `OfflineSubsonic`-antwoord dat dit nu daadwerkelijk kan
  beantwoorden.
- **Er bestond een tweede, ongebruikte "wifi only voor downloads"-instelling.** De `downloadsWifiOnly`
  store in `store.js` werd naar het account gesynchroniseerd, maar de enige plek die hem kon
  schrijven rendert nooit (de rij bestaat alleen als `platform.storage.supported`, en dan schrijft
  `GeneralSettings.svelte` al rechtstreeks de echte Kotlin-instelling). Die dode store, zijn
  `persist`-regel en de account-sync zijn verwijderd; `Settings.isWifiRequiredForDownload` (geschreven
  via de `wifiOnly`-sleutel) is de enige plek waar dit nog vandaan komt. `DownloadService` bleek die
  vlag al te lezen en een download op mobiel netwerk al te laten wachten tot wifi terug is.

<!-- release notes -->

- Playlists werken nu ook zonder verbinding, net als de rest van de bibliotheek. Een oude,
  ongebruikte kopie van de "alleen via wifi downloaden"-instelling is opgeruimd.
