- **De nieuwe interface kende geen rijscherm.** De Kotlin-app opent al jaren automatisch een groot
  scherm — vorige/afspelen/volgende, ster-beoordeling, microfoon voor spraak, genre- en
  favorieten-mixtegels — zodra de telefoon een gekoppelde auto ziet, maar de webspeler in de nieuwe
  schil had daar niets tegenover: een auto die verbond liet de gebruiker gewoon op het gewone scherm
  zitten.
- Een `CarModeView` op route `car` doet nu hetzelfde: transport en beoordeling lopen via de
  bestaande `platform.player`/`setRating`-paden (geen tweede wachtrij-eigenaar), de mixtegels
  starten dezelfde shuffle-wachtrij als de Kotlin-tegels deden, en het scherm opent zelf zodra
  `platform.system.carConnected` afgaat of, bij een koude start die de verbinding al mist, via een
  eenmalige `carState()`-check. Wegtikken sluit het scherm voor de rest van deze rit — een dubbel
  signaal van dezelfde verbinding (denk aan een bluetooth-hapering) opent het niet opnieuw — en de
  volgende keer dat de auto verbindt, wel weer. Ook bereikbaar via het overflow-menu.

<!-- release notes -->

- De webspeler heeft nu een rijscherm: grote knoppen, sterren om te beoordelen en snelle
  genre-mixtegels, dat zelf opent zodra de telefoon een gekoppelde auto ziet.
