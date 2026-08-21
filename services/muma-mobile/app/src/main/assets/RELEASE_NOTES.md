## [Unreleased]

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
