- **Home en de overzichten toonden op een telefoon twee kaarten per rij, halve schermbreedte
  groot, zodat één sectie al de hele hoogte innam en de pagina eindeloos doorscrolde.** Onder
  Tailwinds `md`-grens (en waar dat niet volstond, achter de `isMobile`-store) zijn Home-secties nu
  een horizontaal scrollende rij van vaste kaarten van 140 px — zoals Spotify's eigen "Daily Mix"-
  rijen — in plaats van een raster van twee kolommen. Genres, labels, podcasts, festivals, jaren en
  lineups (allemaal via `CollectionGrid`) en de albums-, artiesten- en zoekresultatenrasters gaan
  naar drie kolommen met kleinere tegels. Playlists krijgen op de telefoon een lijst met een 56 px
  miniatuur per rij in plaats van een tegelraster — dat is wat Spotify's eigen Bibliotheek-tab ook
  doet, terwijl de genre-/labeltegels een raster blijven omdat Spotify die ook zo toont. Een
  ontbrekende cover (het MuMa-merkteken) staat nu klein, gedempt en ingekaderd in plaats van
  levensgroot en wit uitgelicht. Desktop (vanaf `md`) is in geen van deze schermen aangeraakt.

<!-- release notes -->

- **De app is dichter bevolkt op een telefoon.** Home scrollt nu horizontaal per rij in plaats van
  verticaal per twee kaarten, overzichten tonen meer per scherm, en een ontbrekende cover valt niet
  langer op als een groot wit vlak.
