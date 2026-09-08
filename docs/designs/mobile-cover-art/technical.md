# Cover art voor playlists in de app en de auto — Technical Design

Implementeert [`functional.md`](functional.md).

## Data Model

Geen schemawijziging. De tint is afgeleid van de genrenaam en wordt niet opgeslagen: hem bewaren
zou een tweede waarheid opleveren die kan verlopen ten opzichte van de afleiding.

## API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/library/genres` | geen | rijen `{genre, state, count, tint}` | 401 zonder API-key; 500 als de database onbereikbaar is |

`tint` is nieuw en additief: een `#rrggbb`-string naast de bestaande velden. Bestaande consumers
negeren het veld; geen breaking change.

De kleur komt uit `services/music_manager/genre_tint.py`. De genres die deze collectie dragen staan
in een korte tabel — Hardstyle verdient het oranje van de festivals waar het vandaan komt, en dat is
geen hash-uitkomst. Alles daarbuiten wordt uit de naam afgeleid met blake2b (níet `hash()`: CPython
zout string-hashing per proces, dus dezelfde genre zou na elke herstart een andere kleur krijgen).
Verzadiging en helderheid liggen vast, zodat de genrenaam in bijna-zwart over de tint leesbaar
blijft, welke tint er ook uitkomt.

### Wie leest hem

- **Web UI** — `src/lib/genreTints.js` haalt de lijst één keer op en plakt de tint op de
  genre-items die van Subsonic's `getGenres` komen. `getGenres` kent geen kleur; deze join is de
  reden dat de web UI de kleur niet zelf hoeft te kennen.
- **App** — `MumaAPIDefinition.getLibraryGenres()`, gecachet door `GenreTintCache` (een uur). De
  media browser antwoordt op de deadline van de beller, dus een netwerkcall per bladerniveau zou
  een lijst laten wachten waar iemand naar kijkt. Een mislukte fetch behoudt wat er al was: de auto
  is precies de plek waar MuMa het minst bereikbaar is, en een leeg raster is erger dan een oud.

Geen van beide clients heeft een eigen tabel. Dat is het hele punt: Hardstyle oranje in het ene en
magenta in het andere is onzichtbaar tot beide naast elkaar openstaan, en van geen van beide kanten
te testen.

## Hoe Android Auto een niveau tekent

De auto beslist de indeling **per niveau, niet per item**. De hints reizen daarom op de
`LibraryParams` van het niveau, niet op de items:

| Extra | Waarde | Betekenis |
|---|---|---|
| `android.media.browse.CONTENT_STYLE_BROWSABLE_HINT` | `1` = lijst, `2` = raster | indeling van de bladerbare kinderen |
| `android.media.browse.CONTENT_STYLE_PLAYABLE_HINT` | `1` = lijst, `2` = raster | indeling van de afspeelbare kinderen |

De sleutels komen uit `androidx.media.utils.MediaConstants`. Die bibliotheek staat niet op het
classpath; de waarden liggen vast, dus ze zijn overgenomen als letterlijke constante — zoals
`BROWSER_SEARCH_SUPPORTED` er al stond.

**Zonder deze hints negeert de auto de artwork-URI van bladerbare items grotendeels.** Cover art
renderen zonder de hint te zetten levert dus geen zichtbaar verschil op. Dat is de reden dat stap 2
vóór stap 3 gaat.

## De regel

`contentStyleParams(items)` in
`services/muma-mobile/app/src/main/kotlin/nl/teunschriks/mumamobile/service/androidauto/ContentStyle.kt`
beslist over de hele lijst:

- **Bladerbaar wordt een raster** zodra minstens één bladerbaar kind cover art draagt.
- **Cover art is niet hetzelfde als een icoon.** Een URI met scheme `android.resource` is een
  vector uit de APK — het hoofdmenu draagt die — en telt niet mee. Als tegel is dat een klein glyph
  op een leeg vlak, en de naam die de ingangen onderscheidt krijgt minder ruimte dan in de lijst.
- **Eén cover is genoeg.** Een albumpagina voorbij de eerste voegt een bladerbare "Meer"-ingang
  zonder eigen beeld toe. Die ene ingang mag de pagina niet terugtrekken naar een lijst, juist waar
  de collectie het grootst is.
