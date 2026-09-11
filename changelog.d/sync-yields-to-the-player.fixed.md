- **De versie-sync legde de speler plat.** LMS sterft aan een vergrendelde database — een
  onafgevangen exception, het proces stopt — en de sync hield dat slot vast: elke ronde alle 285.671
  rijen herschrijven, met dertig seconden geduld per statement en vijftien seconden tussen elke
  nieuwe poging. Resultaat: **102 herstarts** en een onbereikbare bibliotheek.
- De rolverdeling was omgekeerd. Dit is een achtergrondtaak en LMS is de speler; als beide hetzelfde
  slot willen, hoort degene naar wie niemand luistert te wijken. De wachttijd gaat van dertig
  seconden naar twee, het aantal pogingen van tien naar drie, en de pauze ertussen van vijftien
  seconden naar een minuut — wachten in plaats van duwen. Wat blijft liggen kost niets: de volgende
  ronde schrijft dezelfde rijen.
- **En er wordt alleen nog geschreven wat verandert.** De `UPDATE` draagt dezelfde vier waarden
  nogmaals als voorwaarde, dus een rij die het al goed heeft wordt niet aangeraakt. Na de eerste
  ronde is dat vrijwel alles: 285.000 ongewijzigde rijen per uur herschrijven is wat deze taak
  überhaupt in het pad van de speler bracht.
- **Een mislukte sync liet zijn verbinding open staan.** `sqlite_conn.close()` stond ná de
  `try`-body, dus bij een fout werd hij overgeslagen en bleef de transactie hangen — een slot dat
  niemand meer losliet. Nu in een `finally`.
