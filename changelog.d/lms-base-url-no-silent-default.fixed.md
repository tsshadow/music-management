- **Een muma-container zonder LMS-configuratie belde productie, en niets zei dat.** `lms_base_url()`
  viel bij ontbrekende configuratie terug op een hardgecodeerde `http://lms:5082`. Op de deployment
  klopt dat — `lms` is de container_name van de apart uitgerolde LMS-stack op hetzelfde netwerk — en
  juist dát maakte het gevaarlijk: een kale hostnaam wordt opgelost door de DNS die de host toevallig
  heeft, en op het kantoor-LAN wijst `lms` naar 192.0.2.27. De verouderde lokale stack op een
  werkstation belde daardoor **productie** elke vijf seconden met een sleutel die productie niet kent.
  Aan geen van beide kanten was dat te zien: LMS logt de weigering (`code = 44, msg = 'Invalid API
  key.'`) zónder client-adres, dus het leest als een storing in prods eigen radio-thread. Alleen het
  access-log van de reverse proxy verried dat de requests van een ontwikkelmachine kwamen. Er is nu
  geen default meer: ontbreekt alles, dan volgt een `LmsNotConfigured` met een leesbare melding, en
  `radio.py` degradeert dat tot één logregel per poging in plaats van stil verkeer naar andermans
  server. Meegenomen: `MUMA_SERVER_HOSTS` wordt nu ook gelezen. Dat is de variabele die
  `docker/docker-compose.yml` voor deze service daadwerkelijk zet, mét een commentaarblok waarom —
  de oude code las hem niet, dus de deployment werkte per toeval doordat de hardgecodeerde default
  toevallig gelijk was aan de ingestelde waarde.

<!-- release notes -->

- **Een verkeerd geconfigureerde muma-container kon ongemerkt de productieserver bevragen.** Dat kan
  niet meer: zonder expliciete LMS-instelling stopt de radio met een duidelijke melding in plaats van
  een adres te gokken.
