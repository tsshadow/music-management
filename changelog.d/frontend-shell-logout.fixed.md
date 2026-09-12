- **Uitloggen in de Android-shell deed zichtbaar niets.** `handleLogout` wiste alleen de
  localStorage-cache en herlaadde de pagina; de credentials op de telefoon zelf bleven staan.
  `bootstrapShell()` las ze bij het opnieuw opstarten gewoon terug uit Kotlin en logde de
  gebruiker meteen weer in, dus de knop leek dood. `handleLogout` wacht nu eerst op het nieuwe
  `platform.system.signOut()` — in de shell wist dat het wachtwoord, de muma API-key/refresh-token
  en de wachtrij op de telefoon; in de browser is het een no-op die meteen resolvet — voordat de
  rest van de sessie wordt gewist en er herladen wordt. Na een nieuwe aanmelding via de Svelte
  LoginPage in de shell schrijft `platform.system.saveCredentials()` het paar ook weer terug naar
  Kotlin, zodat downloads, Android Auto en de klassieke interface dezelfde sessie zien. Een
  Google-aanmelding in de shell doet dat nog niet — dat blijft web-only, zie de code-comment bij
  `handleGoogleResponse`.

<!-- release notes -->

- **Uitloggen in de nieuwe interface op de telefoon werkt nu echt.** Voorheen leek de knop dood:
  na het "uitloggen" was je meteen weer ingelogd.
