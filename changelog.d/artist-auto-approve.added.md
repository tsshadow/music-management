- **Artiesten goedkeuren op extern bewijs.** `tools/artist_auto_approve.py` slaat de
  artiestcuratie-wachtrij op, zoekt elke naam op bij Deezer, iTunes en MusicBrainz en keurt
  hem goed als een opname *op naam van die artiest* daar een titel draagt die de bibliotheek
  ook onder die naam heeft — twee titels bij één act, twee titels over bronnen heen, of één
  onderscheidende titel bij MusicBrainz én een winkel. Dat de naam bestaat telt niet (`Otis`,
  `Nero`, `Holly` bestaan overal als iemand). Nooit automatisch afkeuren: geen dekking is geen
  bewijs van rommel. Elke response wordt gecachet, dus stoppen en hervatten kost niets;
  `apply` tekent de rijen als `auto-external` en `undo` draait precies die terug.
  `POST /api/rules/artists/decide` accepteert daarvoor een `decided_by` bij de systeemsleutel.

<!-- release notes -->

- **Artiesten worden goedgekeurd op extern bewijs.** Een script vraagt Deezer, iTunes en
  MusicBrainz of de nummers van een naam daar op die naam staan; wat niet te bewijzen is
  blijft in de wachtrij.
