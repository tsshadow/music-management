- **Festivals worden nu echt geïndexeerd.** `FESTIVAL` stond nooit in de extra tags van de
  LMS-scanner op productie -- een runtime-instelling die alleen in een ontwerpdocument
  genoemd werd -- dus de festivalpagina's, de festivalchip in de nummerdetails en het nieuwe
  `festivals`-veld op het song-node bleven leeg terwijl de tagger al maanden `TXXX:FESTIVAL`
  schreef. Migratie V119 voegt de tag toe aan `scan_settings.extra_tags_to_scan` (achter wat er
  al stond, één keer) en verhoogt de audio-scanversie, zodat de eerstvolgende scan de hele
  bibliotheek één keer herleest en de clusters vult.
- **De kanaalregel in de nummerdetails is een plek om heen te gaan.** Een kanaal dat als label
  gecureerd is opent die labelpagina; een kanaal dat als artiest gecureerd is opent een zoekactie
  op die naam. Een ongecureerd kanaal blijft tekst.

<!-- release notes -->

- **Festivals worden nu echt geïndexeerd.** De scanner leest de festivaltag voortaan mee; na de
  eerstvolgende volledige scan zijn de festivalpagina's en -chips gevuld.
- **Kanaal in de nummerdetails is tikbaar** als het aan een label of artiest gekoppeld is.
