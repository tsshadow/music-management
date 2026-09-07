- **Een download hield "Lil Texas & Albino" nergens vast.** `CleanTagsRule` bewaart de
  artiestenregel zoals hij op het bestand stond, maar alleen als hij hem zelf nog moest splitsen.
  Bij een SoundCloud- of YouTube-download komen de artiesten uit de titel:
  `InferArtistFromTitleRule` draait ervóór en levert de ARTIST-tag al gesplitst aan, dus de
  "is er iets veranderd"-test van `CleanTagsRule` sloeg nooit aan en de weergavenaam ging verloren.
  8 van de 344.757 tracks op productie hadden er een.
- De credit wordt nu in twee stappen vastgelegd, en dat is het lastige deel. `InferArtistFromTitleRule`
  *onthoudt* alleen het ruwe segment, en alleen als dat segment precies uiteenvalt in de namen die
  eruit gekomen zijn — de tekst waar een naam uit gelezen is, is namelijk niet vanzelf een credit:
  `set_cleaned_artist` gooit "(live)" en losse achtervoegsels weg, en de fuzzy-takken houden alleen de
  kandidaten over die op een bekende artiest matchten. `Angerfist (live)` of een naam die de
  bibliotheek juist wegliet als credit wegschrijven is erger dan geen credit, want de webspeler toont
  `display_artist` in plaats van de artiestenlijst. De nieuwe `CaptureDisplayArtistRule` draait als
  laatste van de artiestenregels en schrijft de credit alleen weg als die de artiesten nog benoemt
  waar het bestand uiteindelijk mee eindigt — zo levert
  `Angerfist & Miss K8 - Track (feat. Albino)` géén credit op in plaats van eentje die twee van de
  drie artiesten noemt. Een waarde die al op het bestand stond wordt nooit overschreven.

<!-- release notes -->

- **Nummers van SoundCloud en YouTube tonen weer de artiestenregel zoals die geschreven stond.**
  "Lil Texas & Albino" werd overal uit elkaar getrokken tot twee losse namen en de oorspronkelijke
  schrijfwijze was nergens meer te zien.
