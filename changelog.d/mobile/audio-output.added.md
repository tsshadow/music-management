- **De speler benoemt de audio-uitvoer en opent de uitvoerkiezer.** `MumaSystem` kreeg
  `outputRoute()` (de aangesloten Bluetooth-, bedrade of USB-uitvoer, anders de luidspreker, uit
  `AudioManager.getDevices`), het event `outputRouteChanged` (een `AudioDeviceCallback` die
  meeloopt met de plugin) en `openOutputPicker()` (het MEDIA_OUTPUT-paneel van Android 11+, met de
  Bluetooth-instellingen als terugval). Twee nieuwe strings, `audio_output.wired` en
  `audio_output.speaker`, in het Engels en Nederlands.

<!-- release notes -->

- De speler laat zien via welke uitvoer je luistert; tikken opent de uitvoerkiezer van Android.
