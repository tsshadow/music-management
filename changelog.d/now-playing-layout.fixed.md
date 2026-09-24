- **Een tik op een genre of label in de speler kwam nergens uit.** De speler sloot met
  `history.back()`, maar die komt pas later aan; de navigatie ging eerst, en de late `popstate`
  zette daarna de pagina onder de speler terug. `closeNowPlaying()` geeft nu een promise die pas
  na die `popstate` afloopt, en de speler navigeert daarna. Geldt ook voor album, artiest en de
  rijen onder "Hierna".
- **Bij veel informatie verdween de bediening van de speler onder de navigatiebalk.** Het
  schermvullende scherm is nu één schermhoogte: alleen de hoes krimpt mee, titel, artiesten,
  albumregel, genres, sterren, voortgang en knoppen staan altijd in beeld. Genres en labels staan
  op één rij die zijwaarts scrollt, de datum staat rechts naast het album, meerdere artiesten
  blijven op één regel. Liggend (tablet, gedraaide telefoon) staan hoes en bediening naast elkaar;
  voorheen was de hoes op een liggende tablet hoger dan het scherm en zag je geen enkele knop.
- **Artiesten stonden zonder spatie achter de komma ("Catscan,Starving Insect").** Svelte haalde
  de spatie weg uit `, ` binnen een `{#if}`. Overal waar `ArtistList` artiesten toont.
- **De nummerlijst op een tablet schoof titel, artiest en album over elkaar.** De kolommen gingen
  aan op de breedte van het scherm, terwijl de zijbalk daar een kwart van inneemt: bij ~500px
  tabel bleef er ~65px over voor de titel. Kolommen verschijnen nu op de breedte van de tabel
  zelf, cellen kappen af in plaats van over elkaar heen te lopen, de datum breekt niet meer af en
  aanraakschermen hebben geen lege beoordelingskolom meer. De status- en navigatiebalk van een
  tablet liggen niet meer over het logo en de spelerbalk.

<!-- release notes -->

- **Speler:** de bediening blijft altijd in beeld, genres op één scrollbare rij, datum rechts,
  en een tik op een genre of label opent die pagina weer. Liggend staan hoes en bediening naast
  elkaar.
- **Tablet:** de nummerlijst loopt niet meer over elkaar heen, en de systeembalken bedekken het
  logo en de spelerbalk niet meer.
- Artiesten staan weer met een spatie na de komma.
