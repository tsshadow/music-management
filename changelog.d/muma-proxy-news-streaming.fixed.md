- **Het nieuws afspelen in de webinterface bleef na 0.46.0 hangen op "kon niet afspelen HTTP 504".**
  De vorige poging haalde een overbodige kopie per read weg, maar dat was niet waar de tijd zat.
  Gemeten aan de ontvangstkant op productie: de overdracht begint op 1044 KB/s en zakt naar 92 KB/s
  naarmate de body groeit -- kwadratisch, want Wt's HTTP-client plakt elke read aan de al
  opgebouwde response. 15 MB kostte zo ongeveer 150 seconden, terwijl MuMa het bestand in een halve
  seconde wegschrijft. De proxy stuurt één verzoek tegelijk, dus al die tijd liep ook elke
  artiestafbeelding erachter in een timeout. Een bulletin wordt nu in brokken opgehaald: dat zet
  Wt's eigen buffering uit -- die slaat alleen op zolang er een maximum staat -- en het aan elkaar
  plakken gebeurt in een string die vooraf gereserveerd is, wat wél lineair schaalt.

<!-- release notes -->

- **Nieuws afspelen in de webinterface mislukte nog steeds.** Het bulletin komt nu in seconden
  binnen in plaats van minuten.
