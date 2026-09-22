- **45.066 artiesten hielden een oordeel dat een blinde fetcher had geveld.** `migrate_v30` was
  precies daarvoor geschreven en draaide ook, maar deed niets: zijn voorwaarde was er één voor de
  hele tabel — "reset alles, tenzij er sinds de blackout een provider-foto binnen is" — en tegen
  de tijd dat die migratie voor het eerst op productie kwam, stonden er al 22 met de hand
  opgehaalde Spotify-portretten in. Daarmee was de voorwaarde voor alle overige 45.044 artiesten
  permanent onwaar. `migrate_v32` stelt de vraag per artiest: is *dit* oordeel geveld in het
  venster tussen de blackout en de eerste foto die een provider daarna leverde? Zo ja, terug naar
  "nooit gevraagd"; zo nee, het blijft staan. Zelfbeperkend en herhaalbaar, want deploy draait
  hem elke keer. De fetcher pakt deze artiesten daarna vanzelf op.

<!-- release notes -->

- **Artiestfoto's worden opnieuw opgehaald voor de 45.000 artiesten** die als "geen foto te
  vinden" waren weggeschreven door een fetcher die geen sleutels had.
