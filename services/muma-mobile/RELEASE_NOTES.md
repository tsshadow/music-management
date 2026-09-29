## [Unreleased]

## Global Version 7.13.1 (2026-09-29)

- **Browse by BPM and the listening statistics filters (genre, release year) are now in the app.** Server 0.84.0 shipped them to the web player only; this build carries the same web interface.

## Global Version 7.13.0 (2026-09-29)

- **Android Auto: "Oude hitjes" in the "Daily mixes" folder.** The new server feed of old
  favourites you play less is listed last in the folder, after the classic daily mix, and plays
  like every other feed row. On the phone it appears on Home through the web UI.

## Global Version 7.12.2 (2026-09-29)

- **Test and lint tooling updated** (Renovate). No change in the app itself.

## Global Version 7.12.1 (2026-09-27)

- Android Auto's extra buttons now keep up with repeat and shuffle changes. The diagnostics report
  records more about what the car receives, to track down why the car still does not show them.

## Global Version 7.12.0 (2026-09-27)

- A label page shows the channels linked to that label.

- Channels can be linked to their label or artist by hand in Beheer, and their tracks then show
  that label.

## Global Version 7.11.1 (2026-09-27)

- Settings opens faster, and the app's interface starts a little faster again; Now Playing
  still opens instantly.

## Global Version 7.11.0 (2026-09-27)

- In the car, a genre, label, festival, year, preset or "Recent" list now keeps playing past the
  tracks that were shown, like the daily mixes already did; shuffled lists stay one shuffle.

- The app's interface starts a little faster again; artist and album pages still open instantly.

## Global Version 7.10.3 (2026-09-27)

- The app's interface starts faster: it reads less than half the code at start, and loads pages
  like settings and statistics when you open them.

- Your sign-in is now stored encrypted on the phone. After updating you stay signed in. If the
  phone's secure storage is ever reset, the app asks you to sign in again.

## Global Version 7.10.2 (2026-09-27)

- The app no longer stores your password. After updating you stay signed in. If your account's key
  is ever revoked, the app asks you to sign in again, and the car says to sign in on your phone.

## Global Version 7.10.1 (2026-09-27)

- Genres, labels, festivals and other lists no longer flash the previous list when you open them.
- Search shows "Searching…" instead of "No results" while it waits.

- Daily mixes, the release radar and a song's other versions now open straight away.

- Daily-mix cards now show their play button on the phone and tablet.

## Global Version 7.10.0 (2026-09-27)

- No more black screen while the app starts: it now tells you it is connecting, signing in or
  restoring your queue.
- Artists and albums open instantly; their tracks load in while you look.

- The app no longer sends your password with any request to the music server, not even right after
  an update. If it cannot fetch its sign-in token, the app and the car say "sign in again" or
  "server not reachable" instead of showing empty lists.

## Global Version 7.9.0 (2026-09-27)

- A queue started from any long list, such as "Recent uitgebracht", keeps going past the first page,
  and the queue ends in "Meer laden" or "Einde van de lijst".

- A daily mix started by tapping one of its tracks keeps going past 100 tracks, and the queue has
  a "Meer laden" button.

- Logging out now asks for confirmation first, and tells you your downloads stay on the phone.

## Global Version 7.8.1 (2026-09-27)

