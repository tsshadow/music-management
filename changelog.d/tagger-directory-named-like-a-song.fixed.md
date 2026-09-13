- **Een map met `.mp3` in de naam werd elke tagronde als nummer geparsed, en faalde elke keer.**
  `parse_folder` zocht bestanden met `Path.glob`, en die matcht op naam — dus
  `/mnt/music/EPs/This is Terror/TITCD018 - Srb - Rocket Science (2015).mp3`, een map, kwam
  binnen als kandidaat. `stat()` en `needs_processing` slagen allebei op een map, dus het liep
  pas stuk in mutagen, als `IsADirectoryError: [Errno 21]`. Dat is vijf `Parse_song failed` per
  nacht op productie (2026-09-10) die nooit minder konden worden: geen enkele volgende ronde
  maakt een map leesbaar als audio. De glob levert nu alleen echte bestanden op.

<!-- release notes -->

- **Mappen met `.mp3` in de naam worden niet langer als nummer ingelezen.** Ze leverden elke
  tagronde dezelfde foutmelding op.
