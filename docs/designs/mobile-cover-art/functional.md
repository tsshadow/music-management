# Cover art voor playlists in de app en de auto — Functional Design

## Overview

De web UI toont een collectie als beeld: elke playlist, elk album en elke artiest heeft een cover,
en de gebruiker herkent de rij aan het plaatje voordat hij de tekst leest. De Android app en Android
Auto tonen dezelfde collectie als tekstregels met een generiek icoon. In de auto is dat het duurst:
een lijst met vijftien regels tekst kost meer blikken dan een raster met vier tegels.

Deze feature geeft elke bladerbare ingang een cover. Waar geen bestaande afbeelding is — een genre,
een festival, een stage — genereert de app er zelf een uit de naam. Zo bedient één beeldsysteem web,
telefoon en auto, en is de kleur van Hardstyle overal dezelfde.

De feature valt uiteen in vijf stappen die los uitgeleverd worden. Stap 1, 2 en 3 zijn geleverd;
stap 4 (de telefoon-strips) en stap 5 (echte festivalbeelden) staan nog open.

## User Stories

- Als luisteraar wil ik in de auto mijn genres als tegels met beeld zien, zodat ik met één blik kies
  in plaats van een lijst te lezen.
- Als luisteraar wil ik een festival herkennen aan zijn eigen kleur en naam, zodat Defqon.1 Red en
  Defqon.1 Blue niet twee bijna gelijke tekstregels zijn.
- Als luisteraar wil ik een DJ herkennen aan zijn portret, zodat ik in een lange artiestenlijst
  sneller de juiste vind.
- Als luisteraar wil ik dat een playlist zonder eigen cover er nog steeds uitziet als iets, in
  plaats van als het lege notenbalk-icoon.
- Als bestuurder wil ik dat tracks een lijst blijven, zodat ik veertig titels niet als raster hoef
  af te zoeken.

## Functional Flows

| Situatie | Waarneembaar resultaat |
|---|---|
| Gebruiker opent in de auto een niveau waarvan de ingangen cover art hebben (albums, artiesten) | Android Auto tekent een raster met beeld in plaats van een tekstlijst |
| Gebruiker opent in de auto een niveau waarvan de ingangen geen cover art hebben (de A–Z-index van artiesten) | Het niveau blijft een lijst; er komen geen lege tegels |
| Gebruiker opent in de auto het hoofdmenu | Blijft een lijst: die ingangen dragen een menu-icoon, geen cover art |
| Gebruiker opent een tracklijst of een set | Blijft een lijst, ook als elke track een cover heeft |
| Een albumpagina bevat een "Meer"-ingang zonder eigen beeld | De pagina blijft een raster; die ene ingang trekt hem niet terug naar een lijst |
| Gebruiker opent een genre-niveau in de auto | Elk genre draagt een cover die de app zelf tekent uit naam en kleur; het niveau wordt daardoor een raster |
| Een artiest heeft geen portret | De cover valt terug op initialen op de kleur van diens genre; de artiestenlijst blijft daardoor een raster |
| Een artiest heeft wél een portret | Het portret wint; er wordt niets overheen getekend |
| MuMa is onbereikbaar terwijl de auto bladert | De covers houden de kleuren die het laatst opgehaald zijn; is er nog niets opgehaald, dan de neutrale kleur |
| Een genre dat MuMa niet kent (nieuw in een tag) | Neutrale kleur, geen lege tegel |

## Acceptance Criteria

1. In Android Auto verschijnt de albumlijst als raster met cover art, niet als tekstlijst.
2. In Android Auto verschijnt de artiestenlijst als raster zodra de artiesten een afbeelding hebben.
3. De A–Z-index waar de artiestenlijst boven 100 artiesten op terugvalt, blijft een lijst.
4. Het hoofdmenu in de auto blijft een lijst.
5. Tracks en sets blijven een lijst, ongeacht hun cover.
6. Geen enkel niveau in de auto laat de indeling over aan de standaard van de auto; elk niveau zegt
   zelf wat het wil zijn.
7. Dezelfde genrenaam levert op web en in de app dezelfde kleur op.
8. Een genre in de web UI draagt de kleur die MuMa stuurt; een genre dat MuMa niet kent houdt de
   brand-kleur die de kaart altijd al had.

## Open Questions / Not Yet Decided

- Voor welke festivals bestaat werkelijk bruikbaar beeldmateriaal, en mag dat gebruikt worden? Zolang
  dat niet vaststaat is de gegenereerde cover het eindproduct, niet een tussenstap.
- Krijgen playlists en tegels ook een getekende cover? Op dit moment niet: er is geen
  cover-familie voor "een playlist" en er een verzinnen zou het raster vullen met tegels die niets
  zeggen. Hun niveau blijft een lijst.
- Of het hoofdmenu in de auto een categorie-raster met eigen iconen moet worden. Dat vereist iconen
  die als tegel leesbaar zijn; de huidige monochrome vectoren zijn dat niet.

## Related Docs

- [`mockup.html`](mockup.html) — de drie cover-families en de schermen, in browserbare vorm
- [`technical.md`](technical.md)
