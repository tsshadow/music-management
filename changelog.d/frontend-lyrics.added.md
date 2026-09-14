- **De speler kende geen songtekst.** De legacy `LyricsFragment` haalde die op via
  `getLyrics(artist, title)`, maar de webspeler had nergens een knop. LMS beantwoordt songtekst
  wel echt — `handleGetLyricsBySongId` in `MediaRetrieval.cpp` leest `db::TrackLyrics`, gevuld door
  de scanner uit ingesloten tags en bijpassende `.lrc`-bestanden — en `TrackList.svelte` toonde
  hem al voor een rij in de bureaubladlijst. `Player.svelte` haalt de songtekst nu op voor wat er
  speelt (per track-id, niet de fuzzy artiest/titel-match die `LyricsFragment` deed) en toont een
  knop zodra er tekst is: een bottom sheet in het "Nu speelt"-scherm op de telefoon, een klein
  paneel naast de wachtrijknop op het bureaublad. Zonder songtekst voor het spelende nummer
  verschijnt er niets — geen "geen songtekst"-plek die voor de meeste nummers leeg blijft staan.

<!-- release notes -->

- De speler toont nu songtekst wanneer LMS die heeft: een knop naast de wachtrij op het
  bureaublad, een bottom sheet in "Nu speelt" op de telefoon.
