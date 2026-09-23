- **Een diagnostiekrapport na een autorit bevatte de autorit niet.** De ringbuffer houdt 600
  regels, en de downloadservice vulde die in zijn eentje: elke al gecachete track van de komende
  wachtrij ging bij elke afspeelwijziging opnieuw naar een downloadtaak, die "already exists"
  logde — ongeveer één regel per twee seconden. Rapport 37 besloeg daardoor 2,5 minuut; van de rit
  ervoor stond alleen de ontkoppeling er nog in. Oorzaak was een filter dat elke track doorliet
  (zijn `false` verdween binnen een `let`); dat filtert nu echt, en dezelfde track kan niet meer
  drie keer tegelijk in de wachtrij komen — die dubbele taken gaven de `Failed to delete
  .partial`-excepties. Verbose regels gaan niet meer in de ringbuffer, een herhaalde waarschuwing
  komt er één keer per minuut in met het aantal dat is ingehouden, en een stacktrace wordt na 12
  regels afgekapt.
- **Genrekleuren zonder MuMa vroegen het elke tegel opnieuw.** Een mislukte ophaalpoging liet de
  cache ongemoeid, dus elke genretegel op een browse-niveau deed een nieuwe netwerkaanroep en
  logde dezelfde waarschuwing — 266 keer in één seconde in rapport 34. Na een mislukking wacht de
  cache nu 30 seconden.
- **De auto-knoppen staan nu in het rapport.** Elke gepubliceerde knoppenset wordt gelogd met
  actie en media3-icoonconstante, en een verbinding met de controller die hem maakte (`gearhead`
  voor Android Auto). Android Auto zegt niets als hij een knop weglaat; zo is te zien of de app hem
  niet publiceerde of de auto hem niet tekende.
<!-- release notes -->
- **Diagnostiekrapporten bevatten weer wat er gebeurde.** De downloadservice vulde het logboek met
  ruis, waardoor een autorit uit het rapport verdween; dat is opgelost, en de knoppen die de app
  aan de auto geeft staan er nu in.
