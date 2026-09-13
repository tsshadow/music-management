- **Radio en het nieuws van het uur speelden helemaal niet op de telefoon in de nieuwe interface.**
  Radio stuurt het `<audio>`-element rechtstreeks aan om halverwege een nummer in te haken, en een
  bulletin speelt van een blob-URL af; de schil heeft geen van beide -- `PlaybackService` bezit de
  afspeeldienst. Beide knoppen gaven meteen op met "speelt nog niet in de app". De speeldienst had
  die twee al, ingebouwd voor Android Auto en Assistent (`RadioPlaybackController`/`RadioSync.kt`,
  `NewsPlaybackController`/`NewsQueueRules.kt`): een kanaal starten is één media-id die
  `onAddMediaItems` al herkent, een bulletin is één sessiecommando dat al beide kanten van de wissel
  op zich neemt, inclusief het opnieuw intunen van radio als die aan stond. Twee nieuwe
  plugin-methoden (`startRadio`/`stopRadio`/`toggleNews`) en twee velden op `state()`
  (`radioChannel`/`newsPlaying`) zijn de hele uitbreiding; de webinterface merkt zo ook een kanaal of
  bulletin op dat van buiten de WebView kwam -- Android Auto, Assistent, of een WebView die is
  herschapen terwijl er iets speelde -- en bouwt de juiste knoppen dan terug op in plaats van een
  gewone wachtrij te tonen.

<!-- release notes -->

- Radio en het nieuws van het uur werken nu ook op de telefoon in de nieuwe interface.
