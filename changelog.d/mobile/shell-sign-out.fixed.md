- **`MumaSystem` kon een sessie niet beëindigen.** De Svelte-shell had geen manier om de op de
  telefoon opgeslagen server-credentials te wissen, dus een "uitloggen" in de webinterface liet
  Kotlin's eigen kopie gewoon staan en de volgende `bootstrapShell()` logde meteen weer in. Nieuwe
  pluginmethode `MumaSystem.signOut()` maakt nu hetzelfde op die Kotlin doet als de klassieke
  uitlogknop: `ActiveServerProvider.signOut()` (nieuw, hergebruikt door beide kanten) wist het
  wachtwoord, de muma API-key/user-id en de versleutelde muma-tokens in `SecureSettings` — de
  gebruikersnaam blijft staan, net als bij de klassieke knop. De wachtrij gaat via
  `MediaPlayerManager.clear()`, niet via `onDestroy()`: die laatste breekt de hele
  app-brede speler af (root `single`, zie `di/MediaPlayerModule.kt`) in plaats van alleen de sessie
  te sluiten. Gedownloade bestanden blijven ongemoeid.
- **Een nieuwe aanmelding in de shell kwam nooit bij Kotlin terecht.** Nieuwe pluginmethode
  `MumaSystem.saveCredentials({url, username, password})` schrijft een geverifieerd paar terug via
  `ActiveServerProvider.saveCredentials()` (dezelfde weg als het server-instellingenscherm), zodat
  downloads, Android Auto en de klassieke interface na een aanmelding in de webinterface dezelfde
  sessie zien.

<!-- release notes -->

- **Uitloggen in de nieuwe interface werkt nu ook aan de Kotlin-kant.** Een nieuwe aanmelding daar
  wordt voortaan ook door de klassieke app en Android Auto herkend.
