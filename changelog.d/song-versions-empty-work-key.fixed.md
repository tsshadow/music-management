- **117 losse nummers stonden als één song in de database.** De groeperingssleutel van de
  song-versies is `artiest:::titel`, met de versiemarkering uit de titel gestript. Een titel die na
  dat strippen niets overhoudt — leeg, één duif-emoji, een reeks combining marks, of alleen
  `(Radio Edit)` — leverde de sleutel `:::` op, en de UNIQUE-index op `work_key` maakte daar één
  work van. Op productie zat werk 89834 daardoor op 117 niet-verwante opnames, met nog 543
  titelloze tracks in de wachtrij om zich erbij te voegen. Zo'n titel identificeert niets, dus
  krijgt de track nu een sleutel voor zichzelf (`track:<id>`, naast de bestaande `split:<id>`); een
  lege *artiest* groepeert nog wel gewoon op titel, want de helft van deze bibliotheek heeft geen
  `primary_artist_id` en zet de artiest in de titel. `scripts/repair_song_works.py --dry-run`
  rapporteert wat er verkeerd staat, zonder vlag maakt het de groepering los zodat de worker
  opnieuw indeelt.
- **`library_works.work_key` vergeleek niet op bytes.** De kolom erfde `utf8mb4_general_ci`, waarin
  elk teken buiten de BMP hetzelfde collatiegewicht heeft: twee sleutels van gelijke lengte uit
  zulke tekens zijn dan gelijk, en de UNIQUE-index voegde hun works samen zonder een fout te geven.
  Exact de val die `migrate_v13` voor `channels.normalized_name` opruimde.
  `migrate_v18_work_key_binary.sql` zet de kolom op `utf8mb4_bin`; het repairscript haalt de rijen
  uit elkaar die al waren samengevoegd, doordat het van elke track de sleutel hérberekent in plaats
  van naar één symptoom te zoeken.
- **`migrate_v13` deed zelf nooit iets.** De guard telde de kolommen die al `utf8mb4_bin` zijn en
  koos bij `COUNT(*) = 0` de tak "is already utf8mb4_bin" — dus op een database die de migratie
  nodig had, sloeg hij hem stil over, en alleen op een al gemigreerde voerde hij de ALTER uit. Prod
  staat goed omdat `db_init.py` de tabel meteen binair aanmaakt, maar het bestand deed niet wat het
  claimt. De voorwaarde is omgedraaid.
- **Een track kon gescoord worden op de helft van zijn bestanden.** De batchquery van de worker
  limiteerde ná de join op `library_media_files`, en `LIMIT` telt gejoinde rijen. De laatste track
  van een batch werd zo afgesneden van zijn resterende bestanden, kwam mét work uit de ronde en
  keerde dus nooit terug: zijn FLAC kon één rij voorbij de limiet liggen terwijl zijn MP3 de
  canonieke versie werd. De batch wordt nu vóór de join gekozen.
- **Een gesplitste track bleef de oude groep besturen.** `split_track()` verplaatst de track maar
  liet de pin van de oude work naar hem wijzen, en `recompute_canonicals()` volgde die pin blind —
  waarmee de oude song een canonieke versie kreeg die inmiddels een andere song is. De pin wordt
  bij het splitsen gewist, en een pin die geen lid meer is telt niet meer mee.

<!-- release notes -->

- **117 niet-verwante nummers stonden als één song in de bibliotheek.** Nummers zonder bruikbare
  titel — leeg, of alleen een emoji — werden allemaal op één hoop gegooid. Ze krijgen nu elk hun
  eigen plek. Er is nog niets van te zien in de app: het versiemodel wordt achter de schermen
  opgebouwd.