- **Afspeelbaar blijft altijd een lijst.** Een raster van veertig tracks kost de bestuurder meer
  blikken dan veertig regels.

De regel leest de items zelf, dus niveaus die in stap 3 cover art krijgen — genres, festivals —
worden vanzelf een raster zonder dat er een lijst met media-ids onderhouden hoeft te worden.

## Waar het is aangesloten

Stap 4 zit in `HomeCardAdapter`: `HomeCardArt.kindFor(card)` beslist of een kaart een getekende
cover krijgt, en dezelfde drie families gelden als in de auto. Een kaart waar de server wél een
plaat voor heeft houdt die plaat, en een soort zonder cover-familie (label, jaar, playlist) houdt
zijn icoon. De kleur komt uit `AppGenreTints.cache`, één cache voor de hele app: twee caches
zouden een venster geven waarin de auto en de telefoon het oneens zijn over Hardstyle.

- `MediaLibraryBase.itemListResult(items)` bouwt het antwoord mét params. Alle 27 plekken in
  `MediaLibraryBrowser` die `LibraryResult.ofItemList(..., null)` teruggaven, gaan er nu doorheen,
  net als `emptyResult`. Een niveau kan het dus niet meer vergeten.
- `searchableRootParams` zet lijst/lijst als globale terugval, naast de bestaande zoekclaim. Dat is
  wat de auto gebruikt voor alles wat niet via `itemListResult` loopt.

## Cross-App Impact

Stap 2: geen. Alleen `services/muma-mobile`.

Stap 1 en 3 raken `music-management-server` (tint naast de genrenaam) en `frontend` (dezelfde tint
gebruiken in plaats van een eigen tabel) tegelijk met de app.

## Technical Acceptance Criteria

1. `contentStyleParams` geeft `CONTENT_STYLE_GRID_ITEM` als een bladerbaar item een `content://`-URI
   als artwork heeft.
2. `contentStyleParams` geeft `CONTENT_STYLE_LIST_ITEM` als geen enkel bladerbaar item artwork heeft.
3. `contentStyleParams` geeft `CONTENT_STYLE_LIST_ITEM` als het enige artwork een
   `android.resource://`-URI is.
4. Eén item met artwork tussen bladerbare items zonder artwork levert `CONTENT_STYLE_GRID_ITEM`.
5. De hint voor afspeelbare items is altijd `CONTENT_STYLE_LIST_ITEM`, ook als die items artwork
   dragen.
6. Artwork op een afspeelbaar item verandert de bladerbare hint niet.
7. Een leeg niveau levert `CONTENT_STYLE_LIST_ITEM`.
8. `browser.getChildren(...)` voor het hoofdmenu geeft een resultaat met niet-lege `params`, met
   `CONTENT_STYLE_LIST_ITEM` als bladerbare hint.
9. `searchableRootParams` zet beide hints op `CONTENT_STYLE_LIST_ITEM` en behoudt
   `BROWSER_SEARCH_SUPPORTED`.

Gedekt door `ContentStyleTest` en `SearchableRootParamsTest` in
`services/muma-mobile/app/src/test/kotlin/nl/teunschriks/mumamobile/service/androidauto/`.

## Nog te bouwen

| Stap | Wat | Status |
|---|---|---|
| 1 | Tint per genre vanaf de server; renderer die een cover tekent uit naam, soort en tint | **Geleverd** |
| 2 | Content-style hints | **Geleverd** |
| 3 | Artwork-URI bij bladerbare items in `MediaLibraryBrowser` | **Geleverd** voor genres en artiesten |
| 4 | Home-strips op de telefoon cover-first maken, zoals de web UI | **Geleverd** voor genres, festivals en artiesten |
| 5 | Echte festivalbeelden koppelen waar die er zijn en gebruikt mogen worden | Open |

Wat stap 3 bewust niet raakt: **playlists en tegels**. Die zijn bladerbaar en hebben geen beeld, dus
hun niveau blijft een lijst. Een vierde cover-familie voor "een playlist" bestaat niet in het
ontwerp, en er een verzinnen om het raster te vullen zou de lijst vervangen door tegels zonder
betekenis. De festival-familie is wél gebouwd en getest, maar er is nog geen bladerniveau in de auto
dat festivals toont — die komt met stap 5.

## Related Docs

- [`functional.md`](functional.md)
- [`mockup.html`](mockup.html)
