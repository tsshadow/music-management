- **Een m4a zonder metadatablok liet de tagger bij elke ronde opnieuw stuklopen.** mutagen geeft
  `tags` als `None` terug wanneer het bestand helemaal geen atom heeft — een yt-dlp-fragment dat
  nooit samengevoegd werd (`... Identity Episode 108.f140.m4a`) is zo'n bestand — en
  `BaseSong._set_m4a_tag` schreef daar rechtstreeks in: `TypeError: 'NoneType' object does not
  support item assignment`. De wav-tak maakte dat blok al aan als het ontbrak; m4a doet dat nu ook.
  Omdat een bestand dat de parse niet haalt nooit als verwerkt wordt weggeschreven, kwam het via
  `new_in_library` elke ronde terug: 274 keer in het venster van één nacht, op één bestand.

<!-- release notes -->

- **Een m4a-bestand zonder tags liet de tagger elke ronde opnieuw struikelen.** Zo'n bestand krijgt
  nu gewoon een leeg tagblok en wordt normaal getagd.
