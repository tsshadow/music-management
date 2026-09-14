- **`setQueue` liet de afspeeldienst zijn eigen wachtrijwissel rapporteren als een "vorige" gevolgd
  door een "volgende".** Het vervangen van de wachtrij wist eerst de tijdlijn, laadde daarna het
  eerste nummer van de nieuwe lijst en sprong pas dán naar de gevraagde positie; elk van die drie
  tussenstappen had een ander nummer dan de vorige en werd behandeld als een echte
  transportbeweging. De webinterface volgde beide gemelde bewegingen naar `currentTrack`, wat een
  nieuwe `setQueue` uitlokte die dezelfde drie tussenstappen weer opleverde — op de emulator zo'n
  tien keer per seconde, zonder dat het gevraagde nummer ooit ging spelen en de teller op 0:00 bleef
  staan. De plugin onthoudt nu, net als bij een eigen seek, welke positie hij zelf aan het opzoeken
  is en meldt in de tussentijd niets — geen `command`, geen `durationchange`, geen `ended` — totdat
  hij daar daadwerkelijk is aangekomen.

<!-- release notes -->

- **Afspelen op de telefoon-app kon blijven hangen op 0:00 na een wachtrijwijziging.** Nu niet meer.
