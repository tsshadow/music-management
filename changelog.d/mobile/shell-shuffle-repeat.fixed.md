- **`MumaPlayer` had geen manier om shuffle of herhalen te zetten.** De speeldienst
  (`MediaPlayerManager`/ExoPlayer) kent `isShufflePlayEnabled` en `repeatMode` al langer, maar de
  webinterface in de nieuwe schil kon er niet bij: shuffle en herhalen bleven een beslissing van de
  WebView, die geen weet had van de eigen wachtrijvolgorde van de dienst. Een nieuwe `setMode`-
  plugin-methode zet beide op de dienst en levert de toegepaste stand terug; `state()` en elke
  status-event bevatten `shuffle`/`repeat` voortaan ook, en een polling-tick merkt een stand die van
  buiten de WebView kwam -- Android Auto's eigen knop, de melding -- ook op zonder dat er iets
  anders beweegt.

<!-- release notes -->

- Shuffle en herhalen in de nieuwe interface sturen nu de speeldienst zelf aan, niet meer alleen
  het scherm.
