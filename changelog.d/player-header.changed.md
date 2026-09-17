- **De koptekst van de telefoonspeler stond in hoofdletters (`AFSPELEN UIT: NAAM`), genres en
  label waren platte tekst die na één regel afkapte, en "meer info" zat achter twee knoppen: een
  `(i)` onderaan en een aparte lyrics-knop bovenaan.** De koptekst is nu twee regels — een klein
  "Afspelen vanuit" boven de vetgedrukte naam — en blijft een knop naar het album. Rechtsboven
  staat één ⋮-knop die het bestaande `TrackDetailsSheet` opent (artiest, album, hierna afspelen,
  wachtrij, songtekst als die er is, details); de `(i)`-knop is weg. Genres en label zijn dezelfde
  tikbare pillen als in de sheet (nieuw gedeeld `MetaChips.svelte`) en wikkelen door in plaats van
  af te kappen; de releasedatum stond al in de sheet en verdwijnt uit deze rij. De artiestenregel
  (`ArtistList` `size="lg"`) is 44px hoog met een chevron, de sterren zijn 44×44px tikdoelen met een
  24px ster, en shuffle, herhalen en de onderste rij iconen staan allemaal op 24px.

<!-- release notes -->

- De speler op de telefoon heeft een opgeruimde koptekst zonder hoofdletters, genres en label als
  tikbare pilletjes die niet meer afkappen, één ⋮-menu voor artiest/album/wachtrij/songtekst/
  details, en grotere sterren en iconen.
