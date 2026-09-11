- **"Algemene API-fout", "Playback could not start", "Scrobble failed HTTP 500" — één oorzaak.** Elk
  geauthenticeerd verzoek deed een schrijftransactie op het auth-token: gebruiksteller ophogen,
  `last_used` bijwerken. Dbo versioneert die rij, dus twee verzoeken met hetzelfde token — het nieuwe
  startscherm van de app vuurt er meerdere tegelijk af — laden allebei versie 165, de tweede
  schrijver verliest, en dát verzoek wordt afgebroken met `Uncaught exception from handleRequest`.
  Negen keer in een uur op één token; om 08:55:36 drie binnen een halve seconde: stream, scrobble en
  cover art tegelijk.
- De schrijfactie gebeurt nu alleen als hij ertoe doet: een token met een gebruikslimiet houdt zijn
  teller, en `last_used` schuift hooguit één keer per minuut in plaats van bij elke aanroep. Al het
  andere blijft een leesactie.
- Verliest een verzoek die race alsnog, dan wordt dat genegeerd in plaats van het verzoek af te
  breken. De andere kant heeft dezelfde rij net bijgewerkt; het token was geldig toen we keken, en
  een aanroep laten mislukken over een boekhoudkundige botsing is de ene uitkomst die niet kan.
