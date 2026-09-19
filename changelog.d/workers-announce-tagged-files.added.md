- **Een download of import is meteen zichtbaar: de worker die het bestand tagt meldt het
  ook.** De SoundCloud-, YouTube- en importer-workers tagden hun bestanden al zelf, maar
  schreven niets in de administratie van de tagger, dus de eerstvolgende mapwalk in
  music-manager tagde elk nieuw bestand nog een keer; LMS hoorde ervan bij zijn eigen
  geplande scan en de muma-scanner op zijn uurronde. Telegram-downloads werden helemaal
  niet getagd tot de walk `Telegram/` bereikte, ná EPs, Soundcloud en Youtube. Na de
  tag-pass doet elke worker nu `announce`: de rij in `tagger_processed_files` met de mtime
  van ná het schrijven, een LMS-scan van de map, en `POST /api/scanner/scan/file` voor de
  bibliotheektabellen. Daarvoor krijgen de workers via het nieuwe `environment-lms`-anker
  in `docker/docker-compose.yml` de LMS-host en -sleutel mee die music-manager al had.
  Elke stap is best effort: een gelukte download faalt nooit op een trage server.
  `POST /api/scanner/scan/file` en `POST /api/tagger/tag/file` draaien nu in de threadpool
  in plaats van op de event loop, want ze blokkeren.

<!-- release notes -->

- **Een download of import staat direct in de app.** De worker die het bestand tagt meldt
  het zelf bij LMS en de scanner; Telegram-downloads worden nu ook getagd.
