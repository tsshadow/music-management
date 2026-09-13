- **`MumaPlayer` had geen manier om radio of het nieuws van het uur te starten.** Beide bestonden al
  op de speeldienst -- `RadioPlaybackController`/`RadioSync.kt` en
  `NewsPlaybackController`/`NewsQueueRules.kt`, gebouwd voor Android Auto's kanalenlijst en
  Assistent -- maar de webinterface in de nieuwe schil kon er niet bij. Drie nieuwe plugin-methoden
  (`startRadio`, `stopRadio`, `toggleNews`) sturen dezelfde media-id en dezelfde sessiecommando's aan
  die de auto al gebruikt, dus er is geen tweede implementatie van de tijdlijn-synchronisatie of het
  terugzetten van een onderbroken wachtrij bijgekomen. `state()` en elke status-event dragen voortaan
  ook `radioChannel`/`newsPlaying`, zodat de webinterface een kanaal of bulletin opmerkt dat van
  buiten kwam.

<!-- release notes -->

- Radio en het nieuws van het uur sturen in de nieuwe interface nu de speeldienst zelf aan, net als
  shuffle en herhalen al deden.
