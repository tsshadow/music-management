- **Nieuwe interface: inloggen op een verse installatie.** Zolang de app nog nooit was ingelogd
  stond de actieve server op "Offline", waarvan het adres `http://localhost` is -- precies de
  plek waar de webspeler zijn eigen pagina vandaan haalt. Elke aanroep kreeg daardoor de
  inlogpagina zelf terug in plaats van een antwoord van de server, en de ingevoerde gegevens
  werden niet bewaard omdat de Offline-server geen wachtwoord kent. De schil leest nu altijd de
  echte server, en een inlog vanuit de webspeler maakt die server ook actief, zoals de oude
  inlogdialoog al deed.

<!-- release notes -->

- Inloggen in de nieuwe interface werkt nu ook op een app die nog nooit was ingelogd.
