- **Het genre dat bij een label hoort werd nooit op een labelrelease gezet.**
  `InferGenreFromLabelRule` bestond, had een eigen test en stond in de regellijst van geen enkel
  songtype. `rules_label_genre` werd daardoor alleen gelezen via `InferGenreFromAlbumArtistRule`, dat
  dezelfde tabel raadpleegt op de naam van een YouTube-kanaal — nooit op de publisher. Een echte
  release in de EPs-boom kwam er dus zonder genre uit zodra de artiesten zelf geen genreregel hadden,
  en dat las als een niet-gecureerde release in plaats van als een regel die nergens draait. De regel
  zit nu in `LabelSong`, vóór de subgenreregel zodat een labelgenre ook nog verbreed wordt.
- **De ketentest liep om de labelmap heen.** In `docker/compose.test.yml` stonden
  `eps_folder_path` en `import_folder_path` allebei op `/mnt/music`, dus elk bestand op het volume
  zag eruit als een labelrelease en de drielaagse mappenstructuur waar de tagger publisher en
  catalogusnummer uit leest werd nooit doorlopen. Nieuw:
  `tests/bdd/features/label_import.feature` loopt een scene-release door label, artiesten,
  weergavenaam en beide genres heen, en `services/tagger/Song/LabelSongTest.py` doet hetzelfde per
  veld inclusief de releasedatum uit de NFO.
- De tagger slaat een ontbrekende EPs-map nu over in plaats van eruit te vliegen. Die uitzondering
  nam de achtergrondlus mee, en `/health` meldde de hele dienst degraded om een map die een minuut
  later weer terug was.

<!-- release notes -->

- **Een release op een label met één stijl kreeg geen genre meer mee.** De regel die het genre van
  het label overneemt stond wel klaar, maar werd voor labelreleases nooit gedraaid. Dat is hersteld.
