- **Alle taggerinput onder Beheer › Curatie, elk op een eigen pagina.** Naast Genres, Artiesten
  en Podcasts nu ook **Labels** (elk label met nummers, catalogus-id's, genreregels en
  moederlabel; Bewerken opent de labelpagina), **Festivals** (naam, spellingen, editiedatums en
  actief — de drie tabellen die `FestivalHelper` leest en die tot nu alleen via SQL te vullen
  waren, met een "test een tekst"-vak dat de echte matcher over een titel laat lopen vóór je
  opslaat) en **Lineups** (de tekstbestanden onder `metadata/festival-lineups`: plak een line-up,
  "Controleren" zegt welke namen de bieb matcht en biedt de dichtstbijzijnde spelling voor de
  rest, opslaan schrijft de bieb-spelling). Nieuwe endpoints: `/api/rules/festivals` (+ `/probe`),
  `/api/rules/lineups` (+ `/match`), `GET /api/curation/labels`. Volgorde van de groep: Tagger,
  Genres, Artiesten, Labels, Labelvoorstellen, Podcasts, Festivals, Lineups.

<!-- release notes -->

- Beheer › Curatie heeft nu een pagina per soort taggerinput: Labels, Festivals (met
  spellingen en editiedatums) en Lineups (plakken, controleren, opslaan) zijn erbij.
