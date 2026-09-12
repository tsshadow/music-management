- **In de nieuwe interface op de telefoon begon een aangetikt nummer nooit te spelen.** De
  afspeeldienst kreeg de wachtrij wél binnen, maar bleef op pauze staan: het `setQueue`-bericht
  vroeg niet om te starten, en het `load`-bericht dat dat daarna moest doen werd weggegooid door de
  bewaker "de dienst staat al op dat nummer" — want het aannemen van een wachtrij zet de dienst
  meteen op die positie. Een kaartje op het startscherm of een zoekresultaat kwam nog verder: dat
  zet alleen het huidige nummer en geen wachtrij, en de dienst kan alleen spelen wat hij vasthoudt,
  dus daar gebeurde helemaal niets. Het startverzoek reist nu mee met de wachtrij, en een nummer
  zonder lijst erachter wordt zelf de wachtrij. De unit-test hierop kon dit niet zien: de nagemaakte
  speler verzette het huidige nummer niet bij `setQueue`, zoals de echte plug-in dat wel doet.

<!-- release notes -->

- **In de nieuwe interface op de telefoon begon een aangetikt nummer niet te spelen.** Nu wel.
