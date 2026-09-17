- **De speler op de telefoon vertelt nu waar het geluid heen gaat.** Onder de bedieningsknoppen
  staat de huidige uitvoer — "Bose QC35 II", "Bedrade koptelefoon", "Telefoonluidspreker" — in
  de accentkleur; een tik opent de uitvoerkiezer van Android (of de Bluetooth-instellingen op een
  toestel zonder kiezer). Het label volgt een koptelefoon die verbindt of een stekker die eruit
  gaat zonder de speler te heropenen. Alleen in de app: de browser weet niet waar zijn geluid
  naartoe gaat en toont niets. Het `platform.system`-contract kreeg `outputRoute()`,
  `onOutputRouteChanged()` en `openOutputPicker()`; de browser antwoordt `null` en doet niets.

<!-- release notes -->

- De speler in de app laat zien via welke uitvoer je luistert en opent met één tik de
  uitvoerkiezer van Android.
