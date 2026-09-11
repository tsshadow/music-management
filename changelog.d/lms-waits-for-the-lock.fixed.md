- **LMS stierf zodra een andere schrijver zijn database vasthield.** De verbinding zette
  `journal_mode=WAL` en `synchronous=normal`, maar geen `busy_timeout` — dus stond die op nul, gaf
  SQLite bij elke botsing meteen `SQLITE_BUSY`, en bij het opstarten kwam dat als onafgevangen
  exception uit `ANALYZE`: proces weg, autoheal herstart, volgende opstart botst opnieuw. Twee
  achtergrondschrijvers van muma kostten de server op één dag 102 en 43 herstarts.
- `busy_timeout=15000`: LMS wacht nu tot vijftien seconden op een slot in plaats van te sterven. WAL
  laat lezers al altijd door, dus dit serialiseert alleen ooit twee schrijvers — en een schrijver van
  muma houdt het slot een paar seconden, niet vijftien.