- No app changes of its own: the release build is now started twice on the CI emulator and must show its server address on screen (issue #24), which touched the app's build scripts and README.

## Global Version 7.8.0 (2026-09-27)

- Settings changed in the app and in the web player at the same time no longer overwrite each
  other.

- Voice can play a podcast show by name: "speel de podcast van KTRA af" or "play the latest episode of Monstercat".

## Global Version 7.7.0 (2026-09-27)

- Android Auto and voice can ask for livesets, sets & mixes or podcasts, and a liveset is found under the year it was played.

## Global Version 7.6.3 (2026-09-26)

- Release Radar and the daily mixes in the car no longer stop after the first 100 tracks.

## Global Version 7.6.2 (2026-09-26)

- Release Radar and the daily mixes in the car now hold 100 tracks instead of 30.

## Global Version 7.6.1 (2026-09-26)

- **Android Auto picks up a replaced login token by itself.** Before, it kept failing with "wrong
  username or password" until the app was opened on the phone.

## Global Version 7.6.0 (2026-09-26)

- **Inloggen met Google kan weer in de app.** Op het inlogscherm staat onder het wachtwoordformulier
  een knop "Inloggen met Google"; je kiest je Google-account in het venster van Android zelf.

- **Uitloggen werkt weer.** Na "Uitloggen" stopt het afspelen en zie je het inlogscherm, ook als je
  de app daarna opnieuw opent. Je downloads blijven staan.

- **Je wachtwoord gaat niet meer mee in elk verzoek aan de muziekserver.** De app haalt na het
  inloggen een eigen token op en ondertekent elk nummer, elke hoes en elke lijst daarmee. Je merkt
  er niets van: inloggen, afspelen en Android Auto werken zoals altijd.
## Global Version 7.5.2 (2026-09-26)

- No app changes of its own: a code comment now points at GitLab issue #39 instead of docs/open-work.md. The version moves with server release 0.76.0 because the release check bumps the app whenever its directory changed.
## Global Version 7.5.1 (2026-09-26)

- **Tapping "next" twice quickly no longer makes the player flicker between two tracks.**

- **Songs no longer appear twice in the Release Radar, the daily mixes, favourites, search and the
  home shelves, and the feeds play the official version instead of a rip.**

- **Songs no longer appear twice, or disappear, when only the preferred version is shown.**
## Global Version 7.5.0 (2026-09-25)

- **The sets view has a Soort filter: sets & mixes, live sets or podcasts.** It comes with the web
  UI of the server release that classifies every track by form; picking a year now also finds live
  sets played in that year, when MuMa knows the festival edition.
## Global Version 7.4.8 (2026-09-25)

- On a tablet in landscape the search box and the profile button are back in the top bar.
## Global Version 7.4.7 (2026-09-25)

- **The app ships the web UI fixes of server 0.74.1.** A rating set in one place (a list, the
  player, car mode, track details) now shows everywhere at once and rolls back if the server
  refuses it; a double tap no longer starts the radio twice; saving a long queue no longer fails
  with "URI too long"; the player position is written to storage less often; and the remaining
  hard-coded Dutch texts now follow the app's language.
## Global Version 7.4.6 (2026-09-25)

- **Listens no longer go missing.** A track you played is remembered on the phone until the server
  has it, also when you were offline, in the car, or the app was closed in the middle of a set.

- **Signing in with your name in another case no longer splits your history.** The app now
  always uses your account's own spelling of the name.
## Global Version 7.4.5 (2026-09-25)

- **Now playing:** the label chip is amber, so it no longer reads as another genre.

- **Now playing:** the news of the hour button is back, next to the radio button.

- **Now playing:** the rating stars are centred under the chips, and an unrated track shows
  outlined stars instead of greyed-out ones.
## Global Version 7.4.4 (2026-09-24)

- **Android Auto:** another attempt at bringing the rating, shuffle, repeat and news buttons back
  to the car's player screen. If they are still missing, send a diagnostics report after the drive.

## Global Version 7.4.3 (2026-09-24)

- **Security fixes.** The app checks the server's certificate again, other apps can no longer read
  its stored password, and credentials are kept out of the diagnostics log and out of the APK.

- **Playback service fixes.** Music keeps playing when the app is swiped away, radio no longer runs
  on after the player stops and starts reliably on the phone, a Bluetooth play button is always
  answered, the saved queue stays current, and the app no longer logs in again for every settings
  save.
## Global Version 7.4.2 (2026-09-23)

- **Diagnostiekrapporten bevatten weer wat er gebeurde.** De downloadservice vulde het logboek met
  ruis, waardoor een autorit uit het rapport verdween; dat is opgelost, en de knoppen die de app
  aan de auto geeft staan er nu in.

- **Diagnostiekrapporten bevatten geen wachtwoord of API-key meer.**
## Global Version 7.4.1 (2026-09-21)

- **De statusbalk en de navigatiebalk waren grijs, en de app tekende er niet achter.** Sinds
  targetSdk 35 negeert Android `statusBarColor`/`navigationBarColor` en zijn de balken
  transparant; of de WebView erachter zit, beslist Capacitor's `SystemBars`-plugin -- en die
  doet dat alleen als de pagina `viewport-fit=cover` in zijn viewport-meta heeft. Zonder dat
  kreeg de WebView een marge ter grootte van de balken en toonden de balken de eigen achtergrond
  van de WebView, een grijs (#303030) dat nergens in de app gekozen is. De webpagina draagt nu
  die meta en vult zelf de `env(safe-area-inset-*)`: de zoekbalk bovenaan (sticky, met dezelfde
  doorschijnende grond als Spotify), de onderste navigatie, Now Playing, het lade-menu, de
  wizard en de meldingen. `backgroundColor` in `capacitor.config.json` is de kleur van het
  eerste frame en van de marge op een oudere WebView (< 140), en `SystemBars.style: DARK` houdt
  de balk-iconen licht, ook op een telefoon met een licht thema.
## Global Version 7.4.0 (2026-09-20)

- **De ster, shuffle, herhaal en nieuws staan weer op het rijscherm van Android Auto.** Android
  Auto 17.6 tekent alleen knoppen met een standaard-icoon; de app geeft die nu mee. In de auto is de
  ster leeg, gevuld of een hart (vijf sterren); het cijfer blijft op de telefoon.

- **De debug-app heeft nu een grijs icoon met een D**, zodat je op de telefoon en in de auto ziet
  welke van de twee je opent.

- **"Speel flac hardstyle af" werkt.** Ook "in hoge kwaliteit" voor 320 kbps of beter, in de
  auto en in MuMa Voice.
## Global Version 7.3.2 (2026-09-19)

- **Android Auto bladert nu net als de telefoon.** Vier tabs (Start, Nummers, Sets,
  Bibliotheek), met labels, podcasts, festivals, jaren en lineups; elke tag opent direct op zijn
  nummers met Alles afspelen, Willekeurig en Per jaar erboven. Een preset rond een label of
  festival speelt in de auto nu ook echt dat label of festival.

- **Een nummer aantikken in de auto speelt de lijst vanaf dat nummer**, in plaats van alleen
  dat nummer.

- Een debug-installatie meldt nu ook wanneer een nieuwere release beschikbaar is.
## Global Version 7.3.1 (2026-09-19)

- Onderhoudsrelease: bijgewerkte bouwtools, geen zichtbare wijziging.
## Global Version 7.3.0 (2026-09-17)

- De speler laat zien via welke uitvoer je luistert; tikken opent de uitvoerkiezer van Android.
## Global Version 7.2.1 (2026-09-16)

- **Een andere taal kiezen werkt weer** — het scherm komt in de gekozen taal terug.
## Global Version 7.2.0 (2026-09-16)

- De auto toont nu vijf dagelijkse mixen (zacht/midden/hard, plus de artiest en het label van de
  dag) in een map "Dagelijkse mixen", in plaats van één mix op de rootmap.
## Global Version 7.1.0 (2026-09-16)

- Release radar and daily mix load on the phone again.

- The player shows genre, release date and label again, with a details sheet and a Song button.

- Compact coloured Home tiles, Songs/Sets switch in the top bar, denser phone layout.
## Global Version 7.0.0 (2026-09-15)

- **Android Auto leest de snelkoppelingen nu van de server.** De map "Afspeellijsten" (en
  dezelfde map onder Favorieten en onder Sets) toonde de tegels uit een lokale opslag die alleen
  de oude Kotlin-schermen vulden; sinds die weg zijn kwam er niets meer bij. De auto vraagt nu de
  dynamische afspeellijsten van de gebruiker rechtstreeks aan MuMa — dezelfde lijst die het
  startscherm van de webspeler als tegels toont — dus een snelkoppeling die je op de web opslaat
  staat bij de volgende keer bladeren in de auto. Vijf minuten gecachet; als de server niet
  antwoordt valt de map weg en blijft de rest van de boom staan.

- **Het rijscherm loopt weer mee** met het nummer dat speelt, ook met shuffle aan.

- **De klassieke interface is weg.** De app opent altijd in de nieuwe speler; de knop "Terug naar
  de klassieke interface" en het oude instellingenscherm bestaan niet meer. Afspelen, downloads,
  Android Auto, automodus en stem werken zoals voorheen.

- **Updatemelding is terug**, plus "Controleren op updates" en een Over-pagina met alle
  versies (app, server, webinterface).

- **Geen zwart scherm meer** als je de app na een tijdje weer opent.
## Global Version 6.36.0 (2026-09-14)

- **`MumaSystem` kreeg vier methodes erbij voor de webspeler's instellingen-tab.**
  `listBondedDevices()` geeft de gekoppelde bluetooth-apparaten met wie een auto is; het schrijven
  van `carModeDevices` via `setSetting` gaat voor het eerst via een echte set in plaats van een
  aantal. `requestCarModeFullScreenPermission()` en `pickCacheLocation()`/
  `clearCustomCacheLocation()` doen wat de klassieke rijen voor volledig-scherm-toestemming en
  cachelocatie altijd al deden, nu bereikbaar zonder het klassieke scherm te openen.
  `setAppLocale()` past de taal van de shell zelf aan (vergunningsschermen, deelvensters), niet
  alleen de tekst van de webinterface.

- **Android Auto heeft nu ook een Sets-map**, naast Songs en Livesets, met genres, recent
  toegevoegd/uitgebracht en favoriete genres/afspeellijsten voor sets — precies wat Songs al had.

- Bestaande bookmarks worden bij de eerste start van de nieuwe schil automatisch omgezet naar het
  nieuwe "hervat een set"-onthouden, zodat er niets verloren gaat.

- Je kunt de webspeler nu in de app proberen: Instellingen → Weergave → Nieuwe interface (bèta).
  De muziek blijft via dezelfde speler lopen, dus melding, bluetooth en Android Auto werken
  gewoon door. Standaard staat hij uit.

- **`MumaSystem` beantwoordt de nieuwe instellingen-tab van de webspeler.** `getSettings()` geeft
  een momentopname van de instellingen die de tab toont; `setSetting({key, value})` schrijft er één
  terug, tegen een vaste whitelist met een typecontrole — een onbekende sleutel of een verkeerd
  type wordt geweigerd in plaats van een instelling stilzwijgend niets te laten doen. `MumaStorage`
  kreeg er `clearCache()` bij: annuleert wachtende en actieve downloads en verwijdert daarna elk
  gecachet bestand dat niet is vastgezet.

- **`MumaDiagnostics` weet nu ook wélke interface een rapport schreef.** `identify({bundleVersion,
  userAgent})` legt vast dat de webinterface heeft gedraaid, met welke frontend-build en welke
  WebView; ontbreekt die aanroep, dan meldt een rapport gewoon "legacy" zoals voorheen.
  `CrashReportManager` zet die drie feiten voor in de metadata-kop, boven het bestaande
  actielogboek dat de webacties en -fouten al bevatte.

- **Een aantal instellingen uit het klassieke scherm is opgeruimd, nu de webtab alles dekt wat nog
  nodig was.** Stijl, app-icoon en interfaceschaal zijn geen keuze meer — Spotify-stijl is de enige
  stijl, schalen gaat via de tekstgrootte van het toestel. Delen en chat waren al dode code; hun
  instellingen zijn weg. Bladwijzers zijn al vervangen door het onthouden van de afspeelpositie in
  een set; vooruit/achteruit springen is voortaan altijd ±30 s. ID3-modus staat altijd aan. De
  zoeklimieten en een aantal weergaverijen zijn óf naar de webtab verhuisd, óf hadden al geen
  effect meer. De installatiewizard verloor de drie stappen die deze instellingen tijdens het
  eerste gebruik lieten kiezen. Niets hiervan was nog bereikbaar vanuit de nieuwe interface; het
  klassieke scherm zelf blijft intact tot dat in een latere stap verdwijnt.

- **"Ik zie eigenlijk alleen zwart wit": het beginscherm van de Kotlin-app had geen enkele
  merkkleur en de speler stond vol met Material-lila.** Gemeten op een API 34-emulator: van de
  2.527.200 beeldpunten op het beginscherm waren er nul groen, en het enige kleurvlak was een
  `#4a4458` paars dat in geen van beide stijlen voorkomt. Drie oorzaken, alle drie een kleur die
  niemand gekozen heeft. Beide stijlen overschrijven Material3's primaire en oppervlakteattributen
  maar lieten de secundaire reeks onaangeroerd, dus alles wat die aansprak kreeg het lila van de
  bibliotheek — en de navigatiebalk tekent de vorm achter het actieve tabblad juist met
  `colorSecondaryContainer`. De hoesvervanger sprak diezelfde reeks aan, dus een nummer zonder hoes
  werd een `#ccc2dc` vlak: op de speler 822.514 beeldpunten, bijna een derde van het scherm. En de
  notenglyph van een nummer zonder hoes was hard op `#000000` getint, wat 1,12:1 haalt op een
  venster dat in beide stijlen bijna zwart is — die stond er dus wel en was onzichtbaar. De
  secundaire reeks is nu in beide stijlen benoemd, de hoesvervanger tekent op
  `colorSurfaceVariant` met `colorInkTertiary` (3,92:1 in de MuMa-stijl, 7,03:1 in Spotify, boven
  de 3:1-ondergrens voor wat getekend en niet gelezen wordt), de notenglyph neemt
  `colorControlNormal` (8,8:1) en de vorm achter het actieve tabblad neemt de merkkleur van de
  modus op een vijfde — groen voor nummers, blauw voor sets, dezelfde sterkte waarmee een
  geselecteerde regel al getint wordt. Voor de volledigheid: de sets-schakelaar in de werkbalk
  werd groen op het ene moment dat de app juist blauw is, en leest nu ook de modus.

- De webspeler in de app weet nu welke versie er draait en kan de eigen release notes lezen, voor
  het "wat is er nieuw"-scherm na een update.

- Gedownloade playlists blijven nu ook zichtbaar zonder verbinding, inclusief playlists die al voor
  deze update waren gedownload.

- De nieuwe interface werkt nu ook zonder verbinding: alles wat je gedownload hebt staat gewoon in
  de lijsten, met dezelfde hoesjes en dezelfde filters.

- De speler zit niet langer vast aan het hoofdscherm. Dat haalt de crash weg die de app liet
  verdwijnen zodra je in de auto stapte, en laat de muziek ongestoord doorlopen als een scherm
  opnieuw wordt opgebouwd.

- **Afspelen op de telefoon-app kon blijven hangen op 0:00 na een wachtrijwijziging.** Nu niet meer.

- De speeldienst en de auto-detectie ondersteunen nu het rijscherm van de nieuwe interface.

- Inloggen in de nieuwe interface werkt nu ook op een app die nog nooit was ingelogd.

- Radio en het nieuws van het uur sturen in de nieuwe interface nu de speeldienst zelf aan, net als
  shuffle en herhalen al deden.

- Shuffle en herhalen in de nieuwe interface sturen nu de speeldienst zelf aan, niet meer alleen
  het scherm.

- **Uitloggen in de nieuwe interface werkt nu ook aan de Kotlin-kant.** Een nieuwe aanmelding daar
  wordt voortaan ook door de klassieke app en Android Auto herkend.

- **Wisselen tussen de klassieke en de nieuwe interface werkt.** Voorheen kwam je een seconde later
  op je beginscherm terecht in plaats van in de app.
- **De wachtrij aanvullen begint je nummer niet meer opnieuw.** Een set van drie minuten sprong
  eerder terug naar het begin.
- **Hoesjes zijn ook zichtbaar op een server zonder https.**

- De spraakherkenning van de app is nu ook beschikbaar voor de nieuwe interface, via hetzelfde
  woordbegrip als de auto en het bestaande microfoonscherm.

- Je kunt nu ook zonder genre om een liveset vragen: "speel een set af", "speel een Defqon set af"
  of "speel de nieuwste set van headhunterz af" (en de Engelse versies) werken vanaf nu net als in
  de auto.
## Global Version 6.35.1 (2026-09-11)

- De sectie "Hoog gewaardeerd" op het startscherm toont nu daadwerkelijk je hoog gewaardeerde nummers.
## Global Version 6.35.0 (2026-09-11)

- **Stel zelf in wat er op je startscherm staat** — per sectie een knop, een overzicht of niets,
  onder Instellingen → Startscherm. En Recent uitgebracht en Recent toegevoegd zijn terug.
## Global Version 6.34.0 (2026-09-11)

- **Dagelijkse mix en release radar staan nu ook op het startscherm**, niet alleen in de auto.
## Global Version 6.33.0 (2026-09-10)

- **Dagelijkse mix en release radar staan nu in het hoofdmenu van Android Auto.**

- **Een feed starten in de auto deed niets meer na een herstart, en speelde na middernacht de lijst
  van gisteren.** Allebei verholpen.

- **Ingevulde sterren zijn nu groen in de Spotify-stijl,** in plaats van hetzelfde grijs als een
  lege ster. Een waardering is nu in één oogopslag te zien.
## Global Version 6.32.1 (2026-09-10)

- **De bibliotheek, genres en zoeken gaven een verbindingsfout die geen verbindingsfout was.** De
  app kon zijn eigen cache niet meer openen na de vorige update. Dat is hersteld; de cache wissen is
  niet meer nodig.
## Global Version 6.32.0 (2026-09-10)

- Je ziet nu één regel per nummer in plaats van dezelfde track drie keer. Uit te zetten in de
  instellingen; de andere versies blijven bereikbaar via Versies in de track-info.
## Global Version 6.31.0 (2026-09-10)

- Bij een nummer kun je nu zien welke andere versies ervan in je bibliotheek staan.
## Global Version 6.30.1 (2026-09-08)

- Wat speelt en wat je hebt geselecteerd zijn nu twee verschillende dingen om naar te kijken, en de
  navigatiebalk laat zien waar je bent.
- Genres, festivals en artiesten zonder foto krijgen op Home dezelfde gekleurde cover als in de auto.
## Global Version 6.30.0 (2026-09-07)

- Android Auto tekent bladerniveaus met cover art nu als raster in plaats van als tekstlijst.
  Elk niveau gaf `null` mee als indeling, waardoor de auto terugviel op zijn eigen standaard en de
  albumhoezen die de items al droegen simpelweg negeerde. Niveaus zonder cover art blijven een
  lijst — de A–Z-index van artiesten, het hoofdmenu, en alle tracklijsten — omdat een raster van
  lege tegels of van veertig tracks de bestuurder meer blikken kost dan de lijst die het vervangt.

- Genres en artiesten zonder portret krijgen in Android Auto een cover die de app zelf tekent, in
  de kleur die MuMa voor dat genre stuurt. Die niveaus waren tekstlijsten met een generiek icoon:
  de auto tekent alleen een raster als de items iets te tonen hebben, dus zonder beeld hielp de
  raster-hint uit de vorige release daar niets. Een artiest met een portret houdt het portret.
- De kleuren komen van `GET /api/library/genres` en worden een uur vastgehouden. Is MuMa
  onbereikbaar, dan blijven de kleuren staan die er al waren — de auto is precies de plek waar dat
  het vaakst gebeurt, en een leeg raster is erger dan een oud.
## Global Version 6.29.0 (2026-09-07)

- Beheer heeft er vier werkende pagina's bij: tagger, genrecuratie, labelvoorstellen en
  podcastcuratie. Goedkeuren of afwijzen kan nu vanaf je telefoon.
## Global Version 6.28.4 (2026-09-06)

- **De Bibliotheek laat geen lege tabbladen meer zien.** Podcasts en festivals verschijnen in
  sets-modus, labels en line-ups in nummers-modus. De schakelaar tussen nummers en sets staat nu
  ook op dit scherm.
## [6.28.3] - 2026-09-03

### Changed
- **De lineup-pagina bladert per niveau: festival, editie, podium.** Alle lineups stonden als
  één lijst door elkaar, inclusief het festival, elke editie en elk podium apart. Een niveau
  met iets eronder gaat een stap dieper, de terugknop loopt weer omhoog, en bovenaan een
  editie staat "Alles van ..." om die editie in zijn geheel af te spelen.

## [6.28.2] - 2026-09-03

### Fixed
- **De speler laadde geen enkele afspeellijst meer in.** Nummers aan de wachtrij toevoegen deed
  niets: honderd nummers erin, wachtrij bleef nul, geen foutmelding. De speler-sessie kende de app
  sinds media3 1.11 geen enkel commando meer toe, en een niet-toegekend commando wordt stilzwijgend
  weggegooid. Onder de vorige media3-versie kreeg de app die set nog vanzelf.

## [6.28.1] - 2026-09-03

### Changed
- **De wachtrij meldt nu of het toevoegen is aangekomen.** Honderd nummers toevoegen en een
  milliseconde later een lege wachtrij zien, zonder ook maar één foutmelding -- dat is wat een
  rapport liet zien. De verbinding met de speler en de betrokken rechten worden nu meegelogd, plus
  de lengte van de wachtrij direct na het toevoegen.

## [6.28.0] - 2026-09-03

### Fixed
- **De app bewaarde alles onder gebruiker 0, en die bestaat niet.** Het account-id werd bij het
  inloggen op de verkeerde plek in het serverantwoord gezocht, stond er dus niet in, en werd
  stilzwijgend 0. Favoriete genres, tegels en app-instellingen werden daardoor nooit bewaard. Bij de
  volgende keer inloggen herstelt dit zichzelf.
- **Een diagnostiekrapport beschreef altijd de verkeerde sessie**, omdat je de app moet afsluiten om
  bij Instellingen te komen. Een rapport bevat nu ook de sessie daarvoor.
- **Een scherm dat niet laadde liet geen spoor na.** De fout kwam alleen als toast voorbij en stond
  in geen enkel rapport.

### Added
- **Een rapport vertelt nu wat je gedaan hebt**, niet alleen wat de app aan zichzelf meldde:
  afspelen, pauzeren, vorige, volgende, shuffle, de wachtrij, sterren, downloads, Beheer en elk
  lijstscherm met begin, einde en duur. Het meegestuurde log houdt driemaal zoveel regels vast.

## [6.27.0] - 2026-09-02

### Added
- **Beheer heeft zijn eerste drie systeempagina's: Overzicht, Gezondheid en Logboek.** Ze stonden
  er al als rij in, uitgegrijsd, met de melding dat ze voorlopig op het web woonden. Overzicht vat
  samen hoeveel containers draaien (en welke niet), welke versie de server meldt en welk nummer het
  laatst is toegevoegd. Gezondheid lijst elke container met status en image, met de logstaart in
  een dialoog. Logboek toont de gebeurtenissenstroom met een filter per niveau. Alle drie zijn
  lezen en verder niets.

## [6.26.0] - 2026-09-02

### Fixed
- **Een rij in de jukebox-wachtrij naar beneden slepen zette hem een plek te hoog neer.** Een nummer
  op zijn eigen plek "verplaatsen" schudde daardoor ook de rest van de volgorde door elkaar. Alleen
  de jukebox had hier last van; lokaal afspelen ging altijd goed.
- **Een standaard-vervaltijd voor delen opslaan brak de instelling in talen met andere cijfers.** In
  het Arabisch, Perzisch en Bengaals werd de waarde weggeschreven met cijfers die bij het teruglezen
  niet werden herkend. Het opslagformaat staat nu vast, los van de taal.

### Added
- **Tests voor drie plekken die wel gefixt maar nooit getest waren:** de jukebox-wachtrij, de
  volgorde van de download-wachtrij (waar de crash-fix van 0.31 op leunt) en de wortel van de
  Android Auto-bibliotheek.

## [6.25.3] - 2026-08-31

### Changed
- **Geen wijzigingen in de app zelf.** Deze versie bestaat omdat het bouwproces voortaan het
  vertaalbestand van elke release bewaart, zodat een crash uit de geïnstalleerde app automatisch
  onderzocht kan worden. Bijwerken is aan te raden: van eerdere versies is zo'n vertaalbestand er
  niet.

## [6.25.2] - 2026-08-29

### Fixed
- **De app viel om als het downloaden van een nummer mislukte, en dat gebeurde alleen bij slecht
  bereik.** De downloaddienst haalde een mislukte download uit de lijst met lopend werk en ging
  meteen op zoek naar het volgende nummer, nog voordat die download terug in de wachtrij stond. De
  dienst zag dan niets meer te doen en sloot zichzelf af, terwijl er nog twee downloads liepen — en
  die liepen bij het afronden tegen een afgebroken dienst aan. Bij een wegvallende verbinding
  gebeurt dat vrijwel altijd, want dan vallen alle downloads tegelijk om. Daarmee verdwijnt ook een
  stiller gevolg van dezelfde fout: een download die het opnieuw wilde proberen werd bij dat
  afsluiten uit de wachtrij gegooid en bleef zonder melding hangen.

## [6.25.1] - 2026-08-27

### Changed
- **De app is gebouwd tegen Android 36 en een reeks bijgewerkte bouwstenen.** `compileSdk` staat nu
  op 36 en loopt daarmee bewust één voor op `targetSdk`, dat op 35 blijft: `compileSdk` bepaalt welke
  API's de code mág aanroepen, `targetSdk` bepaalt welk gedrag gebruikers krijgen, en dat laatste
  verhoog je na een test op een toestel, niet als bijvangst van een afhankelijkheid. De aanleiding
  was dwingend: androidx.activity 1.13 en vijftien verwanten weigeren onder 36 geladen te worden.
  Verder mee: Retrofit 3.0.0, Gradle 8.14.5, Robolectric 4.16.1 en ArchUnit 1.5.0. Aan de app zelf
  verandert er niets zichtbaars — dit is een nieuw versienummer omdat de inhoud van de APK
  daadwerkelijk anders is, niet omdat er iets bij is gekomen.

## [6.25.0] - 2026-08-25

### Added
- **Alles wat het infoscherm van een nummer weet, is nu een ingang naar de bibliotheek.** Genre,
  label, mood en het jaar zijn aantikbaar en openen de nummerlijst met dat filter. Label en mood
  zijn nieuwe regels op het scherm. Een nummer met meerdere artiesten maakt van de artiestenregel
  een keuzemenu: elke artiest apart, plus wat ze samen maakten. Bij één artiest verandert er niets.
  De artiestenpagina heeft er een knop "Alle nummers" bij, want de albumlijst daar bevat alleen
  releases waarvan de artiest ook albumartiest is, en samenwerkingen staan op andermans releases.

### Changed
- **Beheer opent op een gegroepeerde index in plaats van een rij tabbladen.** Groepskoppen en
  pagina's in dezelfde volgorde als het web: Collectie, Curatie, Kanalen, Toegang, Systeem en
  Instellingen, met Overzicht en Downloaders los. Alle negentien beheerpagina's staan er; de
  zestien die de app nog niet heeft staan gedimd met de mededeling dat ze voorlopig alleen op het
  web zitten. Downloaders, Gebruikers en Toegangsverzoeken werken precies als voorheen.

### Added
- **Alles wat het infoscherm van een nummer weet, is nu een ingang tot de bibliotheek.** Tik op
  het genre, het label, de mood of het jaar en je krijgt de nummerlijst met dat filter. Label en
  mood zijn nieuwe rijen. Bij een nummer van twee artiesten geeft de artiestenrij een keuzemenu:
  elke artiest apart, plus wat ze samen maakten. Bij een artiest verandert er niets. Op de
  artiestenpagina zit nu een knop "All tracks", want de albumlijst toont daar alleen releases
  waar de artiest de albumartiest van is - samenwerkingen staan op andermans album. Overal staat
  erbij hoeveel nummers er in totaal aan het filter voldoen.

## [6.24.0] - 2026-08-24

### Added
- **Een nummer draagt nu zijn artiesten, moods en labels mee.** De server splitst een
  artiestentag in losse namen en stuurt de labels van de release mee; de app leest ze alle drie.
  Een lijst weet daarnaast hoeveel nummers er in totaal aan het filter voldoen, niet alleen
  hoeveel er op deze pagina staan. Nog niet zichtbaar in het scherm — dit is het fundament onder
  het doorklikken vanuit een nummer.


## [6.23.0] - 2026-08-23

### Changed
- **Het autoscherm is opnieuw ingedeeld.** Bovenin vier snelkoppelingen, in het midden één grote
  microfoonknop die er nu ook uitziet als een knop, en onderin compact wat er speelt: hoes, titel,
  bediening en de sterren.
- **Het spraakscherm luistert meteen als je het opent.** Geen tik meer nodig; de knop eronder is er
  voor nog een keer. Zodra de muziek speelt ga je na tien seconden vanzelf terug naar waar je
  vandaan kwam, en raak je het scherm aan dan blijft het staan.

### Fixed
- **De snelkoppelingen in de auto waren afgesneden, en onderin stond een balk die er niet hoorde.**
  De balk waren er twee: de tabbladen en het kleine spelertje, allebei een tweede uitvoering van wat
  het autoscherm zelf al heeft. Ze blijven nu weg zolang de autostand aan staat, en de
  snelkoppelingen en de speler nemen elkaar geen ruimte meer af. De sterren zijn iets kleiner, want
  vijf grote pasten niet naast elkaar op een smalle telefoon.
- **Nummers die je wegklikte telden niet mee.** De app legde een luisterbeurt alleen vast als een
  track helemaal uitspeelde. Druk je op volgende — bij sets van een kwartier eerder regel dan
  uitzondering — dan verdween hij. Dat telt nu wel, inclusief hoe lang je hem draaide. Korter dan
  vijf seconden blijft niet meetellen.

### Added
- **Het spraakscherm laat zien wat het begrepen heeft.** In woorden: wat het hoorde, en daaronder
  `genre Hardstyle`, `jaar 2021`, regel voor regel. Daar stond eerst een regel technische code. Gaat
  er iets mis, dan zit het volledige verslag één tik verderop.
- **De app onthoudt of je in de auto zat.** Een luisterbeurt krijgt er nu bij waar hij vandaan kwam,
  zodat je jaaroverzicht straks je rituren apart kan laten zien.

## [6.22.1] - 2026-08-22

### Fixed
- **De app ging uit zodra je in de auto stapte.** Opgelost. Zonder autoverbinding was er niets aan
  de hand en het scherm in de auto bleef ook gewoon werken, waardoor het op een probleem van de
  autostand leek.

## [6.22.0] - 2026-08-21

### Added
- **De zoekbalk begrijpt nu ook een verzoek.** Typ je "speel willekeurig uptempo hardcore uit 2021
  af", dan gebeurt dat, in plaats van een zoektocht naar die hele zin. Eén woord wordt nooit
  ontleed. Er is ook een tegel voor de snelle instellingen die het spraakscherm opent.

## [6.21.1] - 2026-08-21

### Fixed
- **De app startte niet meer op.** Opgelost. Wie 6.21.0 draaide hoeft niets te wissen.

## [6.21.0] - 2026-08-21

### Added
- **Er is een rijstand.** Eén scherm met grote knoppen: wat er speelt, spoelen, sterren geven, drie
  snelkoppelingen en de microfoon. De app biedt hem aan zodra je auto verbindt, en sluit hem als de
  verbinding wegvalt. Welke bluetooth-apparaten je auto zijn, kies je in de instellingen — laat je
  oordopjes daar uitgevinkt.
- **De app opent meteen op wat er de vorige keer stond.** Het startscherm en de bladerschermen
  lieten bij elke start pulserende vakjes zien terwijl ze de server opnieuw bevroegen om lijsten
  die bijna nooit veranderd waren. Die lijsten worden nu bewaard en direct weer neergezet, met
  een dun streepje onder de kop zolang de nieuwe versie onderweg is. Aantikken kan meteen, en
  zonder verbinding blijft gewoon staan wat je de vorige keer zag.

### Fixed
- **Sterren geven in de auto werkt weer.** Bij een nummer dat al sterren had deed de knop na een
  paar minuten niets meer: de app las de sterren dan terug uit een kopie die niet meebewoog, kwam op
  hetzelfde getal uit als bij de vorige tik en stuurde niets meer door. Stond een nummer op vijf
  sterren, dan sprong het daardoor terug naar geen.
- **Een gegeven waardering blijft nu overal staan.** Wat je in de auto of in een lijst waardeerde
  ging wel naar de server, maar werd in de app zelf nergens bijgewerkt. Kwam je later terug bij het
  nummer, dan stond de oude waardering er weer, alsof hij was gewist.

## [6.20.1] - 2026-08-21

### Changed
- **De app wordt vanaf nu uitgegeven onder zijn eigen naam.** Downloads heetten nog
  `ultrasonic-*`; ze heten nu `muma-mobile-*`. Voor je telefoon verandert er niets: een oudere
  installatie die om de oude naam vraagt wordt automatisch naar de nieuwe reeks gewezen, dus
  updates blijven gewoon binnenkomen.

## [6.18.0] - 2026-08-20

### Fixed
- **Een genre hardop vragen vindt het nu ook als de telefoon er één woord van verkeerd verstaat.**
  "Uptempo hardcore" leverde het brede genre Hardcore op, of helemaal niets. De spraakherkenning
  had nooit te horen gekregen welke genres deze bibliotheek bevat, dus die antwoordde met het
  gewone Nederlands dat er het dichtst bij lag; ze krijgt nu de genres met de meeste muziek mee
  voordat ze begint te luisteren. En een naam die net verkeerd terugkwam viel terug op het genre
  dat er toevallig in zat — "temple hardcore" bevat "hardcore" — waardoor een verzoek om het ene
  genre antwoordde met alles onder het andere. Zo'n naam wordt nu gelezen als het genre waar hij
  op lijkt, mits de rest exact klopt en het om een van de grote genres gaat. Waar de bibliotheek
  één genre op meerdere manieren spelt wint bovendien de spelling waar de muziek in zit.

### Added
- **Android Auto toont nu een zoekknop binnen MuMa.** De app gaf nooit aan dat er gezocht kon
  worden, dus verborg de auto zijn eigen zoekknop. Zoeken vanuit MuMa loopt door dezelfde
  spraakparser als de microfoon en het tekstveld.

## [6.17.2] - 2026-08-20

### Fixed
- **Een uitgesproken genre vindt nu al zijn muziek.** Om hardstyle vragen leverde niets op, ook al
  werd de zin goed begrepen. De bibliotheek bewaart een genre onder elke schrijfwijze die ooit in
  een tag stond — "Hardstyle", "HARDSTYLE" en "hardstyle" zijn drie losse ingangen — en MuMa hield
  degene die als eerste terugkwam. Dat bleek een restant met vier lange mixen, dus een verzoek om
  nummers vond er geen één van. Een uitgesproken genre draagt nu élke schrijfwijze die de
  bibliotheek ervan heeft; een genre dat het uitgesproken genre alleen maar bevat, zoals
  "Mainstream Hardstyle", blijft er buiten.

## [6.17.1] - 2026-08-20

### Fixed
- **MuMa Voice sluit de app niet meer af zodra hij iets te spelen heeft.** De opdracht werd goed
  gelezen en de bibliotheek goed doorzocht, maar bij de allerlaatste stap — de muziek daadwerkelijk
  starten — viel de app weg. Omdat dat alleen gebeurde als er iets *gevonden* was, leek het alsof
  MuMa Voice niets kon vinden.

## [6.17.0] - 2026-08-20

### Added
- **MuMa Voice: een microfoonknop in de app.** Tik erop en zeg wat er moet spelen. De tekst gaat
  door precies dezelfde parser en zoekmachine als Android Auto, dus een zin die in de auto werkt
  werkt hier ook. De spraakherkenning geeft meerdere lezingen van dezelfde zin terug en MuMa
  probeert ze op volgorde — dat is wat "hard style" alsnog op "hardstyle" laat uitkomen. Er staat
  ook een tekstveld op datzelfde scherm, om een formulering uit te proberen zonder te praten.
- **MuMa vraagt na wat je bedoelde als een naam meerdere dingen kan zijn.** "Speel Thunderdome" kan
  het label, het album of de playlist zijn. MuMa Voice laat de mogelijkheden zien; je tikt er een
  aan of je zegt "het label". In de auto kan dat niet, dus daar kiest hij de sterkste lezing.
- **Albums, playlists, titels en sterren kunnen uitgesproken worden.** "Speel album thunderdome af",
  "speel de afspeellijst zomer af", "speel het nummer dragonborn af", "speel hardstyle met minstens
  4 sterren af". Twee waarden tegelijk kan ook: "speel hardstyle en hardcore af" is één
  zoekopdracht, terwijl "drum and bass" één genre blijft.
- **Voice diagnostics, onder Over.** Elke spraakopdracht laat een volledig spoor achter — via welke
  callback hij binnenkwam, de zoekopdracht zoals ontvangen, élke extra die Android meestuurde, welke
  regel welk woord opeiste, en het verzoek dat eruit ging. De laatste vijftig blijven bewaard en
  zijn te delen. Zo is te zien wat Google van je zin maakt vóór MuMa hem krijgt.

### Fixed
- **Een uitgesproken titel wordt op de titel gezocht, niet op de hele zin.** "Speel het nummer
  dragonborn af" zocht letterlijk daarnaar en vond niets; nu wordt er op "dragonborn" gezocht.
- **Een uitgesproken sterrenfilter sleept niet langer elke ongewaardeerde track mee.**

## [6.16.0] - 2026-08-19

### Added
- **De instelling onder Uiterlijk kiest nu een hele stijl in plaats van alleen een accentkleur.** Er
  stond Groen en Blauw, wat één kleurtje verwisselde en verder alles hetzelfde liet. Er staat nu
  **Spotify** en **MuMa**. Spotify is de app precies zoals hij was. MuMa houdt hetzelfde groen voor
  nummers en blauw voor sets, maar staat op een warmere, diepere achtergrond, scheidt lijstregels
  met een haarlijn in plaats van ze als kaartjes te laten zweven, dimt derde- en vierderangs tekst
  echt, rondt hoeken strakker af, dimt de veldlabels in plaats van ze groen te kleuren, en kleurt
  een ingevulde ster goud. Spotify blijft de standaard, dus er verandert niets tot je zelf wisselt,
  en wisselen werkt meteen. Het blauwe accent vervalt; het blauwe app-icoon is een aparte instelling
  en blijft gewoon staan.

### Fixed
- **Een geselecteerde regel verspringt niet meer van vorm.** De geselecteerde achtergrond was op 8dp
  afgerond en de gewone op 16dp, dus een regel klapte zichtbaar om zodra je hem aantikte.
- **Het uitklapvak is geen witte balk met onleesbare tekst meer.** Het was nog geschilderd voor een
  lichte modus die de app al sinds ver voor de rebrand niet meer heeft.

## [6.15.0] - 2026-08-19

### Added
- **De stemzoekopdracht begrijpt nu een heel verzoek in plaats van alleen een genre.** "Speel
  willekeurige favorieten uit 2023 af" kwam bij de vrije-tekstzoekopdracht terecht, die alleen
  artiest-, album- en titelnamen kent, en antwoordde met stilte. De zin wordt nu uit elkaar gehaald
  in de onderdelen waar de bibliotheek op kan filteren -- een genre, een artiest, een label, een
  jaar, je favorieten, en nummers of livesets -- plus een volgorde: "willekeurig", "recent" of
  "recent toegevoegd". Alles is combineerbaar en optioneel, in het Nederlands en in het Engels. Een
  naam die de bibliotheek niet kan plaatsen valt weg en de rest speelt gewoon door.
- **Een pagina met alle spraakcommando's**, te vinden via Over.
- **Een tracklijst is nu zelf te sorteren.** Een genre, label, festival, jaar, podcast, line-up of
  sterrenfilter kwam altijd terug op releasedatum. Boven de lijst staat nu dezelfde keuzelijst als
  in de webinterface: recent uitgebracht, recent toegevoegd, meest gespeeld, recent gespeeld, op
  waardering, op naam en willekeurig. De lijst opent op de sortering waarmee je binnenkwam, en je
  keuze overleeft het draaien van het scherm. Albums, afspeellijsten en podcastafleveringen houden
  hun eigen volgorde.

### Fixed
- **In de Android Auto-bibliotheek stond "Favorieten" twee keer.** De nummers met een ster en de map
  met favoriete genres en tegels hadden in het Nederlands allebei dezelfde naam. Er is nu één map
  Favorieten, met daarin "Favoriete nummers" naast de favoriete genres en playlists.

## [6.14.2] - 2026-08-19

### Changed
- **Een genre dat je met je stem opvraagt speelt nu op releasedatum, niet op datum toegevoegd.**
  "Speel genre hardstyle af" gaf de nummers die het laatst in je bibliotheek waren beland, en bij een
  importronde is dat honderd nummers uit twintig jaargangen die op één middag binnenkwamen. De
  stemzoekopdracht gebruikt nu dezelfde sortering als het blok "Recent uitgebracht" op de
  startpagina. Een nummer zonder releasedatum valt terug op zijn bestandsdatum en sluit de rij, dus
  er verdwijnt niets uit het resultaat. De bladerboom onder Genres sorteert ongewijzigd op datum
  toegevoegd.

## [6.14.1] - 2026-08-18

### Fixed
- **"Speel mainstream hardstyle af" speelt nu dat genre.** Het woord "genre" was het enige signaal
  waar de app op afging, en juist dat woord haalt Google Assistent uit je zin zodra hij begrijpt dat
  je een genre bedoelt. Wat overbleef ging naar de gewone zoekactie en landde op een album. Een zin
  zonder het woord "genre" wordt nu ook als genrenaam geprobeerd, en speelt dat genre zodra hij
  precies overeenkomt met een genre uit je bibliotheek. Komt hij niet precies overeen, dan verandert
  er niets en zoekt de app gewoon door. "... af op MuMa" wordt voortaan van de zin afgehaald.

## [6.14.0] - 2026-08-18

### Added
- **"Speel genre hardstyle af" speelt dat genre.** De spraakzoekopdracht draaide altijd de
  vrije-tekstzoekactie, en die kijkt naar artiest, album en titel -- een genre komt daar niet in
  voor, dus bleef de auto stil of landde je op een willekeurig album. Een uitgesproken genre draait
  nu dezelfde lijst als het bladermenu: de laatst toegevoegde nummers van dat genre, tot het maximum
  uit de instellingen, ongeacht waardering. "Speel hardstyle sets" geeft de lange opnames in plaats
  van de nummers. "Hard style" en "tech house music" vinden hun genre alsnog; een genre dat de
  bibliotheek niet kent valt terug op de oude zoekactie.
- **"Speel X hierna af op MuMa" zet dat nummer achter wat er speelt.** Google Assistent kent geen
  wachtrij-werkwoord voor externe muziekapps, dus reist de instructie mee in het speelverzoek zelf,
  als markeerwoord aan het eind van de zin. De rest van de wachtrij blijft staan. Markeerwoorden
  tellen alleen aan het eind, dus een titel als "The Next Level" blijft heel.

## [6.13.2] - 2026-08-18

### Fixed
- **"Speel alles" in de auto speelt weer op volgorde.** Shuffle bleef aan staan tussen luisterbeurten
  door, en het bladermenu van Android Auto raakte die stand nooit aan -- dus een wachtrij die je in
  de auto startte erfde de shuffle van je laatste luisterbeurt op de telefoon. Een wachtrij die in
  de auto begint zet shuffle nu uit. De shuffle-knop in de auto blijft gewoon werken.

## [6.13.1] - 2026-08-18

### Fixed
- **"Onlangs afgespeeld" bewoog niet meer.** De bron van een wachtrij werd blijvend onthouden in
  plaats van per wachtrij, dus het laatste bladerscherm waaruit je speelde bleef de bron van alles
  daarna. Een bron hoort nu bij precies één wachtrij.
- **Een snelkoppeling verschijnt zodra je op play drukt**, niet pas als een nummer uitspeelt.
- **Een genre-, label-, festival-, podcast- of jaarlijst wordt als zichzelf herkend.** Spelen uit
  Raw Hardstyle legde de compilatie vast waarop het nummer stond; nu staat het genre er.
- **"Speel nu" op één nummer** onthoudt de lijst waaruit je het speelde. "Speel hierna" en
  "Achteraan" laten de lopende bron met rust.
- **Snelkoppelingen hebben hun hoes terug.** Een album of afspeellijst draagt weer het id waarop de
  hoes hangt; een genre, festival, label of podcast leent er één van een nummer met die tag.

### Changed
- **Een wachtrij zonder lijst erachter legt niets meer vast.** Het album van het spelende nummer is
  niet de plek waar je heen ging.

## [6.13.0] - 2026-08-17

### Added
- **Het beginscherm eindigt in twee lijsten die je kunt lezen.** "Onlangs uitgebracht" en "Onlangs
  toegevoegd" staan er als nummerlijsten, elk met een "Toon meer" die de volledige lijst opent in
  dezelfde volgorde. Een carrousel herken je aan de hoes, en juist het SoundCloud- en YouTube-deel
  van je bibliotheek heeft er geen — een rij blanco vierkantjes zei niets.
- **Twee instellingen onder Home**: hoeveel snelkoppelingen het raster toont (2 tot 10, standaard 8)
  en hoeveel regels elke lijst toont voordat je "Toon meer" nodig hebt (1 tot 10, standaard 5).
- **Een Podcasts-pagina**, met dezelfde shows en afleveringen als in de webspeler.

### Changed
- **"Onlangs afgespeeld" onthoudt waar je vandaan speelde.** De lijst vulde zich met alles wat je
  opende, dus bladeren vervuilde hem en het album van één aangetikt nummer duwde de rest eruit. Er
  wordt nu pas iets vastgelegd als je op afspelen drukt, en wat er wordt vastgelegd is de lijst waar
  de wachtrij uit kwam. Speel je één nummer uit Raw Hardstyle, dan is de snelkoppeling Raw
  Hardstyle, en aantikken geeft je andere nummers uit diezelfde hoek in plaats van een herhaling.
  Shuffle-all, favorieten en gedeelde links leggen niets vast.
- **Memories is één balk geworden** met het dichtstbijzijnde jaar erin, in plaats van een carrousel
  van jaren, en verdwijnt op een dag waar niets in zit. Alle jaren staan nog gewoon op het
  Memories-scherm.

### Removed
- De sectie "Onlangs bijgewerkt". Herschreven metadata is iets wat de scanner doet, niet iets om
  naar te luisteren.

### Nog niet
- Radio is nog geen bron voor een snelkoppeling; het bestaat alleen in de Android Auto-verkenner.
- Een snelkoppeling naar een genre onthoudt het genre, niet de sortering die op je scherm stond.

## [6.12.0] - 2026-08-17

### Changed
- **Een nummer toont de originele releasedatum in plaats van de datum van de uitgave waarin het
  zat.** De app liet die datum altijd al zien, maar kreeg de originele nooit doorgestuurd. Staat er
  alleen een jaartal als origineel, dan wint een volledige datum van de uitgave — je levert dus
  nooit precisie in.

## [6.11.0] - 2026-08-07

### Added
- **Kies je eigen kleur, en je eigen icoon.** Onder Instellingen → Uiterlijk staat nu een
  accentkleur: MuMa-groen of het indigo van het oude Ultrasonic. Voortgangsbalken, actieve tabbladen,
  chips en de afspeelknop volgen die keuze.
- Het app-icoon is een losse instelling in dezelfde twee kleuren. Je kunt dus een blauw accent met
  een groen icoon draaien, of andersom.
- Sets-modus houdt in beide thema's een eigen kleur, zodat nummers en sets nooit dezelfde tint
  krijgen.

### Changed
- De oude thema-instelling bood Dag & Nacht, Donker en Zwart aan en die leverden alle drie hetzelfde
  zwarte thema op. Stond hij op een van die drie, dan begin je nu in het groen.
- De meldingen voor downloads en afspelen tonen het MuMa-merkteken; dat waren de laatste twee
  plekken met een Ultrasonic-koptelefoontje.
- Sommige launchers halen de app van je beginscherm als het icoon wisselt. De app waarschuwt daarvoor
  op het moment zelf.

## [6.10.0] - 2026-08-07

### Added
- **Tik op het spelende nummer voor alle info.** Het menu rechtsboven had zeven regels die allemaal
  over datzelfde ene nummer gingen — naar artiest, naar album, metadata, songtekst, delen,
  verversen en twee keer bookmark — weggestopt achter een menu dat verder over de wachtrij gaat.
  Tik nu op de titel en er schuift een venster omhoog met de hoes op een vervaagde versie van
  zichzelf, de vijf sterren, en artiest en album als regels waar je op door kunt klikken.
- Songtekst, delen, bookmark en verversen staan er als knoppen. Daaronder genre, tracknummer,
  uitgiftedatum en duur, met de technische details dichtgeklapt. Lang indrukken op het pad kopieert
  het.

### Changed
- Het menu rechtsboven gaat weer over de wachtrij en de speler.
- Velden die het nummer niet heeft verdwijnen nu, in plaats van als `Jaar: ` zonder iets erachter te
  blijven staan zoals het oude metadata-scherm deed. Dat scherm is vervangen: ook lang indrukken op
  een nummer in de wachtrij opent hetzelfde venster.

## [6.9.2] - 2026-08-05

### Changed
- **De app heet voortaan gewoon MuMa, en heeft een eigen icoon.** "Mobile" is weg uit de naam op je
  startscherm, uit de meldingen en uit de app zelf: het is hetzelfde MuMa als in je browser. Het
  icoon is niet langer het geërfde koptelefoontje op paars, maar MuMa's eigen merkteken — vijf
  staafjes in een groene schijf waarvan de bovenrand een M vormt. Hij installeert gewoon over je
  huidige versie heen.

### Fixed
- **"Onlangs afgespeeld" onthoudt weer wat je hebt geluisterd.** Het raster op de startpagina
  bewaarde alleen wat je zelf aantikte in een lijst; wie via Android Auto, de melding of de
  wachtrij luisterde, liet dus niets achter. Een avond muziek in de auto veranderde er niets aan.
  Bij dezelfde verbouwing raakte ook het bijhouden van "Laatst gespeelde genres" weg, terwijl
  Android Auto die lijsten wél bleef tonen — ze waren daardoor altijd leeg. Allebei worden ze nu
  weer bijgewerkt: elk nummer dat je uitluistert zet zijn album in het raster en zijn genres in de
  genrelijst.

## [6.9.1] - 2026-08-05

### Fixed
- **"Controleer op updates" ziet nieuwe versies weer.** Sinds de naamswijziging heette het
  geüploade installatiebestand `muma-mobile-...` in plaats van `ultrasonic-...`, en de
  downloadsite gebruikt precies dat stukje naam om bij te houden welke versies bij elkaar horen.
  De app vroeg nog naar de oude naam en kreeg niets terug: 6.9.0 was onzichtbaar en je telefoon
  meldde dat je bij was. De bestandsnaam staat weer op het oude; de app blijft MuMa Mobile heten.

## [6.9.0] - 2026-08-05

### Changed
- **Favoriet bestaat niet meer los: vijf sterren is je favoriet.** Het hartje in de nummerlijst, de
  losse sterknop in de speler en het menu-item erachter zijn weg; de vijf sterren staan er altijd.
  Je favorietenlijst blijft staan waar hij stond en toont voortaan wat vijf sterren heeft. De
  STAR-knop op een bedrade koptelefoon zet vijf sterren.

### Added
- **Albums kun je nu waarderen.** De ster op een albumregel zette eerder een vlaggetje dat nergens
  heen ging; hij zet nu vijf sterren, en die waardering komt ook in je bestandstags terecht.

## [6.8.0] - 2026-08-05

### Fixed
- **In Android Auto kon je alleen 1 ster geven.** Stond een nummer op 5, dan werd het 1; stond het
  op 1, dan bleef het 1; en een nummer zonder waardering kreeg er ook 1. De knop gaf de waardering
  die erop stond mee aan de auto, maar Android Auto stuurt die informatie niet terug, dus begon de
  app elke tik weer bij nul en kwam altijd op 1 uit. De knop kijkt nu naar het nummer dat speelt, en
  loopt weer netjes door 0, 1, 2, 3, 4, 5 en terug naar 0. Een waardering die je op de telefoon
  geeft, zie je nu ook meteen op de knop in de auto.

## [6.7.0] - 2026-08-03

### Added
- **Tracklijst met drie regels.** Album en artiest stonden samengeperst op één regel, waardoor
  beide afkappen zodra een titel wat langer is. Onder Instellingen > Appearance kies je nu tussen
  2 regels (zoals het was) en 3 regels: titel, album en artiest onder elkaar, met rechts de
  sterren, de releasedatum en de speelduur. De compacte weergave blijft de standaard.

### Fixed
- **Beheer-tabblad was voor iedereen verborgen.** De controle op beheerdersrechten ging naar
  `api/auth/verify`, en dat adres viel onder het `/api/auth/`-voorvoegsel dat de app behandelt als
  "hier hoeft geen sleutel bij". Het verzoek vertrok dus zonder sleutel: 401, leeg antwoord, geen
  beheerder. De app noemt nu de vier inlogadressen apart, en de controle wordt opnieuw gedaan zodra
  de app uit de achtergrond terugkomt en zodra automatisch inloggen een sleutel heeft opgehaald.
- **Scherm draaien verdubbelde de afspeellijst.** Honderd nummers werden er tweehonderd. Bij het
  draaien wordt het scherm opnieuw opgebouwd en zette de app de opgeslagen sessie terug, terwijl de
  speler zelf gewoon doordraaide met de lijst er nog in — en terugzetten betekent toevoegen. De
  opgeslagen sessie wordt nu alleen nog teruggezet in een lege speler.

## [6.6.0] - 2026-08-02

### Added
- **Memories: wat er op deze dag werd uitgebracht.** In het Bibliotheek-tabblad staat een
  Memories-scherm, en de startpagina opent met een korte rij "Vandaag, 8 jaar geleden". Alleen
  tags met een volledige releasedatum tellen mee; levert een dag niets op, dan wordt er drie dagen
  naar beide kanten gekeken en staat er "deze week". Je telefoon stuurt zijn eigen datum mee. De
  rij op de startpagina kun je uitzetten in de instellingen.
- **Diagnostiek versturen zonder op een crash te wachten.** Crashrapportage kwam pas bij de
  volgende start op gang, en alleen als de app echt was gestopt. Bij een mislukte call of een leeg
  scherm blijft de app draaien, dus dat bereikte de server nooit. In Instellingen staat nu "Send
  diagnostics now" onder Muma: die stuurt het log van de huidige sessie op en zet een kopie in
  Downloads/UltrasonicLogs. De knop staat bewust buiten de debug-categorie, want die is verborgen
  in release builds. Anders dan het automatische rapport trekt hij zich niets aan van de
  "Crash detection"-schakelaar — op de knop drukken is toestemming genoeg — en hij gooit nooit een
  crashbestand weg dat nog niet gerapporteerd is.

### Changed
- **Geen zoekveld meer op Ratings en Jaren.** Ratings is vijf vaste kaarten die allemaal tegelijk
  in beeld staan, Jaren is een korte lijst getallen in een vaste volgorde. Jaren begint nu bij het
  nieuwste jaar.

### Removed
- **Het "MuMa Sync"-scherm** met zijn zes knoppen. Tegels synchroniseren zichzelf via de
  tegelbewerker en inloggen gebeurt al bij het opslaan van een server. Je MuMa-ID en API-sleutel
  blijven in de instellingen staan.

### Fixed
- **Artiest-snelkoppelingen halen hun ontbrekende afbeelding alsnog op**, ook als ze bewaard zijn
  toen de server nog geen foto had.
- **Artiesten zonder afbeelding kosten niet meer bij elk terugscrollen een mislukte aanvraag**;
  die worden twaalf uur onthouden, en alleen als de server echt "niet gevonden" antwoordde.

## [6.5.26] - 2026-08-02

### Changed
- **De sterknop in Android Auto geeft een cijfer in plaats van een favoriet.** De knop loopt nu
  door zes standen: een lege ster voor geen waardering, daarna een ster met het cijfer 1 tot en
  met 5 erin, en vanaf 5 weer terug naar leeg. De waardering is waar de app verder op sorteert en
  filtert, maar was vanuit de auto niet te bereiken. Favorieten werken op de telefoon gewoon
  door; alleen hun knop in de auto vervalt, zodat shuffle en herhalen op de hoofdbalk blijven
  staan.

## [6.5.25] - 2026-08-02

### Added
- **De artiestenpagina begint bij de artiest.** Bovenaan staat nu een kop met de foto, de naam,
  "12 albums · 143 nummers", de jaren waarin de discografie loopt en de genres. De "alles
  afspelen"-knop zit in die kop.
- **Labels doorbladeren.** Labels staan nu als tabblad in Library, naast Genres; een tik opent de
  nummers van dat label. Voorheen kon je alleen op label filteren als je de naam al kende.
- **Sallaands en Brabants**, te kiezen in het taalmenu in Instellingen — dezelfde twee dialecten
  die de webinterface in 0.0.59 kreeg.

### Fixed
- **Het mapkeuzemenu stond niet meer in één smalle kolom geperst** als een albumlijst op
  rasterweergave stond.
- **Het Nederlands is af, en het Engels is echt Engels.** Er ontbraken 163 Nederlandse teksten, en
  28 teksten stonden in het Nederlands in de Engelse bestanden — een Engelstalige telefoon liet
  dus "Artiesten", "Jaren" en "Goedkeuren" zien.
- **Artiesten zonder opgehaalde foto zijn niet langer grijs.** Je krijgt nu de ingescande
  artiestfoto, of anders de hoes van zijn oudste release.

## [6.5.24] - 2026-08-01

### Added
- **Zoeken en sorteren in Library.** Boven Artiesten en Albums staat nu een zoekveld en een
  sorteerkeuze. Zoeken kijkt door je hele bibliotheek, niet alleen door wat er toevallig geladen
  is, dus "angerfist" vindt die artiest ook als je nog bovenaan de A's staat. Sorteren kan op
  naam, aantal nummers, aantal albums, recent toegevoegd en willekeurig; bij albums ook op artiest
  en jaar. Bij elke artiest staat nu hoeveel albums en nummers je van hem hebt. De tabbladen
  Genres, Jaren, Festivals, Lineups en Ratings hebben hetzelfde zoekveld.

### Fixed
- **Op een artiest tikken opende een leeg scherm.** Zowel in de artiestenlijst als bij de
  artiesten op het beginscherm kwam je op een pagina die nooit is afgebouwd. Je komt nu op het
  album-overzicht van die artiest — hetzelfde scherm dat je al kreeg via zoeken en via "Toon
  artiest" in de speler.


## [6.5.23] - 2026-08-01

### Fixed
- **De knoppen op "Over" wezen naar de verkeerde site.** "Website openen" en "Bug melden" openden nog de pagina's van het originele Ultrasonic-project. Ze gaan nu naar muma.example.com en naar de issue-tracker van dit project zelf.

## [6.5.22] - 2026-08-01

### Fixed
- **De app crashte zodra je Instellingen opende.** Dit kwam door de nieuwe "Interface size"-optie uit 6.5.21: de percentages erin (100%, 75%, ...) werden per ongeluk als opmaakcode gelezen in plaats van als gewone tekst, waardoor de app afsloot op het moment dat die regel getekend werd. Opgelost; Instellingen opent weer gewoon.

## [6.5.21] - 2026-08-01

### Added
- **De hele interface is kleiner en er past een stuk meer op je scherm.** Standaard staat alles nu op 75% van het oude formaat, ongeveer even compact als Spotify. Bevalt dat niet, dan zet je het terug bij Instellingen > Weergave > "Interface size": van 100% (het oude formaat) tot 70%.
- **Favoriete genres.** Houd een genre ingedrukt in Library → Genres en kies "Aan favorieten toevoegen". Favorieten staan bovenaan de lijst met een sterretje. Het is dezelfde lijst als in de webspeler, dus wat je op je telefoon favoriet maakt, staat ook daar.
- **Een Favorieten-map in Android Auto**, met daarin Favoriete genres en Favoriete playlists. Een favoriet genre begint direct met spelen, zonder eerst een jaar of sortering te kiezen. Onder playlists staan de tegels waarvan je het sterretje hebt aangezet in het filtermenu. De map verschijnt alleen als er iets in staat.

### Changed
- **De standaardtegels op Nummers/Livesets zijn nu tijdvak-tegels.** De acht tegels die alleen op één genre filterden voegden niks toe naast de genre-lijst. In plaats daarvan drie tegels die je via genres niet in één keer maakt: Hardstyle Classics (Mainstream Hardstyle, 2009-2017), Millennium Hardcore (Mainstream Hardcore, 2010-2015) en Early Uptempo (Uptempo Hardcore, 2012-2017), elk in willekeurige volgorde. Heb je al tegels staan, dan blijven die zoals ze zijn.
- **Geen crashmelding meer bij het opstarten.** De app zag elke keer dat Android hem op de achtergrond had afgesloten als een crash, waardoor je bij vrijwel elke start de vraag kreeg om diagnostiek te delen. Crashdetectie staat nu uit; je zet hem desgewenst aan via Instellingen > Debug-opties > Crashdetectie.

## [6.5.20] - 2026-07-31
### Added
- **Uitlogknop** in het menu rechtsboven. Hij vraagt eerst om bevestiging, stopt het afspelen en brengt je terug naar het inlogscherm met je gebruikersnaam alvast ingevuld. Gedownloade muziek blijft gewoon op je toestel staan.
- **De startpagina laat meteen zien dat hij aan het laden is**: grijze plaatshouders in de vorm van de kaarten die eraan komen, in plaats van een leeg zwart scherm. Elke sectie vult zichzelf in zodra hij klaar is.

### Changed
- **De startpagina laadt een stuk sneller.** De onderdelen werden een voor een opgehaald; dat gebeurt nu tegelijk.

### Fixed
- **Klopt je wachtwoord niet meer, dan kom je terug op het inlogscherm.** Werd je wachtwoord op de server gewijzigd terwijl de app openstond, dan gaf elk scherm een foutmelding waar je niets mee kon en vroeg de app nooit meer om in te loggen.

## [6.5.19] - 2026-07-31
### Fixed
- **De app crashte bijna elke keer dat het afspelen begon.** In de uitgebrachte versie konden de genres van een nummer niet teruggelezen worden, waardoor de app onderuit ging zodra er een nummer in de speler geladen werd. Afspelen, "alles afspelen" en teruggaan naar het spelerscherm werken weer.
- **Een foutmelding die verscheen terwijl de app op de achtergrond stond, kon de app afsluiten** in plaats van de fout te tonen. Zo'n fout komt nu als gewone melding, of als korte toast wanneer er geen scherm beschikbaar is.

## [6.5.18] - 2026-07-31
### Added
- **Vier tabbladen erbij in Library**: Jaren, Festivals, Lineups en Ratings. Zoeken op lineup kan daarmee weer.
- **Beheer-tab** die de beheerpagina's van de webui spiegelt: Downloaders, Gebruikers en Verzoeken. Alleen zichtbaar als je beheerder bent.

### Changed
- **In sets-modus tonen de carrousels op de startpagina festivals in plaats van labels.** Livesets zijn festivalopnames, dus een platenlabel zegt er weinig over.

## [6.5.17] - 2026-07-31
### Fixed
- **Een artiest aantikken op de startpagina leverde niets op.** De carrousels bevatten ook remixers en gastartiesten zonder eigen albums, waardoor je op een leeg scherm belandde. Er staan nu alleen nog artiesten met eigen releases in.
- **Een label aantikken leverde niets op.** De labels kwamen uit een andere bron dan waarop gefilterd wordt, dus zoeken op zo'n naam gaf nul resultaten. Beide gebruiken nu dezelfde lijst.
- **Artiestafbeeldingen** worden weer onder de juiste sleutel en op groot formaat opgehaald, zodat ze gedeeld worden met de rest van de app.

## [6.5.16] - 2026-07-31
### Fixed
- **Bladeren kan weer**: met de filterknoppen op de startpagina verdween in 6.5.15 ook de enige ingang naar filter-afspeellijsten, genres, de albumlijst en de artiestenlijst — een filter-afspeellijst maken kon zelfs helemaal niet meer. Alles zit nu in de nieuwe Library-tab.
- **De Favorieten-tab liet een kopie van de startpagina zien.** Nu staan er je albums en artiesten met een ster, plus alles wat je vier sterren of hoger gaf; tik je op zo'n nummer, dan speelt het meteen.

### Added
- **Library-tab** met vijf schuifbare pagina's: Playlists (je filter-afspeellijsten, inclusief nieuwe maken), Genres, Artiesten, Opgeslagen afspeellijsten en Albums.

### Changed
- **De onderbalk heeft nog drie knoppen**: Home, Library en Favorieten. Zoeken is eruit omdat het zoekveld al bovenin zit; opgeslagen afspeellijsten zitten nu in Library.

## [6.5.12] - 2026-07-30
### Fixed
- **Login screen showed a generic "network error" for every kind of login problem**: it's now able to tell you when the server itself is unreachable, versus when the server responded but the login didn't succeed.
- **A hidden bug could make the first-time login check silently report "success" without actually contacting the server**, if "Auto-switch server online/offline" was left on from an older install. This no longer happens.

## [6.5.11] - 2026-07-29
### Changed
- **Dependencies**: Updated `activity-ktx`, `core-ktx`, `gson`, `okhttp`, `rxjava`, and other core libraries to latest stable versions.
- **Target SDK**: Updated to Android 17 (API 37).
- **Login/auth UI**: Restyled the login/welcome dialog, edit-server screen, and Google access-request screen to match the web frontend, including a branded "Sign in with Google" button and colored status banners for access requests.
- **Settings**: `autoSwitchOffline` now defaults to `false` instead of `true`.

### Added
- **Export to Media Device**: New feature to export the current playlist to external USB devices (e.g., Shokz OpenSwim Pro) via SAF. Includes an option to clear the destination folder before exporting.

## [6.5.2-232] - 2026-07-16
### Fixed
- **Update Checker**: Added `u=guest` and `p=guest` credentials to APK download URL to prevent access errors.

## [6.5.0] - 2026-07-11
### Added
- **Log Viewer**: New diagnostic tool accessible from Settings > About to view and share app logs.
- **Architecture Tests**: Integrated ArchUnit for maintaining code structure and dependency rules.
- **Coverage Reporting**: Added JaCoCo integration for automated test coverage analysis.
- **Welcome Messages**: Dynamic greeting messages based on the time of day.

### Changed
- **UI Refinement**: Wrapped main layout in a scrollable view for better accessibility on smaller screens.
- **Track Loading**: Optimized track and album loading with a centralized, state-aware repository pattern.
- **Server Selection**: Improved UX for server switching and connection validation.
- **CI/CD**: Enhanced build pipeline with pre-commit hooks and automated documentation updates.

### Fixed
- **Android Auto**: Reverted to a stable Tile-based interface to resolve navigation and performance issues.
- **Build Stability**: Fixed various compilation errors and resource conflicts in recent feature branches.

## [6.4.0] - 2026-07-05
### Added
- **MuMa Cloud Sync**: New server-side backup system for app settings. Users can now backup their entire configuration to the MuMa database.
- **Settings Restore**: Easily restore settings on a new device by entering your MuMa User ID and API Key.
- **Enhanced API Integration**: Implemented a modern MumaAPIClient with support for secure X-API-Key authentication.
- **Cloud Management UI**: Dedicated sync controls in the Settings menu for manual backup and restore operations.

## [6.3.3] - 2026-07-05
### Changed
- **LMS API Key**: Replaced dynamic API key fetching with a hardcoded Subsonic API key for LMS servers for simplified setup.

## [6.3.2] - 2026-07-05
### Added
- **API Key Automation**: Automatically fetches Subsonic API keys for LMS servers during setup and connection testing.

## [6.3.0] - 2026-07-05
### Added
- **Welcome Dialog**: New users are now greeted with a setup wizard to enter login credentials.
- **Auto-Server Discovery**: Automatically configures Alpha and Stable LMS servers based on build type.
- **Connection Validation**: Real-time server ping during setup to ensure correct credentials.
- **Dynamic Playlists (Tiles)**: Support for server-side dynamic playlists synced with LMS and Music Management.
- **Debug Features**: Share and view debug logs directly from settings in debug builds.
- **ListenBrainz**: Scrobbling is now enabled by default.

### Changed
- **UI Improvements**: Significant visibility improvements to player controls, including a green pause button.
- **Landscape Player**: Optimized player layout for landscape mode with scrollable controls.
- **Tile Loading**: Delayed initial tile loading until server connection is established.
- **Deployment**: Improved APK distribution with robust fallbacks.
- **Default Settings**: 5-star rating system enabled by default.

## [6.2.0] - 2026-07-04
### Added
- **Spotify-style UI**: Integrated dynamic "Songs" (Green) and "Sets" (Blue) branding throughout the app.
- **Merged Views**: "Songs" and "Livesets" tabs merged into a single view with a brand-aware toggle switch.
- **OLED Black Theme**: Implemented a pure black (#000000) background for OLED displays and removed the light theme.
- **Brand Consistency**: Dynamic accent color updates for switches, sliders, chips, and scrollbars across all fragments.
- **Tooling Upgrade**: Modernized build pipeline with Gradle 9.6.0 and updated core dependencies.
- **Improved About Screen**: Detailed information on `muma/lms` integration and technical build details.
- **Update System**: Enhanced auto-update checker with authentication and version tracking.

## [6.0.0-140] - 2026-07-04
### Added
- Integrated full changelog support for debug builds in the distribution pipeline.
- Added direct link to `changelog.md` in the download portal.

## [5.2.1] - 2026-07-04
### Added
- Automated version increment support to `bup` script (patch, minor, major).
- Automatic synchronization of bundled assets during release.

## [5.2.0] - 2026-07-04
### Added
- Major dependency update: All packages and Gradle are now completely up to date.
- Under the hood improvements with Gradle 8.12.1, AGP 8.7.3, and Kotlin 2.1.0.
- Script and build pipeline reorganization.

## [5.1.0] - 2026-07-04
### Added
- Added auto update functionality that depends on an apk-hoster server. This will run on startup of the app or can be manually triggered via the "Check for Updates" button in the About screen.
- Highlights: A new "What's New" popup shows you the most important changes after an update.
- Changelog: The full history of changes is now accessible directly from the About screen.
