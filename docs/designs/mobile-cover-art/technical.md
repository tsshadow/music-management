# Cover art voor playlists in de app en de auto — Technical Design

Implementeert [`functional.md`](functional.md).

## Data Model

Geen schemawijziging voor stap 2. Stap 1 voegt een kleur toe naast de genrenaam in het
API-antwoord; die is afgeleid en wordt niet opgeslagen.

## API Contract

Stap 2 raakt geen enkele endpoint: het verkeer loopt tussen de app en Android Auto, over de
media3-sessie.

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| n.v.t. voor stap 2 | | | |

Voor stap 1 (nog niet gebouwd) is het voorstel om de tint mee te sturen op de bestaande
genre-endpoints, als extra veld naast de naam. Dat is additief en dus niet breaking.

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

| Stap | Wat | Waarom in deze volgorde |
|---|---|---|
| 1 | `GenrePalette` + een renderer die een cover tekent uit naam, type en tint; tint vanuit de server | Zonder gedeelde kleurbron lopen web en app uit elkaar |
| 2 | Content-style hints (**geleverd, 0.51.0**) | Zonder de hint is de gerenderde cover in de auto onzichtbaar |
| 3 | Artwork-URI meegeven bij bladerbare items in `MediaLibraryBrowser` | Vult het raster dat stap 2 opent |
| 4 | Home-strips op de telefoon cover-first maken, zoals de web UI | Meeste werk, profiteert van 1 t/m 3 |
| 5 | Echte festivalbeelden koppelen waar die er zijn en gebruikt mogen worden | Optioneel; de gegenereerde cover is al af |

## Related Docs

- [`functional.md`](functional.md)
- [`mockup.html`](mockup.html)
