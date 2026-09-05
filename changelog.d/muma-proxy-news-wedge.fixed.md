- **Het nieuws afspelen in de webinterface gaf "kon niet afspelen" en legde en passant de hele
  MuMa-proxy plat.** De browser haalt een bulletin als blob op omdat een `<audio>`-element geen
  `X-API-Key` kan meesturen, en die 15 MB gaat door `MumaResource`. Gemeten op productie: MuMa
  schrijft het bestand in 0,9 seconde weg, maar de proxy gaf na 30 seconden 504 en de wachtrij
  bleef daarna nog 158 seconden bezet -- die stuurt één verzoek tegelijk, dus elk artiestplaatje
  erachter liep ook in een timeout ("Timeout waiting for MuMa response for artist ..."). De oorzaak
  zat niet in de recorder en niet in het netwerk: `SendQueue` hing een callback aan Wt's
  `bodyDataReceived`, ongeacht of het verzoek streamde. Wt leest in kleine stappen, dus een
  bulletin kwam binnen in tienduizenden read-completions, en elk daarvan werd gekopieerd en naar de
  strand gepost voor een handler die vervolgens niets deed. Die kopie gebeurt nu alleen nog voor een
  verzoek dat de brokken echt gebruikt -- dat is uitsluitend het downloaden van podcastafleveringen.

<!-- release notes -->

- **Nieuws afspelen in de webinterface mislukte, en blokkeerde daarbij tijdelijk de rest van de
  app.** Het bulletin komt nu meteen door.
