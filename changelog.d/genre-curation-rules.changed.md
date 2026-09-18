- **Genre Curatie is nu de plek voor alles rond genres; het Genre Overzicht van de taggerpagina is
  weg.** De pagina onder Curatie › Genres heeft vier onderdelen: de **wachtrij** (met het advies
  van hierboven), **Genres** (elk goedgekeurd genre met aantal nummers, hardheid, waar het onder
  valt en hoeveel artiest- en labelregels erop wijzen; Bewerken opent de genrepagina), en twee
  regelpanelen **Artiest → genre** en **Label → genre**: zoeken op naam óf genre, sorteren op
  bereik, toevoegen met een naam uit de bibliotheek en een goedgekeurd genre (een dubbele regel
  wordt geweigerd vóór de knop), verwijderen, en per rij wie de regel maakte en hoeveel nummers
  hij raakt; een regel voor een naam die niet meer in de bibliotheek staat krijgt een label. De
  taggerpagina houdt alleen nog wat van de tagger is — rescan en retag — en wijst naar Genres.
  Het oude "Genre Overzicht" toonde de hele `rules_genres`-tabel, afgekeurde en nog te beoordelen
  genres incluis, en de koppelkeuzelijst bood die ook aan. `GET /api/rules/artist-genres` en
  `label-genres` geven per regel nu ook `artist_id`/`label_id`, `track_count`, `created_at` en
  `created_by`; `GET /api/curation/genres` is nieuw en levert het overzicht.
