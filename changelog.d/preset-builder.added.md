- **Geavanceerd zoeken, en het resultaat bewaren als snelkoppeling.** Nieuw op `/new-preset`
  (via "+ Nieuwe snelkoppeling" boven de tegels op het startscherm, en op de telefoon bovenaan
  het tabblad Zoeken): kies zoveel genres, artiesten, labels, festivals en jaren als je wilt —
  binnen één soort telt elk, ertussen moeten ze allemaal kloppen — plus een ratingbereik,
  sortering, nummers of sets en een aantal. De lijst eronder volgt de keuze live via dezelfde
  `getSongs`-clusteraanroep die een tegel afspeelt. Opslaan maakt er een dynamische
  afspeellijst van in MuMa, in de tegel-spelling die de Kotlin-app leest: een tegel op het
  startscherm, en sinds Android Auto die lijst van de server leest ook een rij in de auto onder
  Afspeellijsten. Een bestaande tegel is nu te bewerken via "Bewerken" in het menu van de
  tegelpagina (`/preset/<id>/edit`); de snelle "opslaan als preset" op een gefilterde lijst
  blijft bestaan en schrijft dezelfde spelling.

<!-- release notes -->

- **Geavanceerd zoeken.** Zoek op meerdere genres, artiesten, labels, festivals en jaren
  tegelijk, met rating en sortering, en bewaar het als snelkoppeling op je startscherm — en in
  de auto. Bestaande snelkoppelingen zijn nu ook te bewerken.
