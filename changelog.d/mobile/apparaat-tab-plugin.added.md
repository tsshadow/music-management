- **`MumaSystem` kreeg vier methodes erbij voor de webspeler's instellingen-tab.**
  `listBondedDevices()` geeft de gekoppelde bluetooth-apparaten met wie een auto is; het schrijven
  van `carModeDevices` via `setSetting` gaat voor het eerst via een echte set in plaats van een
  aantal. `requestCarModeFullScreenPermission()` en `pickCacheLocation()`/
  `clearCustomCacheLocation()` doen wat de klassieke rijen voor volledig-scherm-toestemming en
  cachelocatie altijd al deden, nu bereikbaar zonder het klassieke scherm te openen.
  `setAppLocale()` past de taal van de shell zelf aan (vergunningsschermen, deelvensters), niet
  alleen de tekst van de webinterface.
