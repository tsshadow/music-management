- **Een download hield "Lil Texas & Albino" nergens vast.** `CleanTagsRule` bewaart de
  artiestenregel zoals hij op het bestand stond, maar alleen als hij hem zelf nog moest splitsen.
  Bij een SoundCloud- of YouTube-download komen de artiesten uit de titel:
  `InferArtistFromTitleRule` draait ervóór en levert de ARTIST-tag al gesplitst aan, dus de
  "is er iets veranderd"-test van `CleanTagsRule` sloeg nooit aan en de weergavenaam ging verloren.
  8 van de 344.757 tracks op productie hadden er een. Het ruwe segment waar de namen uit gelezen
  zijn wordt nu vastgelegd als `ORIGINAL_ARTIST` — niet bij één artiest, want dan gooide de
  splitsing niets weg, en nooit over een waarde heen die er al staat, want een hertag leidt de
  namen opnieuw af uit dezelfde titel.

<!-- release notes -->

- **Nummers van SoundCloud en YouTube tonen weer de artiestenregel zoals die geschreven stond.**
  "Lil Texas & Albino" werd overal uit elkaar getrokken tot twee losse namen en de oorspronkelijke
  schrijfwijze was nergens meer te zien.
