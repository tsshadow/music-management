- **De lms.db-sync liep zes keer per uur in plaats van één keer.** Er draait een tweede
  LMS-instantie (`alpha`) die de migratie naar databaseversie 118 nooit heeft gedraaid. De
  herhaalpoging uit 0.55.0 zag daardoor elke ronde "server nog niet gemigreerd" en herhaalde de
  vólledige pass — 285.360 tracks, ook voor de server die net correct was weggeschreven. Zes keer
  per uur, tegen een database die de speler open heeft staan.
- Een herhaalpoging gaat nu alleen nog over de servers die daadwerkelijk zijn overgeslagen. De eerste
  ronde dekt alles, elke volgende noemt precies de instantie waarop gewacht wordt — en de
  waarschuwing daarna zegt welke dat is, in plaats van hoeveel het er waren.
