- **De ntfy-melding van een download noemde de releasedatum niet.** De pushtekst is letterlijk
  `str(song)`, en die lijst somde titel, artiest, album, genre, publisher en pad op -- de datum zat
  er nooit in, terwijl dat juist het veld is waarop je een download beoordeelt. `BaseSong.__str__`
  zet er nu een regel `Released=` bij, wat in één klap ook de SoundCloud- en de import-melding
  vult, want alle drie sturen dezelfde string. De keuze tussen `DATE` en `ORIGINALDATE` volgt
  dezelfde regel als de web-UI en de app: neem de originele datum alleen als hij minstens zo
  precies is. Nieuw is dat de Python-kant ook de ongescheiden `20260903` aankan die yt-dlp als
  `upload_date` in `DATE` schrijft, en dat een scene-tag `2026-00-00` als `2026` uitkomt in plaats
  van als `00-00-2026`. Een videodownload wordt niet getagd en heeft dus geen Song; die melding
  leest de datum nu rechtstreeks uit het info-dict van yt-dlp.

<!-- release notes -->

- **Een melding dat er iets gedownload is, vermeldt nu de releasedatum.**
