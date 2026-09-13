- **Android Auto had geen eigen tak voor sets.** De boomstructuur in de auto kende alleen Songs en
  Livesets, en Livesets kreeg nooit de Favorieten-map die Songs al had: een genre of afspeellijst
  die voor sets was opgeslagen, kwam in de auto nergens terug — `getFavoriteGenreItems()` had de
  lengte hard op "short" staan, en `getFavoritePlaylistItems()` mengde beide lengtes zonder filter.
  Er staat nu een nieuwe root **Sets** naast Songs en Livesets, altijd aanwezig ongeacht de
  sets-modus-instelling op de telefoon, met dezelfde vier onderdelen als Livesets (zoeken op genre,
  recent toegevoegd, recent uitgebracht, recent gespeelde genres) plus een eigen Favorieten-map voor
  genres en afspeellijsten die met lengte "long" zijn opgeslagen. Songs en Livesets zijn ongewijzigd:
  elke bestaande media-id in de auto blijft exact hetzelfde, en de twee feeds (dagmix, release radar)
  staan waar ze stonden.

<!-- release notes -->

- **Android Auto heeft nu ook een Sets-map**, naast Songs en Livesets, met genres, recent
  toegevoegd/uitgebracht en favoriete genres/afspeellijsten voor sets — precies wat Songs al had.
