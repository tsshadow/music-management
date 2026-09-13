- **MuMa Voice in de webspeler.** De microfoon werkt nu ook op het Svelte-scherm, niet alleen in de
  Kotlin-app: een microfoonknop op het zoektabblad (alleen zichtbaar als het toestel spraakherkenning
  heeft), en de tegel/snelkoppeling/auto-modus openen dezelfde nieuwe pagina in plaats van het
  startscherm. Wat je zei en hoe MuMa dat begreep staat op het scherm; bij een dubbelzinnige naam
  komt de vraag met tikbare keuzes ("bedoel je het album of de afspeellijst?") en luistert de
  microfoon meteen weer mee voor een gesproken antwoord. Een duidelijke opdracht speelt meteen af,
  via dezelfde `getSongs`/`getAlbum`/`getPlaylist`-aanroepen en wachtrij als een preset of een
  Home-tegel. "Wat verstaat MuMa" en een inklapbare diagnoseleist met de laatste verzoeken zitten
  er ook op. De spraakherkenning en de audio blijven native — alleen het scherm eromheen is nu web;
  het woordbegrip (`core/voice`, de genre-, artiest- en labelherkenning) is ongewijzigd Kotlin en
  draait via de nieuwe `MumaSpeech.interpret`-bridge.

<!-- release notes -->

- MuMa Voice werkt nu ook in de nieuwe interface: een microfoon op het zoektabblad, en dezelfde
  vraag-en-antwoord-flow als op de telefoon als een naam dubbelzinnig is.
