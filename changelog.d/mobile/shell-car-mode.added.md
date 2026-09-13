- **`MumaSystemPlugin` en `MumaPlayerPlugin` hadden niets voor het nieuwe rijscherm.** De
  `carConnected`-event bestond al voor de bestaande autodetectie, maar een webscherm dat pas na het
  laden gaat luisteren mist een event dat al is afgevuurd, en er was geen manier om vanuit de
  WebView de wachtrij van de speeldienst te verschuiven of het scherm boven het lockscreen te
  houden zoals de legacy `CarModeFragment` dat via `setShowWhenLocked`/`setTurnScreenOn` deed.
- `MumaSystemPlugin.carState()` geeft de laatste stand van `CarPresence.isInCar` in één keer terug
  voor een koude start; `setKeepScreenOn({showWhenLocked, turnScreenOn})` zet en laat beide vlaggen
  weer los zodra het rijscherm zelf sluit. `MumaPlayerPlugin.next()`/`previous()` roepen
  `MediaPlayerManager.seekToNext()`/`seekToPrevious()` aan — dezelfde aanroep die de legacy
  `CarModeFragment` al deed — zodat de bestaande `tick()`-polling de zet net als een druk op het
  stuurwiel terugmeldt, in plaats van dat de WebView een tweede wachtrij bijhoudt.

<!-- release notes -->

- De speeldienst en de auto-detectie ondersteunen nu het rijscherm van de nieuwe interface.
