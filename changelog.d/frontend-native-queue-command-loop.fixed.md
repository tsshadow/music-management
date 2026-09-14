- **De webinterface hielp een lus op de telefoon-app in stand houden die het afspelen nooit liet
  starten.** Een commando van de afspeeldienst zonder nummer en zonder wachtrijlengte — de
  tussentoestand van een wachtrijwissel die zichzelf nog aan het bijwerken was, niet een echte
  "vorige" of "volgende" — werd tot nu toe gelezen als een stap in de eigen wachtrij, wat
  `currentTrack` verplaatste en een nieuwe wachtrij naar de telefoon stuurde. De hand-off stapt nu
  niet meer op een leeg commando, en onthoudt bovendien bij welke wachtrij en positie al eerder is
  gestuurd, zodat dezelfde stand nooit twee keer wordt doorgegeven — ook niet wanneer de
  afspeeldienst zelf tijdelijk een verouderde stand teruggeeft.

<!-- release notes -->

- **Afspelen op de telefoon-app kon blijven hangen op 0:00 na een wachtrijwijziging.** Nu niet meer.
