# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Memories op web is een fotoboek geworden.** In plaats van één lange pagina met alle jaren onder
  elkaar staat er nu een tegel per jaar: een mozaïek van de hoezen van dat jaar, het jaartal groot
  eroverheen, en daaronder de drie nummers die je er het meest mee hebt. Wat "het meest" is leidt de
  app af uit wat er al bekend is — vijf sterren gaat voor, en binnen én buiten die groep bepaalt het
  aantal beluisteringen de volgorde. Klik je op een tegel, dan krijgt dat jaar een eigen pagina op
  `/memories/2025` met de gewone tracklijst, vijftig nummers tegelijk en een knop om er vijftig bij
  te laden. De afspeelknop start het hele jaar, niet alleen wat er op dat moment staat. Zo'n adres
  is te bewaren en werkt na een refresh, met dit voorbehoud dat bij memories hoort: ze hangen aan de
  dag, dus morgen staan er andere nummers onder hetzelfde jaartal — of geen, en dat zegt de pagina
  dan zelf.

### Fixed
- **De label-backfill eindigde er netjes uit terwijl hij bestanden had overgeslagen.** Hij sloot af
  met een regel als `{'written': 412}`, en wat de schijf geweigerd had stond alleen als waarschuwing
  ergens halverwege een log van uren. Hij zegt nu hardop hoeveel bestanden niet geschreven konden
  worden, per label, met een paar paden erbij. Dat is geen fout van de backfill: op een steekproef
  van 22-08-2026 blijkt ongeveer één op de zes bestanden onder de EPs-map prima te lezen en elke
  schrijfpoging te weigeren, verspreid over mappen uit 2019 tot en met dit jaar. Die schade stond er
  al; de backfill is alleen het eerste dat hem hardop telt.

## [0.24.0] - 2026-08-22

### Added
- **De keten-test dekt nu vijf verhalen in plaats van één.** Naast het nummer dat gescand, gevonden,
  afgespeeld en als luisterbeurt vastgelegd wordt, staan er nu ook uitgeschreven: een luisterbeurt
  voor iets dat de bibliotheek niet heeft (die hoort bewaard te blijven en níet als treffer gemeld —
  dat is de tak waar het gros van de ingelezen geschiedenis in terechtkomt), een ster die in de
  speler wordt gezet en bij de bibliotheek moet aankomen aan het júiste nummer, een genre-tag die een
  te cureren genre wordt, en de vraag of de deur eigenlijk wel dicht zit. Dat laatste was een blinde
  vlek: alle andere scenario's melden zich netjes aan, dus als de sleutelcontrole zou wegvallen bleef
  de hele reeks groen.
- **En er staat nu een test op de fout die 887 sterren kostte.** Ratings hangen aan het kenmerk van
  een nummer, niet aan zijn pad, dus alles wat een bestand een nieuw kenmerk geeft maakt stilzwijgend
  los wat eraan hing — de nummers stonden er nog, er ging niets stuk, de sterren waren alleen weg.
  Dezelfde sleutel draagt ook de audiokenmerken. De test zet een ster, laat het bestand daarna
  helemaal opnieuw inlezen, en controleert dat het kenmerk hetzelfde bleef, dat de ster nog steeds
  bij het nummer te vinden is, en dat de bibliotheek er geen tweede kopie bij heeft gekregen.
- **De keten-test staat nu uitgeschreven in gewone zinnen.** De drie stappen — scannen, opvragen via
  Subsonic, een luisterbeurt registreren — staan in `tests/bdd/features/scan_to_listen.feature`, met
  de code eronder. Dat is niet alleen mooier lezen: de plekken waar de test minder dekt dan zijn naam
  belooft staan nu tússen de stappen, in hetzelfde stuk tekst als de beloftes, in plaats van in een
  codecommentaar dat je alleen ziet als je het bestand opent. De oude schrijfwijze is weg — twee
  versies van dezelfde keten betekent ze voor altijd gelijk houden. De taak duurt drie seconden
  langer, omdat de testrunners de benodigde uitbreiding niet hebben en die in een wegwerpcontainer
  wordt geïnstalleerd.
- **De keten-test speelt het nummer nu ook echt af.** Tot nu toe bewees hij dat een bestand
  gevonden kon worden, niet dat het beluisterd kon worden — de laatste schakel waar de test naar
  vernoemd is ontbrak dus. Hij haalt het nummer nu op bij de muziekserver en controleert twee
  dingen. Het bestand komt byte voor byte terug, even groot als de server zelf opgeeft: dat sluit uit
  dat het onderweg is omgezet, want een omgezette stroom is nog steeds geluid en nog steeds een
  geslaagd antwoord, alleen niet meer het bestand dat gescand werd. En er kan een losse byte uit het
  midden opgevraagd worden, wat een speler doet zodra je in een nummer springt; dat loopt via andere
  code dan een heel bestand ophalen, en een server die het stilzwijgend negeert stuurt gewoon alles
  terug en lijkt daarmee in orde.

### Fixed
- **Een release die een kopie van zijn eigen map meelevert kreeg die map als platenlabel.** De tagger
  telde vanaf het bestand twee mappen omhoog om het label te vinden. Bij scene-releases die hun eigen
  map nóg een keer bevatten staat het nummer een niveau dieper, en dan is die twee-omhoog niet
  `ABSLT Records` maar `ABSLT065 - Hartshorn_-_LOSE_CTRL-(ABSLT065)-SINGLE-WEB-2026-SRG`. Dat kwam
  zo in het label, het catalogusnummer én de copyright terecht, en daarmee ook in de bibliotheek: het
  label bestaat dan één keer voor die ene release. De tagger rekent nu vanaf de EPs-map naar beneden
  — de eerste map daaronder is het label, de tweede de release — zodat het niet meer uitmaakt hoe
  diep het bestand eronder staat. Paden buiten de EPs-map, waar de importer mee werkt, blijven de
  oude telling gebruiken. Voor de nummers die al fout getagd zijn is er
  `scripts/backfill_label_from_path.py`, die alleen bijwerkt wat aantoonbaar de eigen releasemap als
  label draagt en een met de hand gezet label met rust laat.
- **De keten-test controleerde niet wat hij leek te controleren.** De stap die opvraagt of de
  muziekserver het nummer terugvindt, keek alleen of er antwoord kwam. Subsonic verpakt fouten in een
  geslaagd antwoord, en de gebruiker waarmee gevraagd werd bestond helemaal niet — dus de test slaagde
  al die tijd op *"Wrong username or password"*. De teststack maakt nu eerst een gebruiker aan, wacht
  tot die bij de muziekserver is aangekomen, meldt de muziekmap aan en laat die scannen. Pas daarna
  loopt de test, en die controleert nu of het nummer echt in het antwoord staat. Dat kost ongeveer
  vier seconden extra en dekt de helft van de keten die tot nu toe alleen op papier gedekt was.

### Changed
- **De keten-test draait nu bij elke wijziging in plaats van op verzoek.** Hij stond op handmatig
  omdat een volledige stack duur leek: images bouwen, drie containers, een database. Gemeten loopt
  hij tussen de 45 en 80 seconden, waarvan bijna alles wachten is tot de containers opgestart zijn;
  de test zelf duurt twee seconden. Een test die de enige is die de hele keten bewijst en die pas
  draait als iemand eraan denkt, bewijst in de praktijk niets, dus hij draait nu overal mee en houdt
  de pipeline tegen als hij rood is. Hij heet ook niet langer `e2e:golden-path` maar
  `e2e:scan-to-listen`, want dat is wat hij doet. Wat hij nog steeds niet doet is de luisterbeurt uit
  de geschiedenis teruglezen — dat komt uit het antwoord op de registratie zelf — en dat staat er nu
  ook zo bij.

## [0.23.1] - 2026-08-22

### Fixed
- **De app ging uit zodra je in de auto stapte.** MuMa openen terwijl de auto verbonden was sloot
  hem meteen weer af, terwijl dezelfde versie zonder autoverbinding gewoon opende en het scherm in
  de auto ondertussen bleef werken. De autostand vroeg aan de speler of er iets speelde — dat
  bepaalt of hij zelf naar voren komt of alleen een melding achterlaat — en stelde die vraag vanaf
  een plek in de app waar de speler niet bestaat: die hoort bij het hoofdscherm, niet bij de app als
  geheel. De vraag valt alleen op het moment dat de auto voor het eerst wordt gezien, en daarom was
  er niets aan de hand tot je instapte, en bleef het scherm in de auto — dat langs een heel andere
  weg bediend wordt — ongemoeid. Het hoofdscherm levert het antwoord nu zelf aan, dus er valt niets
  meer op te zoeken.

## [0.23.0] - 2026-08-21

### Added
- **Er is een eerste echte keten-test.** Alle bestaande tests bewijzen één onderdeel: dat LMS
  antwoordt in de vorm die de server verwacht, dat de database de query slikt, dat een functie doet
  wat hij belooft. Geen ervan bewijst dat een bestand dat op schijf verschijnt uiteindelijk een
  beluisterd nummer wordt. `e2e:golden-path` doet dat wel: hij zet de teststack op, legt er een
  nummer in, laat het scannen, zoekt het op via dezelfde Subsonic-route die de telefoon gebruikt,
  registreert een luisterbeurt en leest die weer terug. Handmatig te starten en dat blijft zo — hij
  bouwt images en houdt een stack minutenlang bezig, en niets wacht op zijn uitkomst.
- **De zoekbalk in de Android-app begrijpt nu ook een verzoek.** Wat je hardop kunt vragen —
  "speel willekeurig uptempo hardcore uit 2021 af" — leverde getypt een letterlijke zoektocht naar
  die hele zin op, en dus niets. Dezelfde ontleding die de auto en de microfoon gebruiken staat nu
  ook achter de zoekbalk, met dezelfde uitkomst. Eén woord wordt nooit ontleed: dat is verreweg de
  meeste zoekopdrachten en het minst waarschijnlijk een verzoek, en een zoektocht naar de band
  Editors hoort geen "alles met edit" op te leveren. Wordt er wél iets als verzoek gelezen, dan zegt
  de app dat, met een knop ernaast om alsnog op tekst te zoeken. En er is een tegel voor de snelle
  instellingen die het spraakscherm opent: twee vegen vanaf waar je ook bent, in plaats van
  ontgrendelen, app zoeken en wachten. Vanaf een vergrendeld scherm vraagt hij eerst om ontgrendelen.

### Changed
- **De statische analyse van de Android-code draaide nergens.** detekt zat al in de build, maar
  alleen achter een vlag die geen enkele taak meezond — dus faalde er nooit iets en merkte niemand
  het. Hij draait nu mee in de Android-controle. De vierenzeventig bevindingen die er al stonden
  zijn per module vastgelegd in een baseline in plaats van in één ruk gerepareerd: een controle die
  rood is op de dag dat je hem aanzet leert iedereen hem te negeren. Nieuwe bevindingen laten de
  taak wel vallen. De enige bevinding in code van vandaag is verholpen in plaats van vastgelegd.
- **De API accepteert niet langer verzoeken vanaf elke website.** Hij stond open voor iedere
  herkomst, met elke methode en elke header. Dat is op zichzelf geen manier om langs de
  authenticatie te komen — een browser stuurt niets mee en een aanroeper heeft de sleutel al nodig
  — maar het liet wel elke pagina die je opent de onbeveiligde eindpunten binnen dit netwerk
  uitlezen. Voortaan geldt een lijst, in te stellen met `MUMA_CORS_ORIGINS`; staat die niet
  ingesteld, dan blijven alleen de ontwikkelaanroepen over. De webinterface wordt door de
  LMS-server uitgeserveerd en praat dus met dezelfde herkomst, en de Android-app is geen browser,
  dus die merken er niets van. Blijkt er tóch een browserclient te zijn die het nodig heeft, dan
  zet `MUMA_CORS_ORIGINS=*` het oude gedrag terug zonder nieuwe uitrol.
- **Containers kunnen zichzelf geen extra rechten meer geven.** Alle zesenveertig services in de
  compose-bestanden draaien nu met `no-new-privileges`, wat een proces binnen een container belet
  via een setuid-programma meer te mogen dan het kreeg. Het kan niets breken dat nu werkt. Dat de
  containers als root en met een schrijfbaar bestandssysteem draaien blijft staan als vastgelegd
  openstaand punt: dat valt pas bij een uitrol om, en niet te testen zonder productie.
- **Afhankelijkheden wachten voortaan drie dagen voor ze worden voorgesteld.** Een versie die
  minuten geleden is gepubliceerd kan alsnog worden ingetrokken of besmet blijken, en dit project
  voegt een aantal ervan automatisch samen. Beveiligingswaarschuwingen wachten niet, en `yt-dlp`
  ook niet: achterlopen op dat pakket is precies wat downloaden stukmaakt. Tegelijk zijn de
  GitHub-workflows van de Android-app verwijderd — die kwamen mee uit het Ultrasonic-verleden,
  draaiden nergens, want dit is een GitLab-repo zonder GitHub-remote.
- **De pijplijn scant de code nu ook op bekende kwetsbare patronen.** `security:sast` draait
  semgrep over de hele boom. De tweehonderdtweeëndertig meldingen die er vandaag al staan zijn
  stuk voor stuk beoordeeld en vastgelegd in `security/accepted-sast-findings.txt`, met per regel
  de reden waarom ze blijven staan — de taak is daardoor groen vandaag en wordt alleen rood van
  iets nieuws, wat de enige manier is waarop een scanner gelezen blijft worden. Een tweede
  identieke regel op dezelfde plek telt als nieuw: "dat doen we elders ook al" dekt geen nieuwe
  code. Onder de beoordeelde meldingen zitten geen gelekte sleutels; wel drie punten die blijven
  staan als openstaand werk, namelijk dat de API elke herkomst toelaat (`allow_origins=['*']`),
  dat de containers als root en met een schrijfbaar bestandssysteem draaien, en dat de
  Android-app nog dode GitHub-CI-bestanden uit het Ultrasonic-verleden meedraagt.
- **De pijplijn controleert nu ook de shellscripts.** Drieënzestig scripts sturen het uitrollen,
  het taggen en elke testronde aan, en geen enkele taak keek er ooit naar — een fout erin bleek pas
  op het moment dat een uitrol hem uitvoerde. `quality:shellcheck` draait er shellcheck overheen bij
  elke wijziging aan een `.sh`-bestand. De lat ligt voorlopig op fouten, niet op waarschuwingen: er
  staan er tweeëndertig van de tweede soort open, en een controle die rood is op de dag dat je hem
  toevoegt leert iedereen hem te negeren. De ene echte fout die er stond is meteen verholpen — het
  installatiescript van de Android-app vergeleek een lijst met apps als één samengeplakte tekst,
  waardoor een naam die toevallig in een andere naam zat als geldig doorging.

## [0.22.1] - 2026-08-21

### Fixed
- **De Android-app startte niet meer op.** Versie 6.21.0 crashte meteen bij het openen, zodra het
  startscherm de eerste bewaarde kaart wilde tekenen. De nieuwe opslag van die kaarten liet de
  omzetter het type van de lijst uit de veldbeschrijving afleiden, en juist die beschrijving haalt
  de verkleiner uit een uitgavebouw weg — waardoor er losse gegevensbrokken terugkwamen in plaats
  van kaarten. In een ontwikkelbouw en in alle tests gebeurde dat niet, want daar wordt niet
  verkleind. De opslag geeft het type nu expliciet mee, precies zoals de al jaren werkende
  snelkoppelingenlijst dat doet, en een bewaarde regel die niet als kaart te lezen is telt als
  ontbrekend. Wie 6.21.0 draaide hoeft niets te wissen: de oude regels worden vanzelf overschreven.
- **Twee derde van je luistergeschiedenis was onvindbaar voor de rest van MuMa.** Een beluisterd
  nummer werd aan een track gekoppeld door de artiestnaam en de titel letterlijk te vergelijken.
  Op 16.830 gekoppelde luisterbeurten stonden er 35.761 in een tabel die niemand meer las, en het
  verlies zit vrijwel helemaal in geïmporteerde geschiedenis: wat live uit LMS binnenkomt verliest
  zes procent, de ListenBrainz-import drieënzeventig. Dezelfde muziek, andere spelling. Er is nu
  een ladder van vier stappen — letterlijk, genormaliseerd, zonder remix-achtervoegsel, en als
  laatste een gelijkenisdrempel — en per koppeling wordt vastgelegd welke stap hem maakte en hoe
  zeker die was. Elke stap is los uit te zetten en wat een stap koppelde is met één opdracht terug
  te draaien, want de laatste twee kunnen een luisterbeurt aan de verkeerde track hangen. Een
  achtergrondtaak probeert de overgebleven rijen periodiek opnieuw, met een oplopend wachtvenster,
  zodat een nieuwe download een luisterbeurt uit 2019 alsnog kan koppelen zonder dat de taak elke
  ronde dezelfde kansloze rijen doorploegt.
- **De geanalyseerde audiokenmerken hoorden bij niets wat je ooit gedraaid hebt.** Er staan
  90.107 rijen met tempo en klankkenmerken in de database, en elke functie die erop leunt las nul
  procent dekking — het zag eruit alsof de analyzer nooit gelopen had. De sleutel bleek iets anders
  te zijn dan waarvoor hij werd aangezien: de kenmerkentabel is gesleuteld op een hash van het
  bestandspad, terwijl de lezers hem vergeleken met de track-identificatie van de scanner. Dat matcht
  vrijwel nooit. Dat sommige rijen tóch aansloten hield het verborgen: de analyzer maakt zelf
  tracks aan waarvan de identificatie wél die pad-hash is, en juist díe tracks speelt niemand af.
  De lezers gebruiken nu de echte verwijzing, en een migratie herstelt die verwijzing voor de
  bestaande rijen langs beide routes die nog oplossen — ook waar er een verkeerde waarde stond, wat
  het oude migratiescript liet liggen omdat het alleen lege waarden vulde.



## [0.22.0] - 2026-08-21

### Added
- **De Android-app heeft een rijstand.** Alles wat de telefoon in een houder moet kunnen — wat er
  speelt, spoelen, waarderen, drie plekken waar je vaak heen gaat, en de microfoon — staat op één
  scherm met knoppen op armlengte. De app merkt de auto zelf op: een head unit, een
  bluetooth-apparaat dat jij als auto hebt aangevinkt, of een schakelaar in de instellingen.
  Speelt er al muziek, dan komt het scherm naar voren; anders krijg je een melding die je aantikt.
  Dat onderscheid is er omdat Android sinds versie 14 alleen bel- en wekker-apps ongevraagd een
  scherm laat openen — waar dat recht ontbreekt wordt het vanzelf een melding, en één regel in de
  instellingen brengt je naar de systeempagina als je het toch wilt. Wegdrukken is definitief
  zolang de auto verbonden blijft, en zodra die verbinding wegvalt sluit de rijstand zichzelf.
  Oordopjes tellen nooit mee: welke apparaten je auto zijn kies je zelf, want de apparaatklasse
  liegt beide kanten op.
- **De Android-app opent op wat er de vorige keer stond, in plaats van op skeletten.** Elke koude
  start liet het startscherm en de bladerschermen (genres, jaren, labels, festivals, line-ups)
  pulserende plaatshouders tonen terwijl de server opnieuw werd bevraagd om gegevens die sinds de
  vorige keer bijna nooit veranderd waren. De caches die er al waren leefden alleen in het geheugen
  en gingen dus met het proces mee dood. De kaarten die een sectie of een bladerscherm laat zien
  worden nu op schijf bewaard en meteen weer neergezet, met een dunne voortgangsbalk onder de kop
  zolang de verse kopie onderweg is; de kaarten zelf zijn direct aantikbaar. Mislukt het verversen,
  dan blijven de kaarten staan en stopt de balk. Een lege sectie wist zijn eigen bewaarde kopie, en
  een andere server of de Sets-schakelaar is een misser in plaats van een verkeerd antwoord.

### Fixed
- **Een dynamische afspeellijst kwam bijna leeg terug.** Een lijst als "Hardstyle" die om 500
  nummers vroeg leverde er een handvol, wat eruitzag alsof de bibliotheek gewoon weinig hardstyle
  bevatte. De waarderingsfilter stond echter altijd in de query, ook op zijn standaardwaarde 0 tot
  100 — bedoeld als "geen filter". Waarderingen komen binnen via een LEFT JOIN, dus een nummer
  zonder waardering heeft er geen, en niets is nooit groter dan nul: daarmee viel elk ongewaardeerd
  nummer af. Dat zijn er 301.340 van de 302.561. Een bereik dat de hele schaal beslaat bouwt nu geen
  filter meer op; vraag je wel om vier sterren en hoger, dan blijven ongewaardeerde nummers er
  gewoon buiten.
- **Sterren geven vanuit de auto werkt weer op een nummer dat al sterren had.** Een waardering die
  op het spelende item werd gezet, ging naar de cache van de track en naar de extras van het
  media-item, maar datzelfde item draagt de waardering nog een tweede keer als `StarRating`. Die
  wordt bij het bouwen van het item vastgelegd en is daarna onbereikbaar, want `MediaMetadata` is
  onveranderlijk. De trackcache bewaart een item tien minuten, korter in een wachtrij voorbij de 250
  items, en elke herbouw daarna liet de bevroren kopie winnen. De knop werd dan getekend met de
  waardering van het moment waarop de wachtrij werd gebouwd, waardoor de volgende tik uitkwam op de
  waardering die net gezet was en `RatingManager` die als dubbel weggooide: de knop reageerde niet
  meer, en een nummer dat op vijf sterren stond sprong terug naar geen in plaats van door te tellen.
  Een herbouw leest nu de extras; de `StarRating` is alleen nog de terugval voor items die zelf geen
  extras-waarde hebben.
- **Een waardering bereikt nu elke bewaarde kopie van het nummer, niet alleen de server.**
  `setRating` stuurde de nieuwe waardering door en verder niets, dus de kopieën waaruit de app
  antwoordt — het album waarin gerate werd, de lijsten op het startscherm, de bladerboom in de auto
  — hielden de waardering waarmee ze waren opgehaald tot hun cache verliep. Terugkomen bij een
  nummer liet het oude getal zien, wat leest als een waardering die is gewist. Die kopieën worden nu
  ter plekke bijgewerkt, en het bewaarde media-item, waarvan de metadata niet bij te werken is,
  wordt weggegooid zodat het bij de volgende leesbeurt met de nieuwe waardering wordt herbouwd.

## [0.21.1] - 2026-08-21

### Changed
- **Android-builds worden gepubliceerd onder de eigen naam van de app.** Elke APK ging nog steeds
  omhoog als `ultrasonic-*`: apk-hoster groepeert builds op het voorvoegsel van de bestandsnaam, en
  precies dat voorvoegsel vraagt een geïnstalleerde app op bij het controleren op updates — het
  hernoemen op zichzelf zou elke telefoon voorgoed "je bent bij" hebben verteld. Uploads heten nu
  `muma-mobile-*` en de updatecontrole vraagt om die reeks; oudere installaties die nog om
  `ultrasonic` vragen worden er door apk-hoster naartoe gewezen via de nieuwe instelling
  `APK_ALIASES`, die daar is ingesteld. Ook het account waarmee een build bij apk-hoster inlogt is
  meeverhuisd, van `ultrasonic` naar `muma-mobile`; het oude account blijft staan voor builds die
  al geïnstalleerd zijn.

## [0.21.0] - 2026-08-21

### Added
- **Een instelwizard in de Android-app die na een update laat zien wat er veranderd is.**
  Tweeënzestig instellingen staan op één doorlopend scherm, en niets daarop zegt welke er vorige
  week bij kwamen. De wizard loopt er negen één voor één langs — server, stijl, app-icoon,
  interfacegrootte, herinneringen op het startscherm, offline opslag, alleen downloaden op wifi,
  de balk met wat er speelt, en MuMa-synchronisatie — elk met uitleg én de knop zelf, zodat een
  instelling te wijzigen is op de plek waar hij wordt uitgelegd. Instellingen die nieuw zijn sinds
  de versie waar je vandaan komt krijgen het label Nieuw en komen vooraan, waardoor een update-ronde
  kort blijft. De wizard staat ook altijd in het overloopmenu, en een update die geen instellingen
  toevoegt toont gewoon de changelog zoals voorheen.
- **De Android-app heeft nu een handleiding aan boord, onder Help in het overloopmenu.** Alles
  wat MuMa kan was tot nu toe alleen te ontdekken door overal op te drukken: de Sets-schakelaar,
  waar de twaalf bibliotheektabbladen voor zijn, dat één gesproken zin tegelijk een genre, een
  jaar en een waardering mag dragen, en dat de app zichzelf buiten de Play Store om bijwerkt.
  Help is twaalf hoofdstukken in leesvolgorde, dichtgeklapt tot je er één opent, elk met een
  schermafbeelding die je kunt vergroten en, waar lezen de langzaamste manier is om het te
  leren, een knop rechtstreeks naar het scherm dat beschreven wordt. De schermafbeeldingen zijn
  voorlopig plaatshouders: een echte zet je erin door een PNG over het gelijknamige bestand in
  `app/src/main/res/drawable-nodpi` te zetten, en `docs/manual-screenshots.md` vertelt welke
  opname waar hoort.

### Changed
- **Het Over-scherm verwijst niet meer naar sites die er niet meer bij horen.** "Website openen"
  en "Bug melden" stuurden je de app uit naar adressen die niets met deze installatie te maken
  hebben; beide knoppen zijn weg, zodat alleen bijwerken, de wijzigingslijst en het logboek
  overblijven. Dezelfde opruiming liep door de rest van de tekst: de vertaalde Over-tekst
  beschreef in negen talen nog het oude Ultrasonic-product en de bijbehorende Subsonic-servers,
  en is vervangen door de Nederlandse en Engelse MuMa-tekst die er al stond. Waar de oude
  productnaam nog in een vertaling stond — het welkomstscherm, de crashmelding, de
  versiewaarschuwing — staat nu MuMa. In het beheerscherm heet de app bij de sleuteluitleg
  voortaan MuMa Mobile, en het bijdragedocument van de app wijst naar de eigen issuetracker in
  plaats van naar het opgeheven Ultrasonic-project.
- **Een wijziging aan een Dockerfile draaide geen enkele taak.** Zes van de zeven images werden
  pas voor het eerst gebouwd op een release-tak, minuten voor de uitrol — de duurste plek om
  te ontdekken dat er iets niet compileert. Een merge request die een Dockerfile raakt bouwt ze
  nu allemaal, zonder ze te publiceren, en start daarnaast de teststack op om te zien of hij
  gezond bovenkomt.
- **De pijplijn wacht niet meer op werk waar niets van afhangt.** De integratie- en
  browsertaken stonden achter de Android-controle omdat ze toevallig in een latere fase zaten;
  op de 0.19.0-pijplijn was dat zevenendertig minuten wachten op een uitkomst die geen van
  drieën gebruikt. Ze noemen nu zelf waar ze op wachten. Het taggen op master wacht om dezelfde
  reden niet langer op een testronde die de release-tak al gedraaid heeft.
- **Kleiner onderhoud aan de pijplijn.** De Android-controle mag nog twintig minuten duren in
  plaats van vijfenveertig, nu gelijktijdige Android-taken elkaar niet meer uithongeren; de
  dekkingsrapporten van de frontend- en servertests worden ook bewaard als die test faalt,
  precies de keer dat je ze wil lezen; en de foutopsporingsregels die elke Python-testronde
  begonnen met hostnaam, IP-adres en gebruikersnaam zijn weg.

### Fixed
- **Een uitgerolde release-tak wordt nu altijd opgeruimd, ook als er iets misging.** Het
  verwijderen van de zojuist samengevoegde `release/*`-tak hing achteraan het terugsamenvoegen
  naar develop, en erfde daarmee twee voorwaarden die er niets mee te maken hebben: dat script
  stopt er vroegtijdig mee zodra develop de commit al bevat — zo hield `release/0.8.3` zijn tak —
  en sinds de nieuwe versiecontrole hing het er ook van af of productie wel draait wat master
  zegt. Juist het geval dat die controle moet vangen liet dus een samengevoegde release-tak op
  de server achter, en dat is precies de opzet waarin een later opnieuw gestarte pijplijn oude
  images als `latest` publiceert en terugrolt (bugrapport 016). Het opruimen is nu een eigen taak
  die nergens op wacht: een tak die al in master zit weggooien is veilig, wat de tag of de uitrol
  ook deden.
- **Een uitrol die stukliep meldde zichzelf als geslaagd.** De laatste stap van de uitrol
  vroeg de productieserver netjes welke containers er draaiden, drukte dat af, en keek er
  vervolgens niet naar: `docker ps` eindigt succesvol, ook als het een container laat zien die
  elke seconde opnieuw crasht, en ook als het helemaal niets laat zien. Elke storing van het
  afgelopen halfjaar zag er daardoor uit als een groene uitrol. Die stap controleert nu echt:
  geen container in een herstartlus of met een falende gezondheidscontrole, en `/health` moet
  binnen drie minuten antwoorden met status ok én met de versie die zojuist is uitgerold. De
  container die één keer draait en daarna bewust stopt wordt herkend aan zijn herstartbeleid en
  niet langer als storing geteld.
- **Een release kon een merkteken krijgen zonder ooit uitgerold te zijn.** 0.19.0 stond een dag
  lang getagd op master terwijl productie op 0.18.2 bleef staan: de uitrol was *overgeslagen*,
  en een overgeslagen taak houdt niets tegen. Voor het taggen wordt nu aan productie zelf
  gevraagd welke versie er draait, en komt die niet overeen, dan gebeurt er niets.

## [0.20.0] - 2026-08-21

### Added
- **Het nieuws van het uur, ook onderweg.** MuMa neemt het bulletin nu zelf op van de live
  stream van NPO Radio 1 — geen enkele feed publiceert het NOS-radiobulletin op afroep, dus
  meeluisteren en bewaren is de enige route. Elk heel uur wordt tien minuten getapt, de laatste
  twaalf opnames blijven staan, en een opname die korter is dan een minuut wordt weggegooid in
  plaats van bewaard: een afgekapt bulletin in de auto is erger dan geen bulletin. In Android
  Auto staat er een Nieuws-map naast Radio en een nieuwsknop bij de bediening: één tik legt de
  wachtrij vast, speelt het bulletin, en zet daarna de muziek terug op de seconde waar je was.
  Radio is de uitzondering, want die tijdlijn is van de server: dat kanaal wordt na het nieuws
  opnieuw afgestemd. De webspeler doet hetzelfde, en het beheerscherm kreeg een Nieuws-tab met
  bron, schema, bewaartermijn en een knop om meteen op te nemen.

### Changed
- **De Android-app bouwt nu in seconden in plaats van soms een uur.** De pijplijn gaf elke
  gelijktijdige taak zijn eigen Gradle-map, dus de eerste bouw op een verse plek haalde alle
  afhankelijkheden opnieuw op en begon zonder cache: dezelfde controle die warm drie minuten
  duurde liep dan vijftig tot negentig minuten en sloeg tegen de tijdslimiet aan. De
  mobiele taken draaien nu gegarandeerd één voor één en delen daardoor veilig één warme
  Gradle-map. Daar bovenop verdwenen twee dingen die de app nooit gebruikte maar wel elke bouw
  betaalde: de kapt-annotatieverwerker, waarvoor geen enkele verwerker meer bestond sinds Room
  op KSP overging, en DataBinding, dat in geen van de 78 layouts voorkwam. Zonder DataBinding
  kon ook de configuratiecache aan. Een verse checkout met warme cache doet de testronde nu in
  twaalf seconden.

## [0.19.0] - 2026-08-20

### Fixed
- **Een genre hardop vragen vindt het nu ook als de telefoon er één woord van verkeerd verstaat.**
  "Uptempo hardcore" leverde het brede genre Hardcore op, of helemaal niets, vaak genoeg om spraak
  niet de moeite waard te maken. Er waren drie dingen tegelijk mis. De spraakherkenning had nooit
  te horen gekregen welke genres deze bibliotheek bevat, dus die antwoordde met het gewone
  Nederlands dat er het dichtst bij lag — hij krijgt nu de genres met de meeste muziek mee voordat
  hij begint te luisteren. Een naam die net verkeerd terugkwam was daarna niet te redden: een
  genre waarvan alle woorden op één na kloppen kwam nergens exact overeen en viel dan terug op het
  genre dat er toevallig in zat. "Temple hardcore" bevat "hardcore", dus een verzoek om het ene
  genre antwoordde met alles wat onder het andere valt. Zo'n naam wordt nu gelezen als het genre
  waar hij op lijkt, mits de rest exact overeenkomt en het om een van de grote genres gaat. En
  waar de bibliotheek één genre op meerdere manieren spelt wint nu de spelling waar de muziek in
  zit, in plaats van degene die de server toevallig het eerst noemde.

### Added
- **Android Auto toont nu een zoekknop binnen MuMa.** De app gaf nooit aan dat er gezocht kon
  worden, dus verborg de auto zijn eigen zoekknop en was de globale zoekbalk van de auto de enige
  ingang. Zoeken vanuit MuMa gebruikt dezelfde spraakparser als al het andere.

## [0.18.2] - 2026-08-20

### Fixed
- **Een uitgesproken genre vindt nu al zijn muziek, niet toevallig de spelling die de server het
  eerst noemt.** Om hardstyle vragen leverde helemaal niets op, terwijl de zin correct begrepen
  was en de bibliotheek twintigduizend hardstyle-nummers bevat. De bibliotheek bewaart een genre
  onder elke schrijfwijze die ooit in een tag stond — "Hardstyle", "HARDSTYLE" en "hardstyle"
  zijn drie losse ingangen — en MuMa hield degene die als eerste terugkwam. Dat bleek een
  restant met vier lange mixen, dus een verzoek om nummers vond er daar geen één van. Een
  uitgesproken genre draagt nu élke schrijfwijze die de bibliotheek ervan heeft. Een genre dat
  het uitgesproken genre alleen maar bevat, zoals "Mainstream Hardstyle", blijft er buiten.

## [0.18.1] - 2026-08-20

### Fixed
- **MuMa Voice sluit de app niet langer af zodra hij iets gevonden heeft om te spelen.** Het
  scherm las de zin, doorzocht de bibliotheek en klapte er dan op de allerlaatste stap uit — wat
  eruitzag alsof de zoekopdracht mislukt was terwijl die juist geslaagd was. De speler hoort bij
  het scherm dat hem draagt en dit scherm vroeg hem op de verkeerde plek op; omdat die vraag pas
  gesteld wordt als er echt muziek te starten valt, leek alles daarvoor in orde.

## [0.18.0] - 2026-08-20

### Added
- **MuMa Voice: een microfoonknop in de mobiele app, op dezelfde pijplijn als de auto.** Tik op
  de microfoon in de werkbalk en zeg wat er moet spelen. De tekst gaat door precies dezelfde
  parser en zoekmachine die Android Auto gebruikt, dus een zin die daar werkt werkt hier ook.
  De spraakherkenner geeft meerdere lezingen van dezelfde zin terug en MuMa probeert ze op
  volgorde — dat is wat "hard style" alsnog op "hardstyle" laat uitkomen. Op hetzelfde scherm
  staat een tekstveld om een formulering uit te proberen zonder te praten.
- **Een vraag in plaats van een gok, als een naam meer dan één ding kan zijn.** "Speel
  Thunderdome" kan het label, het album of de playlist zijn. MuMa Voice laat de mogelijkheden
  zien en vraagt welke je bedoelde; het antwoord kun je aantikken of inspreken ("het label").
  Android Auto kan niets vragen — een mediasessie heeft geen weg terug — dus daar wordt de
  sterkste lezing gekozen en worden de afgewezen lezingen vastgelegd.
- **Albums, playlists, titels en sterren kunnen nu uitgesproken worden.** "Speel album
  Thunderdome af", "speel de afspeellijst zomer af", "speel het nummer dragonborn af", "speel
  hardstyle met minstens 4 sterren af". Twee waarden van dezelfde soort kan ook: "speel
  hardstyle en hardcore af" is één zoekopdracht, terwijl "drum and bass" één genre blijft.
- **Voice diagnostics, onder Over.** Elke spraakopdracht laat nu een volledig spoor achter: via
  welke callback hij binnenkwam, de zoekopdracht precies zoals ontvangen, élke extra die Android
  meestuurde, de tokens, welke parserregel welk woord opeiste, wat de bibliotheek over elke term
  zei, en het verzoek dat er uiteindelijk uitging. De laatste vijftig worden bewaard en zijn als
  tekst te delen. Hiermee is te achterhalen wat Google herschrijft vóór MuMa iets ziet.

### Fixed
- **Een uitgesproken titel wordt op de titel gezocht, niet op de hele zin.** Als geen enkel
  filter matchte kreeg de terugvalzoekopdracht de hele uiting mee, dus "speel het nummer
  dragonborn af" zocht letterlijk daarnaar en vond niets. Hij zoekt nu op "dragonborn".
- **Een uitgesproken sterrenfilter sleept niet langer elke ongewaardeerde track mee.** De server
  verbreedt een losse minimumwaardering tot alles wat niemand ooit beoordeeld heeft, dus er gaat
  nu altijd een bovengrens mee.

## [0.17.1] - 2026-08-20

### Fixed
- **De hele site gaf 504 zodra er genoeg artiestafbeeldingen tegelijk werden opgevraagd.** LMS heeft
  net zoveel HTTP-threads als de machine cores heeft, en elke aanvraag die een plaatje bij MuMa
  ophaalde hield er daar één van bezet zolang hij op antwoord wachtte. Genoeg tegels op één scherm
  en er was geen thread meer vrij: de server bleef draaien, hield zijn poort open en beantwoordde
  niets meer — een scrobble niet, een gewone ping ook niet — tot iemand hem herstartte. Die
  aanvragen wachten nu naast de threads in plaats van erop. Voor de overige MuMa-calls, die de
  statuscode van MuMa letterlijk moeten doorgeven en dus niet op dezelfde manier opzij kunnen, geldt
  een harde limiet: hooguit de helft van de threads mag tegelijk staan wachten.
- **Een ongeldige API-sleutel greep bij elke poging de exclusieve databaselock.** Een client die na
  een herstart met een dode sleutel bleef proberen — muma-radio doet dat elke vijf seconden — zette
  daarmee elke keer een schrijftransactie op, ook al bestond de sleutel niet. Tijdens een scan stond
  die achter de scanner in de rij. Onbekende sleutels worden nu zonder lock afgehandeld en kort
  onthouden.
- **Subsonic-sleutels overleven een herstart.** Ze stonden in een database die alleen in het
  geheugen bestond, dus elke herstart van LMS gooide ze weg. Voor een client was dat niet te
  onderscheiden van een verkeerde sleutel: die bleef eindeloos proberen met iets dat nooit meer zou
  werken. Daardoor was het herstarten van LMS ook precies wat het volgende probleem opzette.
- **Eén mislukte aanvraag legde niet langer de hele wachtrij stil.** Ging er één call naar MuMa mis,
  dan pauzeerde LMS dertig seconden lang al het uitgaande verkeer — scrobbles en ratings incluis.
  Dat gebeurt nu pas als MuMa meerdere keren achter elkaar niet reageert.
- **`getCoverArt` meldt weer de echte status.** "Geen afbeelding voor deze artiest" is een 404, maar
  kwam in het log terecht als een 502. Dat is waarom het log vol stond met gateway-fouten die nooit
  een gatewayprobleem waren.
- Een vastgelopen LMS herstart nu zichzelf in plaats van te wachten tot iemand merkt dat de site
  eruit ligt.

## [0.17.0] - 2026-08-20

### Added
- **Releases die de importer niet kan wegzetten staan nu als voorstel in het beheerscherm.** Een
  release werd overgeslagen zodra het catalogusnummer niet in de labeltabel stond, of zodra er
  helemaal geen catalogusnummer in de mapnaam zat. Die bleef dan liggen in de importmap en werd
  elke ronde opnieuw als waarschuwing gelogd, zonder dat er iets anders mee gebeurde dan een
  handmatige ingreep in de database. De importer leest nu het label uit de bestanden zelf — uit de
  labelvelden van een FLAC, het publisher-frame van een MP3, en anders uit de `.nfo` — en zet het
  als voorstel klaar onder Labelvoorstellen.
- **Eén bevestiging ruimt een heel label op.** De lijst staat gegroepeerd op voorgesteld label, dus
  je bevestigt in één keer alle releases van bijvoorbeeld Brutal Kuts in plaats van vijftien keer
  hetzelfde. Bevestig je een voorstel met catalogusnummer, dan wordt die koppeling onthouden en
  lopen alle volgende releases van dat label vanzelf door. Zit er geen catalogusnummer in, dan valt
  er niets te onthouden en wordt alleen die ene map weggezet. Het labelveld kiest uit labels die al
  bestaan, zodat een andere schrijfwijze geen tweede labelmap aanmaakt. Een voorstel dat je afwijst
  komt niet meer terug, hoe vaak de importer die map daarna ook nog tegenkomt.

## [0.16.0] - 2026-08-19

### Added
- **De uiterlijk-instelling in de mobiele app kiest nu een hele stijl in plaats van alleen een
  accentkleur.** Er stond Groen en Blauw, wat één kleurtje verwisselde en verder alles hetzelfde
  liet. Er staat nu **Spotify** en **MuMa**. Spotify is de app precies zoals hij was. MuMa houdt
  hetzelfde groen voor nummers en blauw voor sets, maar staat op een warmere, diepere
  achtergrond, scheidt rijen met een haarlijn in plaats van ze als kaartjes te laten zweven,
  dimt derde- en vierderangs tekst echt in plaats van alles hetzelfde grijs te geven, rondt
  hoeken strakker af, dimt de veldlabels in plaats van ze groen te kleuren en kleurt een
  ingevulde ster goud. Spotify blijft de standaard, dus er verandert niets tot je zelf wisselt,
  en wisselen werkt meteen. Het blauwe accent vervalt; het blauwe app-icoon is een aparte
  instelling en blijft gewoon staan.

### Fixed
- **Een geselecteerde regel in de mobiele app verspringt niet meer van vorm.** De geselecteerde
  achtergrond was op 8dp afgerond en de gewone op 16dp, dus een regel klapte zichtbaar om zodra
  je hem aantikte.
- **Het uitklapvak in de mobiele app is geen witte balk met onleesbare tekst meer.** Het was nog
  geschilderd voor een lichte modus die de app al sinds ver voor de rebrand niet meer heeft:
  witte vulling, grijze rand en zwarte tekst, op een zwart scherm.

## [0.15.0] - 2026-08-19

### Added
- **Weekpakketten met meerdere releases worden nu vanzelf uitgepakt tot op de release.** Zet je
  een weekpakket zoals `HHC-2026-WEEK-33.rar` in de importmap, dan blijft na het uitpakken de
  map van het pakket zelf staan met alle releases daarin. De importer keek alleen naar de
  bovenste laag, zag daar geen catalogusnummer in en logde "No valid CAT ID found", waarna geen
  van de releases eronder ooit is opgepakt. Er zit nu een stap tussen die de releases uit de
  pakketmap omhoog haalt, zodat ze precies zo verwerkt worden als een losse download. De pakketmap
  verdwijnt daarna, met de losse `.nfo`- en `.sfv`-bestanden erin. Bestaat een release al in de
  importmap, dan blijft die staan en wordt er niets overschreven. Een album waarvan de nummers in
  één submap staan, zoals `CD1`, wordt met rust gelaten.

## [0.14.0] - 2026-08-19

### Added
- **De stemzoekopdracht begrijpt nu een heel verzoek in plaats van alleen een genre.** "Speel
  willekeurige favorieten uit 2023 af" kwam bij de vrije-tekstzoekopdracht terecht, die alleen
  artiest-, album- en titelnamen kent, en antwoordde met stilte. De zin wordt nu uit elkaar
  gehaald in de onderdelen waar de bibliotheek op kan filteren -- een genre, een artiest ("van
  headhunterz"), een label ("label art of creation"), een jaar ("uit 2021"), je favorieten, en
  nummers of livesets -- plus een volgorde: "willekeurig" schudt, "recent" speelt op releasedatum,
  "recent toegevoegd" op de datum dat de bibliotheek bijkwam. Alles is combineerbaar en alles is
  optioneel, in het Nederlands en in het Engels; "speel recent af" speelt de hele bibliotheek op
  releasedatum.

  Elke uitgesproken naam wordt eerst tegen de bibliotheek gelegd, want de server antwoordt op een
  filterwaarde die hij niet kent met een fout in plaats van met een lege lijst -- één verkeerd
  verstaan woord zou anders het hele verzoek kosten. Wat niet geplaatst kan worden valt weg en de
  rest speelt gewoon, dus "speel zwabberkore uit 2021 af" speelt 2021. Kan er niets geplaatst
  worden, dan neemt de gewone zoekfunctie het over en zoekt op titel -- daarom vindt "speel
  headhunterz af" nog steeds het nummer met die naam en niet alles wat de artiest ooit uitbracht.
- **Een pagina met alle spraakcommando's**, te vinden via Over. Niets van bovenstaande formulering
  is te ontdekken door tegen de auto te praten en te hopen.
- **Een tracklijst in de app is nu zelf te sorteren.** Open je een genre, een label, een
  festival, een jaar, een podcast, een line-up of een sterrenfilter, dan kwam die lijst altijd
  terug op releasedatum, zonder manier om dat te wijzigen. Boven de lijst staat nu dezelfde
  keuzelijst als in de webinterface: recent uitgebracht, recent toegevoegd, meest gespeeld,
  recent gespeeld, op waardering, op naam en willekeurig. De lijst opent op de sortering
  waarmee je binnenkwam, dus zonder een keuze te maken verandert er niets. Albums, afspeellijsten
  en podcastafleveringen houden hun eigen volgorde en krijgen de keuzelijst niet, en in
  offlinemodus blijft hij verborgen omdat de sortering daar bij de server vandaan zou moeten komen.

### Fixed
- **In de Android Auto-bibliotheek stond "Favorieten" twee keer.** De nummers met een ster en de map
  met favoriete genres en tegels hadden in het Nederlands allebei dezelfde naam, dus in de auto was
  niet te zien welke welke was. Er is nu één map Favorieten, met daarin "Favoriete nummers" naast de
  favoriete genres en playlists.

## [0.13.3] - 2026-08-19

### Changed
- **Een genre dat je met je stem opvraagt speelt nu op releasedatum, niet op datum
  toegevoegd.** "Speel genre hardstyle af" gaf de nummers die het laatst in de bibliotheek
  waren beland, en bij een importronde is dat honderd nummers uit twintig jaargangen die op
  één middag binnenkwamen. De stemzoekopdracht gebruikt nu dezelfde sortering als het blok
  "Recent uitgebracht" op de startpagina. Nummers zonder releasedatum vallen terug op hun
  bestandsdatum en sluiten de rij, dus er verdwijnt niets uit het resultaat. De bladerboom
  onder Genres sorteert ongewijzigd op datum toegevoegd.

## [0.13.2] - 2026-08-19

### Changed
- SoundCloud accounts are now checked at a rate that follows how recently they
  uploaded, across five tiers: six-hourly for accounts that posted this week, then
  daily, every three days, weekly, and monthly for accounts dormant over a year. The
  four new tier cooldowns are configurable under Systeembeheer → Downloaders → Timing;
  the dormant one doubles as the longest a returning account can go unnoticed.
- A SoundCloud check now begins with a single-request probe for the account's newest
  track, and skips the account entirely when that track is already archived.
- A sweep now visits the accounts that are furthest past their own cooldown first,
  instead of working alphabetically.

### Fixed
- **De beheerpagina herkent je weer als beheerder.** De gedeelde systeemsleutel stond in de
  productie-`.env` als `MUMA_API_KEY`, maar de compose-stack gaf alleen `API_KEY` door -- en die
  regel was leeg. Zolang de code nog een hardgecodeerde sleutel als terugval had, viel dat niet op;
  sinds die terugval weg is, weigert de server elke aanroep met de systeemsleutel. Dat waren niet
  alleen `/api/auth/verify` (403) en `/api/config` (401) van de beheerpagina, maar ook de
  scrobble- en waarderingswebhooks van LMS, die stilzwijgend werden weggegooid. Beide spellingen
  worden nu doorgegeven, en de pijplijn weigert voortaan te deployen als geen van beide is gezet.
- **Een sleutel die de server niet meer accepteert blokkeert de beheerpagina niet langer.** De
  automatische login liep alleen als er helemaal geen sleutel was, dus een verouderde sleutel in de
  browseropslag bleef eeuwig hangen: elk bezoek toonde "kan niet verbinden" en `isAdmin` viel terug
  op alleen de Subsonic-rol, waardoor je beheerstatus willekeurig leek te verdwijnen. Een 401 of 403
  gooit de sleutel nu weg en logt opnieuw in met je spelerwachtwoord. Een 5xx of een mislukt verzoek
  doet dat expres niet -- een haperend netwerk is geen bewijs dat je sleutel fout is.
- SoundCloud checks paged an account's entire catalogue before downloading anything,
  because `lazy_playlist` was off and `break_on_existing` could therefore only stop the
  download loop. A large account cost 28 API requests per check whether or not it had
  anything new.
- **"File saved" betekent voortaan dat het bestand ook echt geschreven is.** De tagger logde die
  regel één statement vóór de schrijfactie, dus een write die het bestandssysteem weigerde kwam er
  alsnog als succes uit -- de backfill over de bibliotheek logde 17356 keer "File saved" voor 8885
  daadwerkelijk geschreven bestanden, met de waarheid alleen in een WARNING twee regels verderop.

## [0.13.1] - 2026-08-18

### Fixed
- **"Speel mainstream hardstyle af" speelt nu dat genre.** Het woord "genre" was het enige signaal
  waar de spraakzoekactie op afging, en juist dat woord haalt Google Assistent uit de zin zodra hij
  begrijpt dat er een genre bedoeld wordt -- dus kwam er "mainstream hardstyle" binnen, ging dat
  naar de vrije-tekstzoekactie, en landde je op een album. Een zin zonder genre-bewoording wordt nu
  ook als genrenaam aangeboden, en speelt dat genre zodra hij exact overeenkomt met een genre uit de
  bibliotheek. Minder dan exact blijft bij de vrije-tekstzoekactie, zodat een titel die alleen maar
  op een genre lijkt niets merkt. Het aanspreken van de app ("... af op MuMa") wordt voortaan van de
  zin afgehaald, wat eerder niet gebeurde.

## [0.13.0] - 2026-08-18

### Added
- **"Speel genre hardstyle af" speelt dat genre.** De spraakzoekopdracht in de auto draaide altijd de
  vrije-tekstzoekactie, en die kijkt naar artiest, album en titel -- een genre komt daar in geen van
  drieën voor, dus bleef de auto stil of landde je op een willekeurig album dat toevallig een woord
  deelde. Een uitgesproken genre draait nu dezelfde query als het bladermenu: de laatst toegevoegde
  nummers van dat genre, tot het maximum uit de instellingen, ongeacht waardering. Zeg je "sets" of
  "livesets", dan krijg je de lange opnames in plaats van de nummers. Spraakherkenning knipt en plakt
  namen, dus "hard style" en "tech house music" vinden hun genre alsnog; een genre dat de bibliotheek
  niet kent valt terug op de oude vrije-tekstzoekactie.
- **"Speel X hierna af op MuMa" zet dat nummer achter wat er speelt.** Google Assistent kent geen
  wachtrij-werkwoord voor externe muziekapps: "voeg X toe aan MuMa" wordt binnen Assistent zelf
  geweigerd en bereikt de app nooit. De enige deur die wel opengaat is een speelverzoek met vrije
  tekst, dus reist de wachtrij-instructie mee in die zin als markeerwoord ("speel X hierna af op
  MuMa", "play X next on MuMa") en wordt er in de app weer uitgehaald. Markeerwoorden tellen alleen
  aan het eind van de zin, zodat een titel als "The Next Level" heel blijft, en een zin die uit niets
  anders dan een markeerwoord bestaat valt terug op gewoon afspelen.
- **Een LMS-scan kan voortaan per batch worden aangezet.** `LmsScanTrigger` roept `startScan.view`
  aan op elke ingestelde LMS-host, bedoeld voor één keer per download-, import- of tagronde. LMS'
  incrementele scan verwerkt alleen nieuwe of gewijzigde bestanden, dus dat is goedkoop, en het laat
  LMS' eigen schema omlaag -- van uurlijks naar dagelijks -- zonder dat de bibliotheek achterloopt.
  De helper draait nog nergens mee; hij wordt aangesloten bij de uitvoering van het
  retag-invalidatie- en BPM-plan dat in deze release is vastgelegd.

### Fixed
- **De backfill-scripts vinden de database weer.** `backfill_release_dates.py` en
  `seed_scene_group_date_formats.py` lezen hun databaseparameters rechtstreeks uit de omgeving. De
  compose-stack injecteert die, maar vanuit een checkout staan ze alleen in de `.env` van de
  repository -- het seeding-script liep dus eerst de hele bibliotheek af en faalde pas daarna op het
  wegschrijven, wat de volledige run kostte. Allebei laden nu die `.env`, net als
  `scripts/library_stats.py` al deed. Een override op de commandoregel wint nog steeds.

## [0.12.2] - 2026-08-18

### Fixed
- **"Speel alles" in de auto speelt weer op volgorde.** Shuffle is plakkerige spelerstand: zette je
  hem ooit aan op de telefoon, dan bleef hij aan tot je hem zelf uitzette, en het bladermenu van
  Android Auto raakte die stand nooit aan. Een wachtrij die je in de auto startte erfde hem dus --
  precies op de ritten na een geshuffelde luisterbeurt op de telefoon, wat het willekeurig deed
  lijken. Een wachtrij die in de auto begint zet shuffle nu uit. De shuffle-knop in de auto blijft
  gewoon werken; die hutselt de wachtrij zelf door elkaar.

## [0.12.1] - 2026-08-18

### Changed
- **Het raster onthoudt de plek, nooit het album eronder.** Een wachtrij zonder lijst erachter --
  gestart vanuit Android Auto, vanuit de notificatie, of hersteld bij het opstarten -- legde het
  album vast van wat er speelde. Dat is geen plek waar je heen ging, en uit een genrelijst was het
  ronduit fout: een nummer uit Raw Hardstyle schreef de compilatie weg waarop het is uitgebracht.
  Zo'n wachtrij schrijft nu niets weg. Een albumscherm legt nog wel zijn album vast, want daar begon
  het afspelen.

### Fixed
- **Een genre-, label-, festival-, podcast- of jaarlijst wordt eindelijk als zichzelf herkend.** Elk
  bladerscherm draagt zijn tag in de filters in plaats van in een eigen argument, en de historie las
  alleen die argumenten -- dus die schermen leken bronloos en vielen door naar het album. Spelen uit
  Raw Hardstyle legt nu Raw Hardstyle vast, en spelen uit Art of Creation het label.
- **"Speel nu" op één nummer onthoudt de lijst waaruit je het speelde.** Alleen de play-knop van een
  lijst meldde het scherm erachter aan, dus één nummer uit Raw Hardstyle via het nummermenu legde de
  compilatie vast waar dat nummer toevallig op staat -- Dirty Workz in plaats van het genre.
  "Speel hierna" en "Achteraan" laten de bron van de lopende wachtrij met rust.
- **Een snelkoppeling verschijnt nu zodra je op play drukt.** Hij werd pas weggeschreven als een
  nummer scrobbelde, en dat gebeurt alleen als het uitspeelt -- dus een lijst starten en doorskippen,
  of half luisteren, liet het raster onaangeroerd. Het vullen van de wachtrij schrijft hem nu weg.
- **"Onlangs beluisterd" in de Android-app bewoog niet meer.** De lijst waar een wachtrij vandaan kwam
  werd blijvend onthouden in plaats van per wachtrij, dus het laatste bladerscherm waaruit je speelde
  bleef de bron van alles daarna -- van het beginscherm, uit zoeken, uit de notificatie, uit de auto.
  Het raster schreef steeds dezelfde snelkoppeling weg en veranderde daardoor nooit. Een bron hoort nu
  bij precies één wachtrij, en een wachtrij zonder lijst erachter legt niets vast.
- **Snelkoppelingen waren hun hoes kwijt.** Een album of afspeellijst werd opgeslagen zonder het id
  waarop de hoes hangt, dus het raster tekende een placeholder waar eerst de hoes stond. Een genre,
  festival, label of podcast heeft zelf geen hoes en leent er nu één van een nummer met die tag,
  net zoals een artiest zijn foto al leende -- één keer opzoeken per snelkoppeling, daarna bewaard.

## [0.12.0] - 2026-08-17

### Added
- **De Festivals-tab kent nu 63 festivals in plaats van 15.** Qlimax, Reverze, Ground Zero, Q-BASE,
  X-Qlusive, Thunderdome, Masters of Hardcore, Pussy Lounge en de rest zijn toegevoegd, elk met de
  schrijfwijzen waaronder ze in titels en mapnamen voorkomen. Een festival hoeft nog maar één keer
  ingevoerd te worden: waar vroeger een rij per editie nodig was voordat er überhaupt iets herkend werd,
  voegt een editie nu alleen de datum toe.
- **Livesets, warm-up mixes en podcasts worden eindelijk gelabeld.** De festivalherkenning hing alleen aan
  YouTube-downloads, waardoor juist de map met je livesets er nooit langs kwam. Hij draait nu ook op de
  generieke mappen en op SoundCloud, en kijkt naast de titel ook naar de map waarin een set staat --
  `Livesets/Qlimax 2022/` zegt vaak meer dan de tag in het bestand.
- **Radioshows en podcasts worden gelabeld, net als festivals.** Isaac's Hardstyle Sessions, Hard With
  Style, The Uptempo Tribe Podcast, Hardcore Italia: een aflevering was tot nu toe niet van een gewone
  lange mix te onderscheiden. De tagger schrijft nu een PODCAST- en PODCAST_EPISODE-tag op elke mix van
  tien minuten of langer die bij een goedgekeurde show hoort, en herkent de show ook aan de map, want
  `Podcasts/The Magic Show/2011/Podcast week 023.mp3` noemt zichzelf nergens in de bestandsnaam.
- **De showlijst wordt gevonden, niet ingetypt.** `tools/detect_podcasts.py` groepeert alles met een
  afleveringsnummer op wat er overblijft als je het nummer, de gast en de maand weglaat, en zet elke serie
  klaar ter beoordeling. Op de huidige bibliotheek vindt hij 208 series met acht of meer afleveringen.
- **Beheer > Podcasts keurt shows goed of af**, met dezelfde wit/zwart/onbekend-logica als genrecuratie.
  Eén show met meerdere namen voeg je samen: de schrijfwijzen verhuizen naar de show die je houdt, zodat
  "DJ ISAAC - HARDSTYLE SESSIONS" blijft matchen maar "Isaac's Hardstyle Sessions" in je bibliotheek staat.
  Niets wordt getagd zolang een show niet is goedgekeurd.
- **Een Podcasts-pagina in de webplayer en in de Android-app**, met per show zijn afleveringen. Beide
  lijsten komen van de PODCAST-tag, dus ze vullen zich zodra de tagger langs is geweest.
- **Het beginscherm van MuMa Mobile eindigt in twee leesbare nummerlijsten**, "Onlangs uitgebracht" en
  "Onlangs toegevoegd", elk met een "Toon meer" die de volledige lijst in dezelfde sortering opent. Een
  carrousel herken je aan de hoes, en juist het SoundCloud- en YouTube-deel van de bibliotheek heeft er
  geen: een rij blanco vierkantjes zei niets waar een regel met titel en artiest dat altijd doet.
- **Twee nieuwe instellingen onder Home**: hoeveel snelkoppelingen het raster toont (2 tot 10, standaard
  8) en hoeveel regels elke nummerlijst toont voor "Toon meer" (1 tot 10, standaard 5).

### Changed
- **"Onlangs afgespeeld" onthoudt nu waar je vandaan speelde.** De lijst vulde zich met alles wat je
  opende, dus bladeren vervuilde hem en het album van één aangetikt nummer duwde de rest eruit. Een
  snelkoppeling wordt nu pas geschreven als je op afspelen drukt, en wijst naar de lijst waar de
  wachtrij uit kwam: speel je één track uit Raw Hardstyle, dan is de snelkoppeling Raw Hardstyle.
  Aantikken draait die zoekopdracht opnieuw, dus je krijgt andere nummers uit dezelfde hoek van je
  bibliotheek in plaats van een herhaling. Shuffle-all, favorietenlijsten en gedeelde links leggen
  niets vast — daar zit geen zoekopdracht achter om opnieuw te draaien.
- **Memories is één balk in plaats van een carrousel van jaren**, met het dichtstbijzijnde jaar
  samengevat, en verdwijnt volledig op een dag waar niets in zit. Alle jaren staan nog steeds compleet
  op het Memories-scherm, één tik verderop.

### Removed
- **De sectie "Onlangs bijgewerkt" in MuMa Mobile.** Herschreven metadata is iets wat de scanner doet,
  niet iets om naar te luisteren.

### Fixed
- **Bestanden die los in Warm Up Mixes stonden werden helemaal overgeslagen.** De tagger liep alleen over
  de submappen van de generieke mappen, en in die map staat vrijwel alles los. Ze kregen dus ook geen
  genre of artiest.
- **Een nieuw label is meteen zichtbaar in plaats van pas de volgende dag.** Na een tagronde vraagt MuMa
  de muziekserver zelf om te scannen, in plaats van te wachten tot die er uit zichzelf aan toe is.
- **Een festivalnaam met een spatie te veel matchte niet meer.** Herkenning gaat nu op genormaliseerde
  tekst, dus accenten, leestekens en spaties maken niet meer uit -- en 'Rise' matcht niet langer op
  'Sunrise'.

## [0.11.0] - 2026-08-17

### Added
- **Nummers van een label krijgen nu een echte releasedatum, niet alleen een jaartal.** Bij een import
  las MuMa alleen het jaar uit de tags, waardoor alles van 2026 als één hoop door elkaar stond en niets
  van dit jaar bovenaan "recent uitgebracht" kwam. De exacte datum staat meestal al in de NFO die met de
  release meekomt, en die wordt nu uitgelezen en als originele releasedatum weggeschreven. Je kunt in de
  bibliotheek op releasedatum sorteren, en Memories kan er verjaardagen op matchen.
- **De trackkolommen in de bibliotheek zijn sorteerbaar.** Titel, BPM en releasedatum; een klik sorteert
  aflopend, nog een klik draait het om. Nummers zonder bekende datum staan altijd onderaan, in beide
  richtingen — onbekend is niet ouder dan 1970, het is er niet.

### Fixed
- **Een ripdatum maakt oude muziek niet meer jong.** De datum uit een NFO wordt alleen geaccepteerd als
  het jaar overeenkomt met het jaartal van de release zelf, dus een vinylrip uit 1995 die in 2024 is
  gerippt blijft uit 1995 staan.

## [0.10.0] - 2026-08-17

### Added
- **The address bar now describes where you are in the web player.** Screens that had no address of their
  own — listening history, favourites, an open playlist, and every tab inside Settings and Management —
  now each have one, so `/management/scanner` and `/playlist/1234` can be bookmarked, refreshed and shared.
  Visiting `/settings` or `/management` without naming a tab still reopens the tab you last used, and an
  address naming a tab that no longer exists opens that screen's first tab instead of a blank page. Back
  and forward move through the screens you visited, tab switches included. Genre and label addresses keep
  using the name, so links made before this change still work.

### Fixed
- **Refreshing on a genre or search term containing a dot no longer shows "File not found".** LMS treated
  any dot in the address as a request for a file, so a genre named `nu.jazz` returned a 404 on reload
  instead of the app. It now only treats known asset extensions that way.

- **Ratings given in the app now survive in music-management again.** The webhook that mirrors a rating
  matches the track by file path, but only knew the `/mnt/music` spelling of it. Since the media library
  was re-rooted at `/music` no lookup matched, and 202 of the 336 mirrored ratings were filed under a
  track id that no longer exists. Both roots are now recognised, in either direction.

### Security
- **LMS no longer serves files from outside its web root.** A crafted address containing `..` resolved to a
  real path on disk and was returned verbatim; such requests are now rejected with a 404.

## [0.9.3] - 2026-08-15

### Fixed

- **Every genre reported "0 nummers".** On production all 38284 rows of the `cluster` table carried
  `track_count` 0 while `track_cluster` held 1.7M links, so `getGenres` answered `songCount="0"` for
  a library that actually has 67653 Hardstyle tracks. That column is cached, and only
  `ScanStepComputeClusterStats` fills it — a step that ran solely when a scan saw changes. A scan
  that aborts after the clusters are created therefore leaves every count at zero, and each later
  scan, having nothing to do, skips the step and keeps it that way. The step now also runs when a
  cluster has tracks but still reports zero, so an interrupted scan heals itself on the next run.
- **The management tabs are reachable on a phone again.** The sidebar column is hidden below `md`
  and the mobile bottom bar has no entry for the tabs inside the management view, so the screen
  opened on whatever tab was last used with no way to leave it; settings had the same problem. Both
  sidebars are now also offered as a drawer, opened from a menu button in the top bar.

## [0.9.2] - 2026-08-15

### Fixed

- **The library scan no longer takes LMS down with it.** Every hourly scan aborted the process with
  `Sqlite3: commit transaction: FOREIGN KEY constraint failed` — 835 restarts in a day, and no scan
  ever finished: the `tracklist` table held 3 rows against 48266 playlist files. A tracklist the
  scanner builds for a playlist file has no owning user, and that was stored as the internal
  "invalid id" sentinel (-1) instead of NULL, against a foreign key that older databases still
  carry. Because the constraint is deferred, the insert passed and the commit killed the process.
- **The workers no longer leak a database connection per lookup.** Ten call sites opened a
  connection and never closed it; the importer's catalogue-ID lookup alone accounted for 841k of
  the 843k `Aborted connection` warnings MariaDB logged in 24 hours. `DatabaseConnector` now offers
  a context manager that always closes.
- **The radio's Subsonic key is passed through correctly.** The compose file used a nested default
  (`${A:-${B}}`), which the docker-compose version running in production renders as a literal
  string rather than expanding it, so the player received the text `${LMS_SUBSONIC_API_KEY}` as its
  API key. Note that radio is not fully restored by this: LMS keeps Subsonic tokens in memory only,
  so a key configured in a file cannot survive a restart. That remains open.
- **SoundCloud downloads can impersonate a browser again.** The downloader image installed yt-dlp
  without the curl-cffi extra, so every impersonation target reported as unavailable and SoundCloud
  answered with 403s.
- **A slow MusicBrainz no longer floods the log.** Lookups used a flat 5-second timeout with no
  retry, producing ~2.3k error lines a day. They now allow longer to read, retry once, and record a
  timeout as a warning.

## [0.9.1] - 2026-08-14

### Changed
- **Design documents only; no runtime code changed.** This release records two designs that were
  written but never merged: origin metadata sidecars for the downloaders and the importer, and
  navigation out of the track info modal in MuMa Mobile. The published images are identical in
  content to 0.9.0 — nothing under `services/` differs — so a deployment of this version changes
  the version string and nothing else.

## [0.9.0] - 2026-08-14

### Added
- **Failed player actions now say so.** A scrobble that never reached the server, a rating the
  server rejected, playback that would not start and a stream that failed to load all ended in the
  browser console, where nobody looks. They now appear as notifications in the top-right corner of
  the web player: errors stay until you dismiss them or reload the page, while warnings and
  confirmations clear themselves. Repeats of the same message count up instead of stacking. Only
  player errors and actions you took yourself are reported — background loads stay quiet, and the
  management tabs keep their inline status panels.

### Changed

- **The blocking alert boxes are gone from the web player.** Refreshing a track and saving the
  queue as a playlist used browser `alert()` popups, which halt the page and look nothing like the
  rest of the interface. Both now report through the notification stack.

### Fixed
- A rating the server refused is now reported as a notification rather than only being put back
  silently, and the same Subsonic status check now guards scrobbling, which was losing plays the
  way ratings were lost before 0.8.3.

## [0.8.3] - 2026-08-14

### Security

- The system API key is no longer hardcoded as a fallback in the music_manager
  routers. Resolution moved to `services/music_manager/api_key.py`, which fails
  closed when no key is configured. The key's own value still has to be rotated:
  removing it from the working tree does not unpublish the copy in git history.

### Changed

- The browse views are grouped under a collapsible Library section in the
  frontend navigation.

### Fixed
- **YouTube downloads are tagged the way SoundCloud downloads are.** `YoutubeSong` had no artist
  inference; in its place sat a hand-written title split that only fired while the artist tag still
  equalled the channel folder. YouTube's music-credit panel makes yt-dlp supply an artist of its
  own, and from that moment the split stopped happening and the artists stayed in the title. It
  also appended to the artist tag rather than replacing it, so the channel name stayed behind next
  to the real artist. YouTube now runs the same rule stack as SoundCloud, keeping only its own
  album, publisher, festival inference and channel-to-genre lookup.
- **A YouTube download is no longer tagged with the genre `Music`.** yt-dlp resolves the genre tag
  as `genre -> genres -> categories -> tags`, and the YouTube extractor sets neither of the first
  two but always sets `categories` — so ffmpeg wrote the video's YouTube category, or its keyword
  list where there was no category, and every one of them landed in the genre curation queue.
  `migrate_v7_youtube_category_genres.sql` marks the categories black and flags the YouTube tree
  for rescan, so tracks already on disk are corrected too.
- **A rating the server refused no longer looks like it was stored.** Subsonic reports its own
  errors (a throttled login, an id it cannot parse, a failed write) in the response body with HTTP
  200, and the web UI only looked at the HTTP status: the stars lit up and stayed lit while nothing
  reached `rated_track`, so the same track was still unrated in the listening history, in Favorites
  and in the file tags. The track list and the player now read the Subsonic status, put the stars
  back the way they were when the rating did not land, and log why.
- **The stars now repaint on the click that sets them.** They were painted from `track.userRating`
  on an object that is not reactive state in most views (and is rebuilt from scratch on every radio
  update), so the click stored a rating that only became visible after the list was fetched
  again — and in the player during radio, never.

## [0.8.2] - 2026-08-12

### Fixed
- **A genre in `rules_genres` is now recognised whatever its casing.** SoundCloud hands out the
  genre exactly as the uploader typed it, and the rules lookup matched on the stored spelling only:
  `uptempo` was accepted while `Uptempo`, `UPTEMPO`, `techno`, `hardcore` and `frenchcore` were all
  rejected as unknown genres, even though the row was there under a different casing. Both the
  preloaded and the database lookup now compare case-insensitively and answer with the spelling the
  table stores, or with its correction, so a single genre no longer enters the library as
  `Uptempo Hardcore` next to `uptempo`.
- **The SoundCloud genre fetcher no longer pays a full minute for a track that does not exist.** It
  paused 60 seconds after every yt-dlp call, so a deleted track (HTTP 404) and a DRM-only track cost
  as much as a real fetch, while a 403 was skipped as if nothing had happened and the next thousand
  tracks ran into the same refusal. Failures are now told apart: a permanent one waits 5 seconds, a
  refusal backs off from 5 minutes and doubles to at most an hour, and five refusals in a row end
  the pass. The end-of-run summary reports the failures per kind, and yt-dlp's multi-line complaint
  is logged as its single ERROR line.

## [0.8.1] - 2026-08-08

### Fixed
- **A track with more than one genre now offers a link per genre.** The genre column in the track
  list rendered the whole genre string as a single link, so a track tagged `hardstyle, hardcore`
  linked to a genre by that literal name — a genre that does not exist — instead of to either of
  the two. The column now links each genre on its own and keeps the separators as plain text, so it
  still reads exactly as the server sent it.

## [0.8.0] - 2026-08-07

### Added
- **MuMa Mobile gets two accent colours and a launcher icon you pick separately.** Settings →
  Appearance now offers an accent colour, MuMa green or Ultrasonic indigo, and an app icon in those
  same two colours, as two independent settings. The theme preference it replaces offered Day &
  Night, Dark and Black, all three of which resolved to the same black theme and so did nothing. The
  accent lives in the theme now rather than in 34 hardcoded resource references and 8 Kotlin call
  sites, which is what makes a second colour possible at all. Sets mode turns out to carry a second
  brand colour of its own, so that one is a theme attribute too and the pair swaps roles rather than
  leaving two near-identical blues next to each other. The launcher icon is switched by enabling one
  of two `activity-alias` entries, which is the only mechanism Android offers.

### Changed
- **The last two Ultrasonic headphones are gone.** The download and playback notification icons show
  the five-bar MuMa mark. All icon geometry is now emitted by `tools/render_branding_icons.py` from
  one description of the mark, so the green and indigo variants cannot drift apart.

## [0.7.0] - 2026-08-07

### Added
- **A severity-tagged event log replaces the flat notifications list.** Every service now writes
  `INFO`/`WARNING`/`ERROR`/`CRITICAL` events straight to a new `events` table, which is the source of
  truth; `ntfy.sh` becomes a downstream sink instead of the only place an event ever existed. The
  frontend's Notifications tab is now Logboek, with level chips, a service filter, a time window and
  search. A new `notify_topic_alerts` topic gets every `WARNING` and higher automatically, with a
  priority and tag per severity and de-duplication for repeats within five minutes, so a single
  flapping connection can't flood the phone. `GET /health` reports real database and background-thread
  status and returns 503 when degraded, instead of a hard-coded `ok`.
- **Tapping the playing track opens a track info sheet.** The MuMa Mobile player's options menu
  carried seven entries that all acted on the one playing track — go to artist, go to album, show
  metadata, lyrics, share song, refresh track and the two bookmark items — buried behind an overflow
  menu that is otherwise about the queue. Tapping the title block now opens a sheet with the cover on
  a blurred backdrop of itself, the five star rating, artist and album as rows that navigate, the
  remaining actions as buttons, and genre, track number, release date and duration underneath, with
  the technical details folded away. Rows the track cannot fill hide instead of rendering `Year: `
  with nothing after it, which the old metadata screen did.
- **The genres, labels and playlists views can be sorted and filtered.** The three collection grids
  had no controls at all: genres arrived alphabetically with everything under ten tracks silently
  dropped, labels arrived alphabetically without counts, and playlists in whatever order the server
  listed them. They now share a search box, a sort key with a direction toggle, a favourites chip and
  a live "shown of total". Genres and labels get "minimaal 10/50/100" chips in place of the hardcoded
  threshold, playlists get a visibility chip and sort on length and last change, and labels and
  playlists can be favourited the way genres already could. `getRecordLabels` answers with
  `songCount`/`albumCount`, without which labels could not be sorted or filtered by size at all.

### Fixed
- **Clicking a label filtered on the wrong thing.** `label:Kompakt: Total` was split on every colon
  and filtered on `Kompakt`, which no track carries; names are now taken whole. The genre, year and
  search filters are shared by every track list, so a genre picked on the Songs screen — or a
  leftover search term — silently narrowed the label just tapped; they are reset when a different
  track list opens. Genre and label names now go into the URL percent-encoded, so a name with a slash
  no longer parses back as a different view.
- The management screen kept polling artist-image progress after it was gone, so the requests and
  their logging outlived the screen.
- The event log tab no longer crashes on a `200` whose body is not the log payload; it shows nothing
  instead.

## [0.6.0] - 2026-08-06

### Added
- **A radio channel is a stored library filter.** Channels could only be "the whole library" or one
  genre, which is too coarse to give a station an identity — Q-dance Records and Dirty Workz both
  collapse into "hardstyle". A channel now stores any combination of label, genre, artist, length,
  year and rating, served by a new `/rest/getSongsByFilter` endpoint in LMS that exposes filtering
  the database layer already had.
- **Radio channels are managed from the management page**, behind a new `radio.manage` permission:
  create, edit, take on and off air, and preview what a filter matches — how many tracks plus a
  sample — before saving. Previewing is also what catches a label name LMS does not know.
- **The player offers a channel picker** when more than one channel is on air, labelled by what each
  one plays, and still tunes straight in when there is only one.

### Fixed
- The tagger, scanner and radio loops no longer start when `MUMA_DISABLE_BACKGROUND_WORKERS` is set,
  which keeps the radio scheduler out of the integration database it was deadlocking with.

## [0.5.5] - 2026-08-06

### Changed
- **The MuMa wordmark appears once per screen again.** The top bar carried its own mark and wordmark
  next to the profile button, right above the one the sidebar header already shows, so the branding
  read twice on every screen. The top-right copy is gone and the sidebar owns the brand.

## [0.5.4] - 2026-08-06

### Fixed
- **A broken .m4a on a read-only volume no longer fails in a confusing way.** When the tagger cannot
  read an m4a it deletes the file and moves on, but if the delete itself fails — a read-only mount, a
  permission error — the load continued into code that reads a field the failed load never set, so
  the real problem surfaced as an `AttributeError` about an internal attribute. Both outcomes now
  stop at the same place.
- **"Zie meer" in the search results opens again.** The link handed its category on without an item,
  and the code behind it read an id off that missing item, so clicking it threw and the full result
  list never appeared.
- **`BoundedTreeSet` built from an existing collection is no longer empty.** Its two element-taking
  constructors handed their contents to `TreeSet`, which adds them through the very method that
  enforces the bound — before the bound has a value. Every element was trimmed away immediately. The
  bound is now set first. Nothing in the app used those constructors, so no behaviour changed with
  it, but the class no longer contains a trap.

- **The management screen stops polling when you leave it.** It asks the server every second how far
  the artist-image fetch has got, and nothing cancelled that when the screen was torn down, so the
  requests — and the logging when they stopped being answerable — carried on for the rest of the
  session.

### Removed
- Two management components that nothing imported (`components/Sidebar.svelte` and
  `components/Login.svelte` — the app uses `ManagementSidebar.svelte`), and an unreachable
  `openArtist()` in the album view. Dropping them puts the frontend coverage figure at 82.0%, where
  it was measuring code that could never run.

## [0.5.3] - 2026-08-05

### Changed
- **The test suites now cover the parts of the product people actually touch.** The frontend went
  from 24.8% to 80.8% of statements and the Python services from 77.8% to 87.9% of production code,
  with both ratchets moved up to match (frontend 80/60/78/79, Python 92%). The frontend gained
  coverage of the login screen including the Google access-request flow, the dashboard and every
  view it routes to, the player transport, the artist and album screens, dynamic playlists, tagger
  rules, genre curation, the ListenBrainz import, access-request review, the library browser and its
  facets, and the queue actions. On the Python side `services/ml-analyzer` had no tests at all — 766
  lines at 0% — and now covers the analyzer, its maintenance scripts and the predictor.
  `trainer.py` is deliberately left uncovered: it is pandas and scikit-learn end to end, and with
  those libraries stubbed a test would assert on mocks rather than on behaviour.
- **Coverage figures no longer count generated code.** Jacoco was measuring Room's generated
  `*_Impl` classes for MuMa Mobile — 4534 of the 25331 lines it reported, about 18% of the app — so
  the figure looked worse than the hand-written code actually is. No unit test should ever target
  KSP output.

### Fixed
- **The music server's coverage report was measuring under 1% of it.** `CMAKE_UNITY_BUILD=ON` merges
  many `.cpp` files into a single translation unit, and gcov then reports against that merged file
  instead of the real sources: gcovr resolved 18 files and 453 lines of a 76 000-line codebase, so
  the reported 36.9% was a figure about almost nothing. The unity build stays on for the images that
  are shipped and is turned off for the run that measures coverage. The report now covers 686 files
  and 44 034 lines, at 38.6% — the suite was always doing more than the badge showed.

## [0.5.2] - 2026-08-05

### Changed
- **MuMa is one name carrying one mark.** The web app and the Android app are the same product on
  two screens, but they carried two names and no mark of their own: the browser tab said "MuMa
  Spotify", the app was "MuMa Mobile", and the sidebar rendered Spotify's actual logo. The name is
  now MuMa everywhere — launcher, notification channels, browser tab and user-facing strings — and
  the mark is five bars in a green disc whose top edge traces an M. A single generator derives the
  favicon, the adaptive icon layers, the round variant and all five mipmap densities from one
  source, so they cannot drift apart; the adaptive foreground scales the disc to 83% so a round or
  square mask cannot clip it, and the monochrome layer carries only the bars, since themed icons
  get one colour. `applicationId` deliberately stays `nl.teunschriks.mumamobile`, so updates keep
  landing on the existing install. Written up in
  `docs/superpowers/specs/2026-08-05-muma-brand-design.md`.

### Fixed
- **"Recently played" remembers what was played, not only what was opened.** The home grid recorded
  items opened on a browse screen, on the assumption that playing something implies having opened it
  first. That does not hold for a session driven from Android Auto, the notification or the play
  queue, so an evening of listening in the car left the grid showing whatever was last tapped by
  hand. The same rebuild had also deleted the only writer of the "Last played genres" lists while
  leaving the Android Auto browser reading them, so those two lists were permanently empty. Both are
  written again from one place: every scrobble records the played album into the home grid and its
  genres into the per-mode genre lists.

## [0.5.1] - 2026-08-05

### Fixed
- **The app can find its own updates again.** The rename to MuMa Mobile also renamed the uploaded
  APK, from `ultrasonic-vX.Y.Z-<code>.apk` to `muma-mobile-*`, but apk-hoster has no field for an
  app name — the upload carries the file and its release notes and nothing else — so it reads the
  filename prefix to decide which series a build belongs to. Installed apps ask for the series by
  name (`/api/version?apk=ultrasonic`), so 0.4.0 landed in a series nothing queries: every phone
  would have stayed on 6.8.0 and been told it was up to date. The filename prefix now lives in its
  own `APK_SERIES` setting, pinned to `ultrasonic` and independent of the app's name. Moving it
  needs two releases — first a build that asks for the new series and falls back to the old one,
  then the flip — and is written up in `docs/deployment.md`.

## [0.5.0] - 2026-08-05

The YouTube downloader finally reads the `download_type` column that has been sitting in the
database unused, so channels marked as video are fetched as video -- in the best quality YouTube
offers, not the 360p a failed merge leaves behind.

### Added
- **YouTube channels marked as video are downloaded as video, in the best quality that exists.**
  `downloads_youtube_accounts.download_type` had been in the database for years without a single
  line of code reading it, so the eight channels set to `video` were fetched as audio instead.
  A sweep now runs the audio channels first and the video channels after, asks yt-dlp for
  `bestvideo*+bestaudio` merged into mkv, and writes to `youtube_video_folder`
  (`/mnt/music/Youtube_Video`) so the library scanner never meets a video file.
- `tools/list_youtube_video_residue.py` reports the stray video files and unmerged `.fNNN`
  fragments sitting in the audio tree, with their resolution. It only reports.

### Fixed
- **A channel listed as both audio and video is no longer swept twice as audio.** The table's key
  is `(name, download_type)` but the downloader selected only `name`, so seven channels came back
  as duplicates and both copies were treated as audio.
- **The 360p downloads.** yt-dlp falls back to YouTube's one remaining progressive stream, which is
  640x360, whenever it cannot merge separate video and audio. The video pass now refuses to run
  when ffmpeg is missing rather than silently producing that, and logs the resolution of every
  video it does fetch.
- **`downloads_youtube_archive` can hold the same video twice**, once as audio and once as video.
  Its key was `video_id` alone, so whichever pass ran first would have blocked the other forever.
- `active` and `min_duration` on a YouTube account row are read at last: an inactive channel is
  skipped, and the duration floor comes from the row instead of a hardcoded 60 seconds.

## [0.4.0] - 2026-08-05

Rating 5 now means "favorite" everywhere, and the separate favorite flag is gone. This cycle also
completes the Android app's rename to MuMa Mobile.

### Added
- **Albums can be rated.** The app only ever stored a favorite flag for an album, which synced
  nowhere; albums now carry a 0-5 rating like tracks do, and the star on an album row writes
  rating 5 instead of that flag.
- `scripts/migrate_stars_to_ratings.py` turns the existing `starred_*` rows in the LMS database
  into ratings, so favorites set before this release stay visible. An explicit rating always wins
  over a star, nothing is deleted, every row is written to a JSON export, and re-running is a
  no-op.

### Changed
- **There is no separate "favorite" any more: rating 5 is what favorite means.** Two ways to say
  "I like this" could contradict each other -- a four star track that was also starred, a starred
  track with no rating -- and only the rating travelled on to the file tags. `getStarred`,
  `getAlbumList type=starred` and the `starred` attribute in Subsonic responses now read the
  ratings. The Favorites screens keep their place and simply list what is rated five stars.
- **`star`/`unstar` still work, and now reach the file tags.** They stay in the Subsonic API for
  third party clients, but set rating 5 / clear the rating. A star from such a client used to be
  dropped on the way to the tags; it no longer is.
- The favorite toggles are gone from the interfaces: the star buttons in the LMS web UI, and in
  the app the heart/star toggle in track rows, the dedicated button in the player and its overflow
  menu entry. The five star display is the only rating control left.
- **The Android app is now MuMa Mobile.** The name it shows on the launcher, in its notifications
  and in its own screens changed from "Ultrasonic" to "MuMa Mobile", the Kotlin package moved from
  `org.moire.ultrasonic` to `nl.teunschriks.mumamobile`, and the module from `services/ultrasonic`
  to `services/muma-mobile` — completing the split from the deprecated upstream Ultrasonic project.
  The app's install identity (`applicationId`) is unchanged, so the update installs in place and
  keeps all servers, settings and downloads. **Home-screen widgets must be removed and re-added
  once** — launchers store the widget's old class name, which no longer exists. Media-button
  broadcast actions, media-session custom commands and notification channel IDs deliberately keep
  their historical `org.moire.ultrasonic` identifiers, pinned by `RuntimeContractTest`, so existing
  notification settings and pending intents keep working. The Subsonic client id sent to the server
  is unchanged for the same reason.
- **The built-in server entry is now called "MuMa" instead of "LMS".** Installs that already store
  the old name keep matching it, so nobody has to re-add the server.
- CI jobs, scripts and coverage artifacts followed the module rename: `ultrasonic:check` is now
  `muma-mobile:check`, `ultrasonic:build-debug`/`build-release` are now `muma-mobile:build-debug`/
  `build-release`, and the app release tag prefix changed from `ultrasonic-v*` to `muma-mobile-v*`.
  Existing tags are immutable and keep their old prefix; the version line continues unbroken.

### Fixed
- A change under `services/tests/` or `scripts/` did not run the Python test job, so a test added
  there was never executed by CI.

## [0.3.0] - 2026-08-05

An app-only cycle; the backend is unchanged. Ultrasonic moves to 6.8.0 / versionCode 259, and its
own [CHANGELOG](services/muma-mobile/CHANGELOG.md) carries the full detail.

### Added
- **The number of tracks a genre opens with is picked from the genre screen**, through a dropdown
  on the genre grid — 10, 25, 50, 100 or 500 — instead of a preference several screens away.

### Fixed
- **The rating button in Android Auto always gave one star**, whatever the track was rated before.
  Each button carries the rating it was drawn with in its `SessionCommand` extras, but a tap made
  in the car comes in over the legacy session, where media3 builds a fresh
  `SessionCommand(action, Bundle.EMPTY)` and hands the received bundle to a separate parameter — so
  the rating read as its default of 0 and every tap cycled to 1. The playing track now decides.
  See `docs/bug-reports/024-android-auto-rating-button-always-sets-one-star.md`.
- **The genre track limit in Settings did nothing**: it was stored under one preference key and
  read from another, so every genre opened with the built-in 100.

## [0.2.1] - 2026-08-03

### Fixed
- **A restart of music-manager no longer logs everybody out of the music server.** LMS sent its
  password checks through the HTTP client built for polite calls to third-party APIs like
  ListenBrainz: one request in flight at a time, retries on failure, and a 30-second freeze of the
  entire queue whenever anything went wrong. On an authentication check that combination is
  ruinous. A single connection error — which every deploy produces, because music-manager is
  recreated and gets a new address — stopped *all* authentication for thirty seconds. Every waiting
  request ran into its own ten-second timeout, and a timeout was reported to clients as "wrong
  username or password", so Ultrasonic and the web player discarded working credentials and logged
  themselves out. Their retries then kept the queue full, so each new batch of errors bought another
  thirty seconds and it never recovered on its own; only restarting the server cleared it. Password
  checks now go out directly, each independent of the others, with a two-second timeout instead of
  ten. A healthy check answers in well under a tenth of a second.
- **An unreachable login service is no longer reported as a wrong password.** It was impossible to
  tell the two apart: both came back as a plain "no". Clients take "wrong password" as final and
  wipe what they have stored, which is why a few seconds of downtime cost everyone their session.
  The two are now distinct all the way out — Subsonic clients get "authentication backend
  unavailable" rather than error 40, the Muma API answers 503 rather than 401, and the web login
  says the service cannot be reached. Nothing throws credentials away over it.
- **A rate-limited login is no longer counted as a failed one.** Being told "too many attempts" says
  nothing about whether the password was right, but it was recorded as a failed attempt anyway, so
  a throttle fed a second throttle on top of itself. LMS also ran its own login throttler in front
  of a music-manager that already limits per account — and it counted per client address, which for
  Subsonic traffic is the internal proxy hop that every user shares, so one person's typo could
  throttle everyone. That second throttler is now off for this backend; music-manager remains the
  single place where login rate limiting happens.

## [0.2.0] - 2026-08-03

### Added
- **The track list can show three lines instead of two.** Album and artist shared a single line, so
  a slightly longer title pushed both of them into an ellipsis and neither could be read.
  Settings > Appearance now offers a three-line row — title, album and artist stacked, with the
  stars, release date and duration on the right — alongside the compact two-line row, which stays
  the default and is unchanged.

### Fixed
- **The Beheer tab was hidden from admins.** The admin check calls `api/auth/verify`, which sits
  under the `/api/auth/` prefix the Muma interceptor treats as "needs no key", so the request went
  out unauthenticated: 401, an empty body, and `isAdmin` read as false for everyone. The
  interceptor now names the four credential endpoints explicitly rather than matching a prefix, and
  the visibility check re-runs on resume and after the auto-login has fetched a key, since the
  original check ran before either had happened.
- **Rotating the phone doubled the playlist.** A hundred tracks became two hundred, two hundred
  became four hundred. A configuration change closes the Koin activity scope, so the player's
  lifecycle support is rebuilt and restores the serialized session — but the playback service
  survives the rotation with the playlist still loaded, and restoring appends. The restore now
  returns early when the player already holds tracks: the serialized state exists to repopulate an
  empty player, and a live service is already the source of truth.

- **A pruned image no longer strands a production deploy half-applied.** A container whose image
  had since been removed from the host could not be recreated in place, so compose stopped and
  asked "Continue with the new image? [yN]" — a question nothing can answer over a non-interactive
  SSH session. The deploy died having already recreated most of the stack. Such containers are now
  removed before `up -d` runs, and rebuilt from the image the deploy just pulled.

### Documentation
- The README carries a functional overview of the CI/CD pipeline: which jobs run on which branch,
  and what each one gates.
- A design document for a release-candidate acceptance stack — an environment where a release
  branch can be exercised against production-like data before `deploy:prod` runs.

## [0.1.3] - 2026-08-02

### Fixed
- **Everyone was logged out again seconds after logging in.** The rate limit added to the
  authentication endpoints this cycle assumed `/api/auth/login` is a login form. It is also the
  password oracle the music server calls on *every* Subsonic request, over an internal hop that
  carries no client address — so all users shared one budget of ten calls a minute, and opening a
  home screen spent it in a second or two. Past that, the server read the refusal as "wrong
  password" and each client dutifully logged itself out. Only rejected attempts are counted now,
  and a login is counted per account instead of per caller, so browsing a library costs nothing and
  one account being guessed at cannot lock anyone else out. Guessing a password is still capped.

## [0.1.2] - 2026-08-02

### Changed
- **A track SoundCloud will not hand over no longer stops the whole downloader.** yt-dlp reports a
  subscriber-only, geo-blocked or since-deleted track as a 403, and the downloader read every one of
  those as SoundCloud pushing back: it parked the source, abandoned the remaining accounts of a
  1110-account sweep, and never marked the account as checked, so the next sweep met the same track
  and took the same 403. The counter behind that only returned to zero after a sweep that touched
  every account without a single 403 — which one permanently unavailable track makes impossible — so
  the backoff climbed to its ceiling and stayed there. Downloads stopped for two days while
  SoundCloud itself was still answering normally. A 403 is now read as what it is: individual tracks
  are written down and skipped on later sweeps, and the source is only parked on an explicit 429 or
  after several accounts in a row come back empty-handed. The backoff also decays on its own with
  time, and its ceiling drops from a day to an hour.
- **The downloader presents one consistent client to SoundCloud.** It sent a Chrome 120 user agent
  while offering cookies issued to Firefox, which is precisely the mismatch the anti-bot layer in
  front of SoundCloud looks for. It now says Firefox, matching the container the cookies come from,
  and the value is a setting rather than a constant frozen in code.
- **yt-dlp no longer ages between releases.** Its fixes for SoundCloud and YouTube changes land within
  days, but the images were only ever built during a release, so the downloader could run a yt-dlp
  older than the problem it was hitting. A weekly scheduled pipeline now rebuilds and republishes the
  downloader image from master, and the version floor no longer pins it to a single month.

### Fixed
- **Cookies are read complete rather than as of the last checkpoint.** yt-dlp copies Firefox's cookie
  database and nothing else, while Firefox writes through a log that can hold the most recent cookies
  — including the rotating one the anti-bot layer issues. The profile is now snapshotted and folded
  together before it is read, so what the downloader presents is what the browser actually holds.

## [0.1.1] - 2026-08-02

### Fixed
- **The library scanner failed on every single file.** Genre indexing, added in the previous
  cycle, read a song's genres through a method that does not exist on `BaseSong`, so each file
  raised an `AttributeError` that the scanner caught, logged and moved past. On production 1427
  of 1429 scanner log lines were this one error. The damage went further than missing genres:
  the failure happened before the media-file row was written, and the database connection
  commits as it goes, so tracks and their artists were stored while file modification times
  never were — which left every scan re-reading the entire library from scratch and the genre
  table empty. The scanner now reads genres through the method songs really have. The tests
  missed this because they described a song with a mock that answers to any method name at all;
  they now use a stub limited to the real interface, so an invented method fails in the test
  suite instead of in production.
- **A downloader container respawned every minute, forever.** The SoundCloud full-sweep worker is
  built to do one pass and exit, but was configured to be restarted whenever it stopped — which
  is exactly what it does by design. It had restarted 21 times when this was found. It is now
  left alone once its sweep is done.
- **YouTube downloads had no way to solve the site's JavaScript challenges.** The downloader image
  shipped without a JavaScript runtime, so every video logged that signature solving had failed
  and only the formats needing no challenge stayed reachable. The image now carries the solver
  scripts and Deno to run them. This clears the warnings; it does not by itself lift the
  rate-limiting YouTube is currently applying.

## [0.1.0] - 2026-08-02

### Added
- **Memories: what was released on this day, in earlier years.** The library holds release dates
  it never showed you anything with; the web interface and the Android app now open on a short row
  of them — "Today, 8 years ago" — with a full screen behind it that lists one section per year,
  each playable in one tap. Only tags carrying a complete date can say what happened on a given
  day, so a tag with just a year, or just a year and a month, never appears. A day with no exact
  match widens to three days either side rather than showing nothing, and says "this week" instead
  of "today" when it does, so the heading never claims a precision the tags do not have. The row on
  the home screen can be switched off in settings; the Memories screen itself stays where it is,
  in the web sidebar and in the Android Library tab. Served by one new LMS endpoint,
  `/rest/getMemories`, which both clients read; the device sends its own date, so a phone in
  another time zone gets its own today. Filling in the release dates that are still missing, from
  MusicBrainz or Discogs, is a separate piece of work and is not part of this.
- **Diagnostics can be sent without waiting for a crash.** Crash reporting only fired on the next
  app start, and only after the app had actually died, so the failures that leave the app running
  — a call that returns an error, a screen that stays empty — never reached the server. Settings
  now has "Send diagnostics now" under the Muma section, which uploads the current session's log
  and writes a copy to Downloads/UltrasonicLogs. It sits outside the debug category on purpose,
  because that category is hidden in release builds. Unlike the automatic report it ignores the
  "Crash detection" toggle — pressing the button is consent — and it never deletes a crash file
  that hasn't been reported yet. Manual reports are marked as such in `crash_reports`, so they
  are distinguishable from real crashes and from silent kills.

### Changed
- **The Ratings tab no longer offers a search field.** Every Library tab got the same filter bar,
  but Ratings is not a list the library grows: it is the same five cards ("4 stars and up" down to
  "1 star and up"), all of them on screen at once. Searching five visible cards is busywork, so the
  field is hidden there and stays on the tabs that do grow — genres, labels, years, festivals and
  lineups.

### Removed
- **The "MuMa Sync" screen in Ultrasonic** and its six buttons (log on, load/write tiles,
  clear tiles, load/write settings). Tiles already sync themselves through the tile editor,
  the log-on step already happens when a server is saved, and the settings backup/restore pair was a
  blunt dump of every shared preference that needed an app restart to take effect and could
  overwrite a working install with another device's state. The MuMa user ID and API key
  settings stay — they are what the rest of the app authenticates with. Along with the screen
  went the unused `POST /api/users/{id}/dynamic-playlists/sync` endpoint on the manager, which
  no client had called since the tile editor started writing playlists directly.

### Fixed
- **An artist shortcut on the home screen keeps the blank it was saved with.** The shortcuts grid
  stores whole cards, written once, at the moment the user opens something. An artist saved while
  the server had no picture for them holds an empty cover art id, and an empty id means the card
  never asks for a picture at all — so it stays grey however many pictures have arrived since.
  Such a card now has its artwork looked up and the stored copy repaired, which is one lookup per
  artist, ever. The index conversion also stored an empty string where the artist conversion
  already stored nothing, so a missing id looked like a usable one downstream; both now agree.
- **A cover art the server does not have is not re-requested on every bind.** 0.0.60 made the
  server answer with the artist's own release artwork instead of a 404, so this is now only the
  artists who have no artwork anywhere — but for those, scrolling the home screen back into view
  cost one failed request per card, every time, and the placeholder appeared only after the round
  trip. Their ids are remembered for twelve hours, per app run, and only when the server actually
  answered "not found": a timeout, a 5xx or being offline says nothing about whether the picture
  exists, and caching those would blank out artwork that is perfectly fine.

## [0.0.61] - 2026-08-02

### Added
- **The star button in Android Auto now sets a rating instead of a favourite.** It used to toggle
  the Subsonic favourite flag on and off, which left the five-point rating — the thing the rest of
  the app sorts by, filters on, and shows a five-star widget for — unreachable from the car. The
  button now cycles through six states: an empty star for no rating, then a star carrying the
  digit 1 through 5, wrapping back to empty. Favourites are unchanged on the phone; they lose only
  their car button, which keeps shuffle and repeat out of the overflow menu where they are harder
  to hit while driving.

## [0.0.60] - 2026-08-02

### Added
- **The artist page opens with the artist rather than with a list.** Tapping an artist used to
  land straight on their albums, with the name in the app bar the only thing distinguishing one
  artist from the next — even though the app already downloads and caches artist images and
  already shows the album and track counts one screen earlier, in the artist list. The page now
  starts with a header: the artist image, the name, "12 albums · 143 tracks", the years the
  discography spans, and the genres. The play-all button moved into it and queues the artist's
  tracks the same way the long-press menu's "play now" does. Artists reached through search or
  from a home screen card never went through the cache that holds the counts, so the header
  derives them from the discography on screen instead of showing nothing.
- **Labels are browsable on Android.** The filter modal could already narrow songs down to a
  record label, but nothing showed which labels the library holds — you had to know the name
  before you could filter on it. Labels now sit in the Library tabs next to Genres, fed by the
  same PUBLISHER tag the filter chip uses, and a tap opens that label's tracks.
- **The Android app speaks Sallaands and Brabants**, the same two dialects the web interface
  picked up in 0.0.59, chosen from the language menu that was already in Settings. Neither
  dialect has a language code, so they ride along on Dutch with a region no Dutch speaker has
  set: nl-BQ and nl-CW. Three other shapes were tried first and none of them survive Android's
  resource matching — a three letter code (nds-NL) and a BCP 47 variant (nl-NL-brabant) both
  fall back to the default, and any locale missing from `resourceConfigurations` is stripped
  from the APK before it ever reaches a device.

### Fixed
- **The folder selector no longer sits squeezed into one column** when an album list is switched
  to the grid layout. It was laid out as a single album-sized cell with the first two albums
  beside it; headers now span the full width of the grid.
- **Dutch is complete on Android, and English is actually English.** The Dutch resources were
  163 strings short of the English ones, and 28 strings this fork added were written in Dutch in
  the default resources — so an English-language phone showed "Artiesten", "Jaren" and
  "Goedkeuren". Both are filled in now, which the dialects depend on: Android treats nl-BQ and
  nl-CW as Dutch, so a gap in Dutch falls through to a dialect rather than to English.
- **Artists show a picture on the phone, whether or not one has been fetched for them.** An artist
  without artwork of their own is served from the artist image fetcher, and only 11762 of the
  library's 51378 artists have a picture there so far, so for the rest that request 404s and every
  client — the Ultrasonic home screen, the artist list, the web player — drew its grey placeholder.
  The server now answers such a request with artwork the artist already has: their scanned artist
  image if there is one, otherwise the cover of their earliest release. The cover art id still
  points at the fetcher, so a real artist picture takes over the moment it lands, without any
  client cache holding on to the release cover.

## [0.0.59] - 2026-08-02

### Added
- **The web interface is translated, and speaks Sallands and Brabants.** The translation layer
  landed in an earlier release but had nothing in it: two locale files holding four strings between
  them, and one of 54 components resolving its text through them. Every screen now does — 640 keys
  across the player and the management console, in English and Dutch. The interface was a mix of the
  two languages rather than one of them (the mobile navigation bar rendered "Home", "Nummers",
  "Sets", "Bieb" and "Beheer" side by side), so both files needed new text written for the strings
  that existed in only one language.
- **Sallands and Brabants**, picked from the same language menu. Lookup now walks a per-locale
  fallback chain instead of resolving a missing key straight to English, so both dialects reach
  Dutch first and their files can stay partial: 131 keys each, covering the player side, with the
  management console reading as ordinary Dutch instead of half-English. Neither dialect has a BCP 47
  tag, so both report `nl` to the browser, which is what screen readers and spell-check need.
- **Plural forms**, chosen with `Intl.PluralRules`, so counts no longer read "1 nummers". The form
  is decided by the language the text is written in rather than the active one, so Dutch reached by
  falling out of a dialect still pluralises as Dutch.

### Changed
- Sentences that were assembled from fragments are single translatable strings now, because where a
  noun sits in a sentence differs per language. Labels that lived in plain module state — sort
  options, tab lists, artist roles, scanner step names — hold translation keys, since as data they
  could not follow a language change.
- Text that originates in the backend (worker statuses, health output) is unchanged and stays
  English; translating it would mean changing what the Python services emit.

## [0.0.58] - 2026-08-01

### Added
- **Interface language setting in the web frontend.** The frontend now has a translation mechanism —
  JSON translation files per language (`services/frontend/src/lib/i18n/locales/`), a `t()` store with
  English fallback and `{name}` interpolation — plus a language picker (English/Dutch) in General
  Settings. The chosen language is stored in the per-user `frontend` app-settings blob
  (`/api/users/{id}/settings/frontend`, alongside `favoriteGenres`), so it follows the user across
  devices; a language applied from the account is not written to `localStorage`, so logging out falls
  back to this browser's own preference instead of keeping the previous user's. No backend or database
  change. Only the picker itself is translated so far — converting the remaining screens is a
  follow-up. See `docs/designs/i18n/`.
- **Android: search and sort on the Library tabs.** The Artists and Albums tabs gained a search
  field and a sort selector; artist search runs server-side over the whole library through new
  `query`/`sortBy` parameters on `getArtists.view`, which also reports `songCount` per artist.
  Albums reuse the `query` parameter `getAlbumList2.view` already accepted and gained a
  `byTrackCount` order. The genre, year, festival, lineup and rating tabs filter and sort in
  memory.

### Changed
- **Server administration moved out of the player's settings screen and into the management view.**
  The scanner (status, schedule, tag handling) and the media libraries are now management tabs of
  their own, so everything that requires an administrator lives in one place. The player's settings
  are personal settings only: general, advanced and about. The two separate scanner screens that
  both polled `getScanStatus` on their own timer are merged into a single tab that only polls while
  a scan is actually running.
- **Subsonic API tokens are issued by an administrator**, from the user detail panel in the
  management view, instead of every user minting their own in two different places. The music
  server exposes them at `/muma/api/admin/subsonic-token`, which requires Subsonic admin
  credentials.
- **The about page is written for listeners**: the running version and the release notes, without
  the developer-oriented links.
- Scrobbling to the central MuMa database is on for every user. It was a per-user toggle that the
  player's settings screen could set, which is not something individual users should opt out of.
- `store.js`'s account sync was generalised into `loadFrontendSettings`/`saveFrontendSetting`, which
  read-merge-write a single key of the `frontend` app-settings blob; `favoriteGenres` now goes through
  them and both settings are loaded in one request on login. No behaviour change for favorite genres.

### Removed
- **The "Audio (Web Player)" settings block.** Transcoding mode/format/bitrate and the ReplayGain
  settings were never read back by `getUser`, never written by `updateUser`, and never consulted by
  the player (which hardcodes its own stream parameters), so saving them silently did nothing.
- **The user administration screen in the player's settings.** It wrote straight into the music
  server's own user table, which the MuMa user sync then overwrote; the management view's user tab
  is the single place where users are managed. Its non-functional "Scrobbling enabled" checkbox
  (never read by `createUser`/`updateUser`) is gone with it.
- **The ListenBrainz import button in the player's settings.** Importing listening history is an
  administrative job and already exists, per user, in the management view's scrobble tab.

### Fixed
- An unset album sort method no longer makes the settings screen fall back to `107`, which is not a
  valid `ReleaseSortMethod` and was written back to the database on the next save.
- **`Track::getCount`/`Release::getCount` returned one row per matching entity instead of a
  single total.** Both classes' private query builders (`createQuery` in `Track.cpp` and
  `Release.cpp`) applied `GROUP BY` unconditionally, including on the aggregate `COUNT` select
  `getCount` builds, which turned its single-row result into one row per entity and made
  `fetchQuerySingleResult` throw whenever the query also needed to deduplicate joined rows (e.g. a
  keyword filter, or `Release`'s new `TrackCountDesc` sort). Both now take an explicit `aggregate`
  flag and only apply `GROUP BY` when it is false.
- **`Dockerfile-build-alpine` could produce a "passing" image with a failing test suite.** It ran
  `make test && ...;` where the trailing semicolon broke the `&&` chain, so a failing CTest suite
  no longer failed the build, and `scripts/test/lms-unit.sh` reported green regardless.
- **Android: tapping an artist opened a blank screen.** The artist list and the home screen's
  artist cards navigated to a stub fragment that had no layout and loaded no data. Both now open
  the artist's album list, the destination search and the player's "show artist" already used.


## [0.0.57] - 2026-08-01

### Fixed
- **The Android About page still linked to upstream Ultrasonic.** "Visit webpage" opened
  `ultrasonic.gitlab.io` and "Report a bug" opened `gitlab.com/ultrasonic/ultrasonic/issues`,
  neither of which has anything to do with this fork. They now point at `https://muma.example.com`
  and the project's own issue tracker at
  `https://gitlab.example.com/muma/music-management/-/issues`.

## [0.0.56] - 2026-08-01

### Fixed
- **Ultrasonic crashed as soon as Settings was opened.** `SettingsFragment` sets every list
  setting's summary to its selected entry, and `ListPreference.getSummary()` runs that summary
  through `String.format()` to substitute the entry into it. The interface size options shipped in
  0.0.55 are the first entries in the app containing a literal `%` ("100%", "90%", ... "70%"), so
  the summary became an invalid format string and binding that row threw
  `UnknownFormatConversionException: Conversion = '%'`, killing the process. The `%` is now
  escaped. It affected every install rather than only upgrades: the preference persists its default
  while the screen inflates, so the summary is applied the first time Settings is opened.
- **Robolectric could not see the app's own resources**, because `includeAndroidResources` was
  never enabled, so any test touching a real screen failed with `Resources$NotFoundException` and
  none existed. Enabling it is what made the Settings crash reproducible in a test.

## [0.0.55] - 2026-08-01

### Added
- **Radio mode (beta): one server-owned programme, any number of listeners in sync.** The server
  publishes a timeline of tracks with absolute `started_at` timestamps and a scheduler keeps it
  filled ten minutes ahead, so a channel plays with nobody listening and a late joiner lands mid-track
  at the right spot. Clients never push state: they measure their clock offset against a DB-free
  `/api/radio/time`, derive `position = serverNow - started_at`, and close drift with a hard seek
  above 3 seconds or an inaudible `playbackRate` nudge below it. Available in the web player and as a
  "Radio" entry in Android Auto, where skip and seek are removed from the player commands so the car
  greys them out. One channel (`main`, whole library) ships enabled; the schema already carries a
  `genre` per channel, so genre channels need a row rather than a migration. See `docs/radio-mode.md`.

### Fixed
- **Jam followers wiped the host's play position.** The reactive push effect ran for followers too,
  and a follower's `savePlayQueue` call omits `position`, which the server stores as `0`
  (`handleSavePlayQueueCommon` reads it as `value_or(0)`). Every follower echo therefore reset the
  host's progress to the start of the track and its `playing` flag to false — the "jumping" that made
  the old sync modes unusable. Only the host writes state now; followers still send explicit
  play/pause/next/previous commands.

- **Library Browser, replacing the Library, Advanced Library and Statistics tabs.** One view over the
  collection with facet filters for genre, label, artist, BPM range and release year that intersect,
  distributions that follow the active filter, and a header reporting how much of the current selection
  actually has BPM, genre and artist data — so a thin histogram is not mistaken for a thin collection.
- **`/api/analytics` endpoints for filtered aggregations:** summary with data coverage, genre
  distribution, BPM and release-year histograms, top artists, top labels, and artist type-ahead. The
  path names the metric and the query parameters name the scope, so an artist's BPM spread is
  `bpm-histogram?artist=X` rather than a new endpoint. A later player page can reuse them unchanged.
- **The scanner now indexes genres from file tags into `library_track_genres`.** It already read every
  file's tags for artist, label, title and duration and simply skipped genre, although
  `BaseSong.genres()` returns it — which is why LMS knew genres the management UI did not. Resolution
  goes through `GenreRulesHelper`, so approved genres index under their curated name, rejected ones are
  dropped, and genres awaiting curation index under their raw name and are grouped separately in the
  sidebar.

### Fixed
- **`/api/library/advanced` returned HTTP 500 for every request.** It selected `musical_key`, `energy`,
  `danceability`, `valence` and `popularity`, none of which exist in the database: `db_init.py` lists
  them in a `CREATE TABLE IF NOT EXISTS` that is a no-op against an existing table, and no `ALTER TABLE`
  exists anywhere. The frontend never checked `res.ok`, so that failure rendered as "no tracks found" —
  which is how a completely broken page stayed invisible. The columns are removed rather than added,
  since nothing writes them.
- **`/api/library/genres` always returned an empty list**, because it joined `rules_genres` against
  `library_track_genres`, a table with no rows. The genre sidebar was therefore always empty and the
  genre filter always matched nothing.
- **`library_track_genres` was never created on a fresh database.** Its `CREATE` names a foreign key to
  `rules_genres` but ran before that table existed, and the failure was swallowed by a debug-level
  `except`. It survived in production only because an older migration had created it.
- **The duration column in the track list always showed `-`.** The frontend rendered
  `track.duration_secs`, which the query never selected.

### Changed
- **Popular genres now count curated genres instead of machine-learning predictions**, so the figures on
  Overview change. `top_genres` previously unioned `library_track_genres` with `ml_genre`, which was
  harmless only while the first table was empty; once it has rows, a track carrying the same genre in
  its tag and its prediction would be counted twice.
- **Dynamic playlist previews match more tracks**, since their genre rules no longer fall back to
  machine-learning predictions alone. This affects the preview in the web UI only; Ultrasonic resolves
  its playlists elsewhere.

### Migration
- Run `POST /api/scanner/scan/all?force=true` once after deploying, to populate `library_track_genres`
  for the existing library. The scanner skips files whose size and modification time are unchanged, so
  without the forced run only files touched later get genres. Genre coverage in the browser header
  shows the progress; before the scan it reads 0%.

- **Android: an "Interface size" setting, defaulting to 75%.** Ultrasonic's rows and type were about
  a quarter larger than Spotify's, so noticeably less fit on screen. The layouts hardcode dp values,
  so the scale is applied by wrapping the activity's context with a reduced `densityDpi` instead of
  touching ~60 layout files. See `services/ultrasonic/ultrasonic/src/main/assets/CHANGELOG.md`.

- **The Artist Images tab is now a real image manager.** Per artist you can let it search
  automatically, upload a file, paste an image URL, remove the current image, or promote one of the
  previously fetched images to primary. Results can be filtered on all / with image / without image
  and are paged, and a new `/api/artists/manage/search` endpoint returns every matching artist —
  with or without an image — in a single call.

### Fixed
- **Searching in the Artist Images tab no longer shows an empty page.** The tab assigned any
  response body straight into its result list, so an error response (or a name containing `&` or
  `#`, which was never URL-encoded) produced a page with neither results nor a message. It now
  checks the response, reports the backend's error with a retry button, and debounces typing.
  See `docs/bug-reports/022-artist-images-tab-search-shows-nothing.md`.

- **Ultrasonic: favorite genres, shared with the web player.** Long-press a genre in Library →
  Genres to add or remove it; favorites get a star and sort above everything else. It is the same
  list the web UI keeps (`favoriteGenres` in the per-user `frontend` settings blob), so both clients
  agree, and a local copy keeps it working offline.
- **Ultrasonic: a Favorites folder in Android Auto**, holding favorite genres and the dynamic
  playlists you starred. A genre plays straight from the folder instead of asking for a year and a
  sort order first. The folder is hidden when there is nothing in it.

### Changed
- **Ultrasonic: the default tiles on Songs/Livesets are era tiles now.** The eight tiles that
  filtered on a single genre added nothing next to the genre list, which gets you the same result on
  its own. In their place three combinations the genre list cannot express in one go: Hardstyle
  Classics (Mainstream Hardstyle, 2009-2017), Millennium Hardcore (Mainstream Hardcore, 2010-2015)
  and Early Uptempo (Uptempo Hardcore, 2012-2017), each in random order. Existing installs keep the
  tiles they already have.

## [0.0.54] - 2026-08-01

### Fixed
- **`migrate_v2.sql` fought `migrate_v3` on every deploy.** It re-created the unique key on
  `rules_genres.name` that v3 deliberately drops in favour of one on `normalized_name`, so a deploy
  failed with `Duplicate entry ... for key 'name'` on rows v3 had legitimately created. It also
  shrank `name` back to `VARCHAR(100)` each time, truncating long genre names. Both statements are
  removed; v3 now owns that schema. Every migration re-runs on every deploy, so an older file is not
  history — it keeps being re-asserted.

### Added
- **A genre can now be corrected to more than one genre.** Contractions expand instead of being thrown
  away: `Upterror` becomes `Uptempo Hardcore` plus `Terror`. Targets live in the new
  `rules_genre_expansions` table and the curation page offers a multiple choice; `canonical_id` stays
  as a legacy column that the tagger no longer reads, so one place decides a rewrite instead of two.

### Fixed
- **`Hardstyle/Hardcore` was treated as a single genre.** `Tag.resplit` claims to split on `/`, but it
  only runs when `Tag.regex` changed something and `ARTIST_REGEX` never matches a slash, so composites
  arrived whole and filled the curation queue with combinations that never repeat. Genres are now split
  on `/` and each part is judged on its own. The split is genre-only — artists keep their slashes
  (`AC/DC`) — and a genre that has been decided on is never split, so approving a name that genuinely
  contains a slash protects it permanently.
- **Slash genres that only the migration approved are split automatically.** `migrate_v3` whitened every
  pre-existing row, which would otherwise have protected exactly the composites worth splitting.
  `migrate_v4_genre_expansions.sql` turns those into a rejected genre expanding into its parts, and
  leaves anything a human decided untouched.

### Added
- **Artist name analysis, as a dry run.** `ArtistNameAnalyzer` turns a raw artist string into a
  proposal — keep, rewrite, split, reject, or no answer — with the reasoning attached, and
  `tools/artist_curation_report.py` runs it over the whole artist list and prints what would happen
  without changing anything. Handles noise around a real name (`**FREE DOWNLOAD** DJ KURT`), names
  glued together (`AngerfistHeadhunter`), misspellings, and sentences a tagger rule mistook for an
  artist. An unrecognised name is never removed: real artists exist that no streaming service lists.
  Every threshold is configurable, because what counts as good enough can only be judged from a report
  over the real library. No schema, tagger or UI change yet.

### Changed
- **Artist analysis defaults, corrected by the first run over the real library.** Names are no longer
  removed for looking like a sentence: `Boaz Van De Beatz`, `We Are Loud` and `The Beholder
  (Neophyte)` are real artists that score exactly like a stray quote, so the signals are reported and
  the name is flagged instead. Splitting glued names is off by default after it took `Technotronic`
  apart into `Techno` + `Tonic`. Matching is blocked by first character and length, without which a
  51k-name run did not finish in twenty minutes.

### Fixed
- **Artists in non-Latin scripts are no longer proposed for deletion.** The letter check was
  `[A-Za-z]` and the normalisation key was `a-z0-9`, so every Cyrillic name counted as having no
  letters and collapsed to an empty key.

## [0.0.53] - 2026-08-01

### Fixed
- **The genre curation migration never reached production.** `.gitignore` ignores `*.sql`, so
  `migrate_genre_states.sql` was silently never committed and 0.0.52 ran against the old
  `rules_genres` schema: the curation page errored and the tagger quietly stopped writing genres.
  Root-level migrations are now exempt from the ignore rule, the file is committed as
  `migrate_v3_genre_states.sql`, and `scripts/deploy.sh` globs `migrate_*.sql` so its naming rule
  matches `.gitignore`'s exactly. See `docs/bug-reports/021-genre-migration-never-shipped.md`.
- **The migration no longer aborts on genres that differ only in punctuation.** Production had the
  same genre stored three times, which cannot coexist under the new unique key. It now merges them
  itself — lowest id survives, artist, label, track and correction references are repointed — and
  reports the count into the deploy log, instead of requiring a manual pre-check before an
  unattended deploy.
- **A failed database migration no longer reports a successful deploy.** The remote command ended
  with `rm`, so its exit status masked the one from `mysql`.

## [0.0.52] - 2026-08-01

### Added
- **A curation state per genre.** `rules_genres` now records whether a genre is kept (`white`),
  dropped (`black`) or still awaiting a decision (`unknown`), plus an optional correction target, so
  `uptempo` can be rewritten to `Uptempo Hardcore` while `Arts` is simply removed. Genres nobody has
  judged are counted and listed for review instead of being applied.
- **Curation API.** `GET /api/rules/genres` returns genres by state, most frequently seen first
  (`state=unknown` is the review queue), and `POST /api/rules/genres/{id}/decide` records a decision
  together with who made it, so the tagger never reverses it later.
- **Genre Curation page in the management UI.** A new tab that opens on the unjudged queue, most
  frequent genre first, and approves, rejects or corrects a genre per row. Every row states in words
  what the genre currently does to a tag, corrections can only point at an approved genre, and
  decisions on already-judged genres can be reversed from the same screen.

### Changed
- **One rule decides a genre instead of two.** `AddMissingGenreToDatabaseRule` and
  `CleanAndFilterGenreRule` are replaced by `ResolveGenreRule`, which performs a single lookup and a
  single decision per genre. Unknown genres are left on the file untouched rather than written into
  the library.

### Fixed
- **Unknown genres are no longer approved the moment they are detected.** The two rules above ran back
  to back: the first added an unknown genre to the backlog, the second accepted any genre found in
  that backlog. Every genre the tagger had ever seen therefore became valid, and the backlog only ever
  grew. Existing whitelist, ignore list and backlog entries are migrated to their equivalent state by
  `migrate_v3_genre_states.sql`.

## [0.0.51] - 2026-07-31

### Added
- **Ultrasonic: a "Log out" entry in the toolbar overflow menu.** Signing out previously meant
  clearing the app data or reinstalling. It confirms first, stops playback, clears the password,
  the MuMa API key and the stored MuMa tokens, and returns to the login screen with the username
  prefilled. Downloads stay on the device.
- **Ultrasonic: skeleton placeholders on the home screen.** Each section shows pulsing grey cards in
  the shape of the content that is loading, and swaps them for real cards on its own, so a slow
  section no longer holds up the ones that are ready. Returning to the home screen refreshes it
  without flashing skeletons over content that is already there.

### Changed
- **Ultrasonic: the home screen loads its sections concurrently.** Both library carousels fetched
  artists, albums and labels/festivals one after another, and the screen waited for every section
  before drawing anything — six sequential round trips before the first pixel. The sources now run
  in parallel and each section publishes as soon as it is ready.

### Fixed
- **Ultrasonic: a password rejected mid-session now returns to the login screen.** When the password
  was changed on the server (or an API key revoked) while the app was running, every screen failed
  with an error the user could not act on and the app never asked for credentials again. Subsonic
  error 40 now ends the session and shows the login screen with an explanation. Permission ("not
  authorized") and "not found" errors deliberately do not log anyone out.

## [0.0.50] - 2026-07-31

### Security
- **The tagger, scanner and ListenBrainz-import endpoints now require an API key.** `POST
  /api/tagger/tag/all`, `/tag/file`, `/tag/stop`, `POST /api/scanner/scan/all`, `/scan/file`,
  `POST /api/scrobbler/import/listenbrainz` and `GET /api/scrobbler/import/latest` had no
  authentication at all — anyone who could reach the API could start a full re-tag of the library,
  which rewrites tags in the actual music files. This went unnoticed because Cloudflare Access sat
  in front of `muma.example.com` externally; the moment that had to be bypassed so the mobile
  app could log in from outside the LAN, they became publicly reachable. The `/health` endpoints
  stay open for monitoring. See `docs/bug-reports/020-new-user-cannot-log-in-android.md`.

### Fixed
- **Ultrasonic login screen no longer blames the connection for a rejected password.** The welcome
  dialog already probes the server to tell an outage apart from bad credentials, but then showed
  "Could not connect to LMS" on the branch where the server *had* answered — so a wrong (or
  non-existent) account looked like a server outage. That case now says "Wrong username or password
  ... or ask the administrator for an account".
- **Ultrasonic Google Sign-In failures now name their cause on screen**, not only in logcat: the
  concrete exception class or HTTP status is shown in the error text, so a remote user's screenshot
  is enough to tell a Play Services refusal apart from an unregistered signing certificate or an
  OAuth client misconfiguration.
- **CI debug APKs are signed with the real keystore when it is available.** Previously only release
  builds got `SIGNING_STORE_FILE`, leaving debug builds signed by a throwaway keystore generated
  inside the ephemeral build container — a different certificate every build, so their SHA-1 could
  never be registered as an Android OAuth client and "Sign in with Google" could never work on a
  debug APK from apk-hoster. See `docs/bug-reports/020-new-user-cannot-log-in-android.md`.
- **Batch pacing settings were never applied**: `DownloaderService` never passed its keyword
  arguments, so `max_workers`, `burst_size`, `min_pause` and `max_pause` always sat on their
  defaults — a pause of one to five seconds between batches.
- **SoundCloud never throttled between batches**: `_throttle()` existed but was only called by the
  YouTube downloader.
- **YouTube did not recognise a 429 at all**: it fell through to the generic branch and slept
  `5 * attempt` seconds.
- **Backoff state was lost on restart**: the 403 counter lived in a module global and 429 had no
  counter at all, so a container restart resumed at full speed.
- **`POST /api/config` always failed**: it called `config_store.update_many()`, which does not exist
  on `ConfigStore`. The resulting `AttributeError` was swallowed by a broad `except` and returned as
  a 400, so saving a setting over the API could never work.
- **Ultrasonic release builds crashed on nearly every playback start.** `Converters.toStringList`,
  `MediaItem.toTrack()` and `TileStorage` built their Gson type from an anonymous Guava `TypeToken`
  subclass. Guava ships no consumer ProGuard rules, so with `android.enableR8.fullMode=true` R8
  merged away the parameterized superclass those tokens read at runtime and the constructor threw
  `IllegalArgumentException: class com.google.common.reflect.TypeCapture isn't parameterized`. It
  fired from `onTimelineChanged`/`onMediaItemTransition` and accounts for 15 of the 16 crash reports
  collected on 6.5.14 through 6.5.18. All three now deserialize through `Array<T>::class.java`,
  which needs no runtime generic signature, with keep rules for the Guava `TypeToken` hierarchy as
  a second line of defence.
- **An Ultrasonic error raised while no Activity was available took the app down.** `InfoDialog`/
  `ErrorDialog` built their `MaterialAlertDialogBuilder` in the constructor, outside the existing
  try/catch, so a context without an AppCompat theme threw instead of failing to show a dialog. The
  builder is now created lazily against a themed context, with a toast fallback. A global
  `RxJavaPlugins` error handler also stops a throw inside an RxBus subscriber from killing the
  process.
- **Android Auto kept a dead or offline `MusicService`.** The media session resolved it once at
  construction and held that instance for the process lifetime, so a server switch, a credential
  edit, or `getMusicService()` returning the offline service left Auto browsing empty lists forever
  while the phone UI worked. Auto now resolves the service per call.

### Added
- **Downloader timing is configurable from the UI**: a new *Timing* tab under
  Systeembeheer → Downloaders exposes the sweep interval, per-account cooldown, batch size,
  pauses, yt-dlp sleeps, rate limit and backoff ladders for SoundCloud, YouTube and Telegram.
  The settings live in the new `downloads_settings` table rather than in `ConfigStore`, because
  the manager and the worker containers mount different host directories for `/app/data` and so
  do not share `config.json`.
- **Self-regulating backoff that survives a restart**: a 429 now doubles a per-source multiplier
  and parks that source until a cooldown expires, both stored in `downloads_rate_state`. The
  multiplier stretches every wait time, and halves again after enough clean sweeps. The Timing tab
  shows the current multiplier, when the source wakes up and when the last 429 was, with a reset
  button. Exposed over `GET /api/downloaders/rate-state`.
- **Per-account check schedule**: `downloads_account_checks` records when each account was last
  visited, so a sweep only touches accounts past their cooldown instead of all of them every time.

### Changed
- **SoundCloud is swept far less aggressively by default**: the workers used to run
  `--repeat --sleeptime 300`, so every SoundCloud account was queried every five minutes. The
  interval now comes from the settings (default 15 minutes) and each account has its own six-hour
  cooldown on top, which is roughly 72 times less traffic before the self-regulation even starts.
  `--sleeptime` remains as an explicit override for manual runs.
- **The 403 ladder is now configurable**: the hardcoded 240 / 1800 / 10800 / 21600 / 43200 / 86400
  sequence is replaced by a geometric one with a configurable base, factor and cap
  (240 / 960 / 3840 / … by default).
- **A rate limit no longer blocks a worker thread**: SoundCloud used to `time.sleep()` for up to two
  hours inside the thread pool. The wait is now recorded in the database and the sweep ends instead.
- **Telegram reads ConfigStore** instead of `os.getenv`, and takes its concurrency and flood
  threshold from the timing settings. A Telethon flood wait is treated like a 429.

## [0.0.49] - 2026-07-31

### Added
- **Ultrasonic Beheer tab**: a fourth bottom-bar tab mirroring the web UI's management section
  (`services/frontend/src/lib/management/`), starting with Downloaders (SoundCloud accounts and
  YouTube channels), Gebruikers (list, enable, disable) and Verzoeken (approve, unapprove, reject,
  filtered by status). Like Library it is a pager, so the web UI's remaining management tabs can
  follow as pages rather than screens.
  The tab is hidden unless `/api/auth/verify` says the stored API key belongs to an admin, and stays
  hidden while that answer is pending or the check fails. That is presentation only — every endpoint
  behind it is already guarded by `require_admin()` server-side.

### Added
- **Ultrasonic Library gains four tabs**: Jaren, Festivals, Lineups and Ratings, alongside the
  existing Playlists, Genres, Artiesten, Albums and Opgeslagen. Every source already existed and was
  already used by the filter modal, so this adds no API surface. Lineup browsing in particular
  returns a capability that had been lost.

### Changed
- **Ultrasonic: in sets mode the home carousels show festivals instead of labels.** Livesets are
  festival recordings, so a record label says nothing about them.
- **Ultrasonic: the five list-shaped Library pages now share one `FilterBrowseFragment`** driven by
  a `BrowseCategory` enum, replacing `GenreListFragment`. Adding a browse dimension is now an enum
  value and a loader branch rather than a fragment.

## [0.0.48] - 2026-07-31

### Fixed
- **Ultrasonic: opening an artist from the home screen showed nothing.** `getArtistList` defaults its
  `role` parameter to `all`, so the carousels listed every artist link in the library — remixers,
  featured artists, composers — most of which have no albums of their own and therefore an empty
  detail screen. The client now asks for `role=release`.
- **Ultrasonic: opening a label from the home screen showed nothing.** `getLabelList` returned
  `db::Label` names, which come from `release_label`, while song filtering matches the PUBLISHER
  cluster — a different table fed by a different tag. The endpoint now reads the PUBLISHER cluster,
  so the names it returns are the ones filtering understands. `ClusterSortMethod` gains `AddedDesc`
  and `LastWrittenDesc`; the `LabelSortMethod` additions from 0.0.46 are removed again.
- **Ultrasonic: artist pictures on the home screen.** Artist art is keyed with
  `FileUtil.getArtistArtKey` again and requested at the large size, so it is shared with the rest of
  the app instead of being refetched under a key nothing reads. Missing artist cover art now becomes
  null at the converter instead of an empty string that looked like a usable id.

## [0.0.47] - 2026-07-31

### Added
- **Ultrasonic Library tab**: one bottom-bar tab holding every browse-by-type screen — dynamic
  playlists, genres, artists, saved playlists and albums — as swipeable pages under a tab strip.
  Adds `GenreListFragment`, the only new screen; the other four pages are the existing fragments,
  now hosted instead of navigated to.

### Fixed
- **Browsing was unreachable in 0.0.46**: the home screen rebuild removed the filter chip row, which
  was the only entry point to dynamic playlists, genres, the album list and the artist list. Since
  dynamic playlists are also created from that screen, there was no way to make one at all. The
  Library tab restores every one of them.
- **The Favorites tab showed a copy of the home screen**: it was the home screen with the favorites
  filter chip pre-selected, so removing the chips left it identical to Home. It is now its own
  screen with starred albums, starred artists and tracks rated four stars or better.

### Changed
- **Ultrasonic bottom navigation is now Home, Library and Favorieten.** Search left the bottom bar
  because the toolbar already carries a search field; playlists moved into Library.

## [0.0.46] - 2026-07-31

### Added
- **Rebuilt Ultrasonic home screen**: the Android home screen is now a Spotify-style shortcuts grid
  of the eight items you most recently opened (albums, artists, labels, static playlists and
  dynamic playlists), followed by a "Recently updated" and a "Recently added" carousel covering
  artists, labels and albums. All sections render from one generic card model and one reusable card
  component, so future sections need no new UI. Shortcuts are stored whole, so the grid renders
  instantly and offline instead of refetching every item on each visit. Adds a "Separate home
  history per mode" setting that controls whether songs and livesets keep separate histories.
- **LMS: `getLabelList` endpoint and label recency sorting**: labels can now be ordered by how
  recently their music was added to or rewritten in the library (`Label::findIds` with the new
  `AddedDesc`/`LastWrittenDesc` sort methods). `getAlbumList`/`getAlbumList2` gained a matching
  `type=updated`.

### Removed
- **Ultrasonic home screen filter chips** (Recent / Favorites / New / Genres / Playlists) and the
  old per-type "recently played" lists they drove. Genres remain browsable elsewhere in the app.

## [0.0.45] - 2026-07-30

### Added
- **Label tab and label search in the web UI**: labels are now a first-class way to browse the
  library, alongside artists and genres. Adds a Label entry to the sidebar and dashboard, lets the
  search bar match labels, and renders label hits in the search results. Backed by new Subsonic
  endpoints in the LMS server (`Browsing.cpp`/`Spotify.cpp`) so the mobile clients can use the same
  data.
- **Android crash log reporting for background playback crashes**: the app now keeps an always-on,
  disk-backed ring buffer of recent log output, marks clean playback-service shutdowns so a
  silent kill by the OS can be told apart from a normal stop, and on the next start detects a
  pending crash, combines the stacktrace and ring buffer into a single report, and uploads it. Adds
  the backend upload endpoint and the matching Muma API client call. This exists because
  background-playback crashes leave no trace the user can hand over.
- **`scripts/vw.sh`**: wrapper for on-demand password manager CLI access.

### Changed
- **Simplified Android navigation**: the nav drawer is gone; its items moved into the toolbar
  overflow menu. The bottom navigation now carries a Favorieten tab and no longer carries Downloads,
  and Bookmarks got an entry point on the Playlists screen.
- **AGENTS.md now requires asking which environment to use before querying live data**, so a
  read-only question can't silently end up pointed at production.

### Fixed
- **CI browser tests killed each other when two pipelines shared a runner**:
  `scripts/test/frontend-browser.sh` already picked free ports for the manager and LMS containers,
  but the Playwright dev server stayed hardcoded on 5174 with `--strictPort` and
  `reuseExistingServer: false`, so concurrent jobs failed with
  `Error: http://localhost:5174 is already used`. This took out the label-tab and crash-log merge
  requests and the 0.0.43 tag pipeline as false failures. The script now picks a third free port and
  exports it as `MUMA_TEST_PORT_FRONTEND`, which `playwright.config.js` uses for the base URL, the
  dev server command and the readiness URL, falling back to 5174 for local runs.
- **Ultrasonic failed to compile once crash reporting landed**: `MusicService` gained
  `uploadCrashReport()`, implemented in `RESTMusicService` and `OfflineMusicService` but not in the
  `CachedMusicService` decorator. Crash reports aren't cacheable, so it now delegates straight
  through to the wrapped service, matching `scrobble`/`star`/`saveMumaSettings`.

## [0.0.44] - 2026-07-30

### Fixed
- **`ultrasonic:build-release` was silently skippable on `release/*`**: the job had a
  `changes: - services/ultrasonic/**/*` filter, so a release branch that didn't happen to touch
  `services/ultrasonic/` would skip the official, signed Ultrasonic build+upload entirely — contrary
  to `docs/release-management.md`'s job-to-branch mapping, where `ultrasonic:build-release` is meant
  to run unconditionally on `release/*` (same as `release:build-images` and `deploy:prod`, neither of
  which has a `changes` filter). The optional, manual debug build on merge requests
  (`ultrasonic:build-debug`) was already correct and is unchanged. Removed the `changes` filter so
  the official build+upload always runs on `release/*` when the required secrets are present.

## [0.0.43] - 2026-07-30

### Added
- **Ultrasonic welcome dialog is now full-page, with a secondary "skip login" action**: previously,
  if both Google Sign-In and manual username/password login failed (e.g. server down, misconfigured
  Google OAuth client), the welcome dialog (`NavigationActivity.showWelcomeDialog()`) had no way to
  dismiss without a successful login (`setCancelable(false)`, no close affordance) - a hard lockout.
  Added a small, de-emphasized, confirmation-gated close ("X") button that switches to the app's
  existing offline mode (`ActiveServerProvider.OFFLINE_DB_ID`) instead of writing any credentials,
  so the same dialog naturally reappears on the next app start to try again. Also added an
  always-visible connectivity status line at the bottom of the dialog (reachable/unreachable/
  checking, via the existing unauthenticated `isServerReachable()` probe from `0.0.40`) so it's
  clear before even submitting anything whether a problem would be the server or the login itself.
- **App-wide offline-mode banner**: whenever the active server is the offline pseudo-server -
  whether reached via the new skip button or the existing manual "Offline" entry in the server
  selector - a banner now appears below the toolbar ("Offline mode — limited functionality. Tap to
  log in.") so degraded functionality is never silent. Tapping it reopens the welcome dialog.

### Fixed
- **Google Sign-In failures were hard to diagnose remotely**: `performWelcomeGoogleSignIn()` now
  logs the concrete exception class for Credential Manager failures and the HTTP status/body for a
  failed `/api/auth/google` call, instead of only a generic message. Investigated a report of
  Google Sign-In failing again on the release APK after previously working
  (`docs/bug-reports/019-google-signin-release-regression-external.md`) - no application code
  regression was found (every Google Sign-In code path is unchanged since `0.0.40`, and every prior
  Google Sign-In bug, 009-013, remains fixed); the likely cause is external (Google Cloud Console
  OAuth client registration or a Google Play Services behavior change on the affected device),
  which this release cannot fix directly but is now easier to confirm from device logs.
- **Ultrasonic 5-star rating hidden behind the album art on the Now Playing screen**: `current_playing.xml`
  gave the album art `ShapeableImageView` `a:elevation="12dp"` (for its Material shadow) while the sibling
  `song_rating` star row stayed at the default elevation. Android's view elevation controls Z-order
  independent of XML declaration order, so the album art always rendered on top of the rating row,
  making it impossible to tap a star. Gave the `album_art_inside` container a higher elevation (`13dp`)
  so the rating row draws above the art again. Also added a manual (opt-in) `ultrasonic:build-debug`
  pipeline rule for non-default branches, so a debug APK for a specific MR can be built and installed
  to verify a fix like this one against prod before merging.
- **Web player: mobile mini player had no rating control at all**: the 5-star rating in
  `services/frontend/src/lib/Player.svelte` only existed in the desktop layout branch; the mobile
  mini-player rendered no rating UI whatsoever. Added a compact 5-star row next to the track title/artist
  for parity with desktop.

## [0.0.42] - 2026-07-30

### Fixed
- **Re-deploy 0.0.41 after its own `deploy:prod` job failed (`bug 018`)**: `release/0.0.41`'s MR
  merged into `master` while its own, still-running full pipeline's `release:build-images` job was
  still going — because GitLab associated the MR's mergeability with a smaller, faster duplicate
  pipeline for the same commit rather than the full one. `release:back-merge-develop` then deleted
  the (already-merged) `release/0.0.41` branch as usual, so by the time the full pipeline reached
  `deploy:prod`, `git fetch`/checkout for that branch failed outright (`fatal: couldn't find remote
  ref refs/heads/release/0.0.41`) — production was never actually redeployed with 0.0.41's artist-
  images fix, even though `master`/`develop` and the `release-v0.0.41` tag were correct. No
  functional code change in this release — this is purely the automated re-deploy of 0.0.41's
  already-merged fix. See
  [docs/bug-reports/018-release-branch-deleted-before-own-deploy-prod-ran.md](docs/bug-reports/018-release-branch-deleted-before-own-deploy-prod-ran.md).

## [0.0.41] - 2026-07-30

### Fixed
- **Artist images (profile photo, similar artists, ...) rendered as a black square**: `/rest/getCoverArt`'s
  MuMa-artwork proxy (`handleGetCoverArt` in `services/music-management-server/src/libs/subsonic/impl/endpoints/MediaRetrieval.cpp`)
  only stripped a `/api` suffix from the `music-management-api-url` *fallback* config key, not from
  the primary `music-management-url` key — which is documented/used *with* a `/api` suffix. Whenever
  the primary key was set (the normal case), the resulting base URL kept its `/api` suffix, and the
  outgoing request became `.../api/api/artists/.../image` — a double-prefixed URL that failed at the
  connection level (a `502` from the proxy itself, not a `404` from MuMa). Applied the same stripping
  `MumaResource.cpp`'s constructor already does correctly, for either config key. Affects every artist
  whose artwork only exists via MuMa's cache (no native LMS artwork) — the common case. See
  [docs/bug-reports/017-getcoverart-muma-url-double-api-prefix.md](docs/bug-reports/017-getcoverart-muma-url-double-api-prefix.md).

## [0.0.40] - 2026-07-30

### Added
- **Ultrasonic welcome dialog now distinguishes "server unreachable" from "login failed"**:
  both the manual username/password submit and "Sign in with Google" previously collapsed every
  failure (a real network/server outage, wrong credentials, an expired Google OAuth client, an
  unexpected response shape, ...) into the same generic message. Added an unauthenticated
  reachability probe (`NavigationActivity.isServerReachable()`, a `/rest/ping.view` request with
  its own short 5s timeouts) that runs whenever a login attempt fails, so the dialog can now show
  a distinct "kan de server niet bereiken" message when the server truly isn't reachable, versus
  a "login mislukt" message when the server responded but the login itself didn't succeed.
- **Favorite genres now saved per user in the web player**: previously `favoriteGenres`
  (`services/frontend/src/lib/store.js`) only lived in the browser's `localStorage`, so it was lost when
  switching devices/browsers or reinstalling. Now synced to the user's account via the existing generic
  `GET/POST /api/users/{id}/settings/{app_id}` endpoints (`app_id = 'frontend'`, already used by
  Ultrasonic for its own settings backup) — no backend changes needed. Loaded automatically on login;
  a user's pre-existing local-only favorites are uploaded on first login after the update so nothing is
  lost. Logging out clears the locally-shown favorites so they aren't shown to the next browser user.
  See [docs/designs/favorite-genres/](docs/designs/favorite-genres/).

### Fixed
- **Ultrasonic's welcome-dialog login test could silently "succeed" without ever contacting the
  server**: `MusicServiceFactory.getMusicService()` falls back to `OfflineMusicService` - whose
  `ping()` is a no-op that always returns without error - whenever "Auto-switch server
  online/offline" is enabled and a `ConnectivityManager` capability check transiently/incorrectly
  reports no network. That setting defaulted to enabled before version 0.0.34, so any install from
  before that update carried it forward as `true`. The welcome dialog's login test now calls the
  new `MusicServiceFactory.getOnlineMusicService()`, which always uses the real, network-backed
  service - a first-time login/setup check's entire purpose is proving the server is reachable and
  the credentials are valid, so it must never be satisfiable by a no-op.

## [0.0.39] - 2026-07-29

### Fixed
- **`release:back-merge-develop` intermittently failed with "Branch cannot be merged"**: right
  after opening (or reusing) the automated `master` -> `develop` MR, `scripts/ci/back-merge-
  develop.sh` attempted the merge immediately, but GitLab computes an MR's `merge_status`
  asynchronously, so the merge could be rejected purely because that computation hadn't finished
  yet — not because of a real conflict. Observed on `release/0.0.38`'s `master` pipeline: MR !65
  became mergeable within a second of the failed attempt. Added a short poll loop (up to 10 x 3s)
  waiting for `detailed_merge_status == "mergeable"` before merging, plus up to 3 retries on the
  merge call itself, before falling back to leaving the MR open for manual resolution.

## [0.0.38] - 2026-07-29

### Fixed
- **A stale, already-merged-but-never-deleted `release/0.0.35` branch's delayed pipeline
  re-pushed old code as `muma/muma-tools:latest` and redeployed it to production right after
  `bug 015`'s fix went live (`bug 016`)**: `release:build-images`/`deploy:prod` trigger on any
  `release/*` branch push or pipeline run, and the repository had accumulated many old, merged
  `release/*` branches; one of them (`release/0.0.35`) had a job stuck queued on the shared
  runner that finally executed *after* the `0.0.37` fix's pipeline, overwriting `latest` with its
  stale, pre-fix checkout. Deleted `release/0.0.35` and all other already-merged stale branches,
  and made `release:back-merge-develop` (`scripts/ci/back-merge-develop.sh`) automatically delete
  the `release/*`/`hotfix/*` branch it just merged into `master`, so merged release branches can no
  longer accumulate and race a later release's build/deploy. No functional application code
  change in this release — this is purely the automated re-deploy of `bug 015`'s already-merged
  fix plus the branch-cleanup safeguard.

## [0.0.37] - 2026-07-29

### Fixed
- **`genre-processor` and `muma-soundcloud-fetcher` production containers crashed on start with
  `ModuleNotFoundError` (`bug 015`)**: an earlier refactor (commit `cb345cf79`) removed
  `services/common/settings.py` (replaced by `services.common.config_store.ConfigStore`) and moved
  `services/common/api/db_init.py` to `services/common/db_init.py`, updating all call sites under
  `services/`, but missed `tools/soundcloud_fetcher.py` and `tools/process_genres.py` — these
  `tools/` scripts aren't covered by the regular unit test suite, so the stale imports only
  surfaced as a container-runtime crash, not a CI failure. Fixed both imports and added
  `tools/test_tools_imports.py` (wired into `scripts/test/music-management-unit.sh`) to catch this
  class of regression going forward.

## [0.0.36] - 2026-07-29

### Fixed
- **Manager "Overview" tab crashed on load**: the recent-activity list's `{#each}` block was keyed
  on `item.file_path`, but `/api/system/activity` never returns that field (only `title`, `artist`,
  `timestamp`). Every row therefore shared the identical `undefined` key, and Svelte 5 throws a
  runtime error on duplicate keyed-each keys — crashing the whole Overview tab as soon as there
  were 2+ recent items (the normal case). Keyed the loop on array index instead, and guarded the
  filename fallback so it can't throw even if `file_path` is ever absent.

## [0.0.34] - 2026-07-29

### Added
- **Automated `master` -> `develop` back-merge**: previously, after a `release/*` branch was merged
  into `master`, keeping `develop` in sync required manually opening and merging a second MR from
  the release branch (or `master`) into `develop`. Added `release:back-merge-develop`
  (`scripts/ci/back-merge-develop.sh`), a new CI job that runs on `master` right after
  `release:tag` and automatically opens+merges a `master` -> `develop` MR via the GitLab API,
  reusing the existing `TAG_CREATION_TOKEN`. It's a no-op if `develop` already contains `master`'s
  tip, and leaves the MR open for manual conflict resolution if the merge can't be done
  automatically.

### Changed
- **Ultrasonic UI**: Restyled the login/welcome dialog, edit-server screen, and Google
  access-request screen to match the web frontend's `LoginPage.svelte` and
  `docs/styleguide.md`: filled pill-shaped inputs, a real "Sign in with Google" button with the
  brand G logo, a proper divider, a red error banner, and colored info/success/error status
  banners for pending/rejected/approved access requests. Also replaced a stray non-brand color
  in the filter dialog/search FAB with the app's `spotify_green` token, and aligned the nav
  drawer's item tinting with the bottom nav's existing brand colors.
- **Ultrasonic settings**: `autoSwitchOffline` now defaults to `false` instead of `true`.
- Bumped Ultrasonic's own `versionCode`/`versionName` (`240`/`6.5.10` -> `241`/`6.5.11`).

## [0.0.33] - 2026-07-29

### Fixed
- **Ultrasonic Google Sign-In selected an account in the picker but then silently returned to the
  login dialog, with no error shown (`bug 013`)**: both `NavigationActivity.performWelcomeGoogleSignIn()`
  and `EditServerFragment.handleGoogleSignInResult()` checked the credential returned by
  `CredentialManager.getCredential()` with a naive `is GoogleIdTokenCredential`. Android's Credential
  Manager never delivers third-party credential types (like Google's) as their concrete subclass
  across the IPC boundary — they always arrive as a generic `CustomCredential` (a `type` string plus
  a raw `data: Bundle`), even though `GoogleIdTokenCredential` extends `CustomCredential` in the
  `googleid` library's own class hierarchy. The cast always failed, silently discarding a
  successful account selection before the ID token was extracted and before `/api/auth/google` was
  ever called. Replaced both checks with the documented pattern
  (`credential is CustomCredential && credential.type == GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL`,
  then `GoogleIdTokenCredential.createFrom(credential.data)`), with an explicit logged/user-visible
  error path for any unexpected credential type or parse failure.
- Bumped Ultrasonic's own `versionCode`/`versionName` (`239`/`6.5.9` -> `240`/`6.5.10`).

## [0.0.32] - 2026-07-29

### Added
- **Artist face images in the web player bar**: `Player.svelte` previously rendered only track
  cover art and plain artist-name text — no artist photo, unlike `ArtistView`, `Dashboard`,
  `SearchResults`, and `StarredView`, which already fetch artist images from `music_manager` via
  the shared `getArtistImageUrl()` helper. Reused that same helper to show a small circular
  avatar next to the artist name in both the mobile mini player and the desktop player bar, using
  the primary (first) artist of the currently playing track. No backend changes were needed — the
  manager's image-fetching/caching pipeline was already working, it just wasn't wired into the
  player UI.

## [0.0.30] - 2026-07-29

### Fixed
- **Ultrasonic welcome-screen Google Sign-In succeeded but the dialog never closed, leaving the
  app stuck requiring login (`bug 012`)**: `NavigationActivity.performWelcomeGoogleSignIn()`'s
  `"ok"` branch had been copied from the manual username/password submit handler just above it,
  including a `MusicServiceFactory.getMusicService().ping()` connectivity check gating whether the
  dialog was allowed to dismiss. That gate makes sense for manual credential entry (verifying
  arbitrary user-typed input), but not for Google Sign-In, where a `status: "ok"` response from
  `/api/auth/google` is already a server-verified, guaranteed-valid credential — the same trust
  model already used by `EditServerFragment.performMumaGoogleAuth()` and the web frontend's
  `handleGoogleResponse()`, neither of which re-verifies with a ping. A transient/unrelated
  connectivity hiccup on that extra ping call could silently discard an already-successful Google
  sign-in. Removed the ping-gating; the dialog now always closes on `"ok"`, exactly like the other
  two flows.
- Bumped Ultrasonic's own `versionCode`/`versionName` (`238`/`6.5.8` -> `239`/`6.5.9`).

## [0.0.29] - 2026-07-29

### Fixed
- **Ultrasonic Google Sign-In still failed with "No Google accounts found" on a real device with
  a real Google account already signed in, even with a correct (non-placeholder)
  `GOOGLE_WEB_CLIENT_ID` (`bug 011`)**: two combined causes. First, `GetGoogleIdOption` (used by
  both `NavigationActivity.performWelcomeGoogleSignIn()` and
  `EditServerFragment.startGoogleSignIn()`), even with `setFilterByAuthorizedAccounts(false)`, only
  reliably returns a credential for an account that has already authorized this app before —
  switched both call sites to `GetSignInWithGoogleOption`, Google's dedicated option for
  not-yet-authorized/first-time sign-ins. Second, and more fundamentally, Google's Credential
  Manager backend refuses to issue any credential to a native Android app unless a separate
  **Android**-type OAuth client (package name + signing certificate SHA-1) is registered in the
  same Google Cloud project as the Web client ID — this is a manual, one-time Google Cloud Console
  step (not fixable purely in code/CI), documented in `docs/deployment.md` and
  `docs/bug-reports/011-google-signin-no-credential-real-device.md`, along with the two client
  registrations needed (one for the release keystore, one for the debug keystore).
- Corrected `docs/deployment.md` and `docs/designs/authentication/technical.md`, which previously
  (incorrectly) stated no separate Android OAuth client/SHA-1 registration was needed for
  Ultrasonic's Google Sign-In.
- Bumped Ultrasonic's own `versionCode`/`versionName` (`237`/`6.5.7` -> `238`/`6.5.8`).

## [0.0.28] - 2026-07-29

### Fixed
- **Ultrasonic Google Sign-In showed a generic network error when no Google account exists on
  the device (`bug 010`)**: `CredentialManager.getCredential()` throws typed exceptions for
  distinct failure modes, but `NavigationActivity.performWelcomeGoogleSignIn()` and
  `EditServerFragment.startGoogleSignIn()` only had a catch-all `catch (e: Exception)`, so a
  device with no Google account (e.g. an emulator used for testing) always showed the same
  "network error" message as a real backend outage. Added explicit `catch` branches for
  `GetCredentialCancellationException` (silently ignored — user-initiated cancellation) and
  `NoCredentialException` (new, specific `google_signin_no_accounts` string: "No Google accounts
  found on this device."), both ordered before the generic fallback. Also logs a `Timber.e`
  warning in both call sites whenever `BuildConfig.GOOGLE_WEB_CLIENT_ID` is still the
  `"placeholder-id"` default, making a misconfigured build immediately visible in the logs.
- Bumped Ultrasonic's own `versionCode`/`versionName` (`236`/`6.5.6` -> `237`/`6.5.7`).

## [0.0.27] - 2026-07-29

### Fixed
- **Ultrasonic welcome-screen "Sign in with Google" always failed with a network error
  (`bug 009`)**: the button added in `0.0.25` reused the app's shared, Koin-injected
  `SubsonicAPIClient.mumaApi`, which on a fresh install (before any server had been configured)
  was still built against the offline/`localhost` fallback server, so the Google auth request
  never reached the real backend. `NavigationActivity.performWelcomeGoogleSignIn()` now builds a
  dedicated Muma API client targeting the fixed production server address directly; extracted the
  Muma base-URL derivation into a reusable `SubsonicAPIClient.mumaBaseUrlFor()` so both call sites
  stay consistent.
- Bumped Ultrasonic's own `versionCode`/`versionName` (`235`/`6.5.5` -> `236`/`6.5.6`).

## [0.0.25] - 2026-07-28

> **Two Ultrasonic (Android) fixes, requested together: the default server was still pointing at
> the retired "alpha" test instance, and the "Sign in with Google" option was missing from the
> very first login screen users see on a fresh install.**

### Changed
- **Default server is now `music.example.com`**: the separate "alpha" server entry (already
  retired at the infrastructure level, see `docs/deployment.md`'s "production-lms-consolidation")
  has been removed from Ultrasonic's static server list; there is now exactly one, fixed
  production server. Adjusted the (previously hard-coded) debug-build server selection, the
  "offline" pseudo-server's list index, and updated `docs/architecture.md`/`docs/OVERVIEW.md`
  which still described a live Alpha instance.
- **"Sign in with Google" is now available on the very first login screen** (the welcome dialog
  shown on a fresh install / after a full logout), not just from deep inside the server-edit
  screen — this was the actual requirement: a first-time user must be able to choose Google login
  immediately, without first setting up a username/password server entry. The new button reuses
  the exact same Credential Manager flow, response handling (nested `user`/`api_key` fields,
  access-request navigation for not-yet-linked accounts) and Subsonic-credential-population logic
  already fixed for the in-app flow in `0.0.23`.
- Bumped Ultrasonic's own `versionCode`/`versionName` (`234`/`6.5.4` -> `235`/`6.5.5`).

## [0.0.23] - 2026-07-28

> **Ultrasonic (Android) now supports "Sign in with Google", functionally equivalent to the web frontend.**
> A native Credential Manager-based Google Sign-In flow already existed in the Ultrasonic codebase (button,
> access-request UX, token handling), but had two bugs that meant it could never actually work end-to-end.

### Fixed
- **Ultrasonic's `MumaAuthResponse` used a stale, flat response shape**: `/api/auth/google`/`/api/auth/refresh`
  return account fields nested under `user` (per the `0.0.4` fix to `/api/auth/login`/`/api/auth/google`), but
  the Android DTO still declared `id`/`username`/`display_name`/etc. as top-level fields, so they always
  deserialized as `null` after a successful Google sign-in. Added a `MumaAuthUser` nested type matching the
  real backend contract.
- **Ultrasonic never populated Subsonic/LMS credentials after a Google sign-in** (the exact same class of bug
  fixed for the web frontend in `0.0.6`): `EditServerFragment.performMumaGoogleAuth()`'s `"ok"` branch stored
  the MuMa access/refresh token but never wrote a username/password into the server's Subsonic fields, so
  streaming/library calls (and every other Subsonic request) stayed unauthenticated after a Google login. Now
  mirrors the web frontend exactly: writes `result.user.username`/`api_key` into `userNameEditText`/
  `passwordEditText`/`ServerSetting.userName`/`.password`, relying on the same `api_key`-as-password fallback
  in `/api/auth/login`.
- **Wired up the missing `GOOGLE_WEB_CLIENT_ID` build config value in CI**: the app's Google Sign-In flow
  already read `BuildConfig.GOOGLE_WEB_CLIENT_ID` (intended to equal the web's `GOOGLE_CLIENT_ID`), but no CI
  job ever provided a real value, so every CI-built APK shipped with the `build.gradle` default
  `"placeholder-id"`, making Google Sign-In silently non-functional. `scripts/ci/ultrasonic-build-upload.sh`
  now extracts `GOOGLE_CLIENT_ID` from the existing `PROD_ENV_FILE` CI/CD variable and passes it through — no
  new secret or Android-specific OAuth client registration required, since the Android flow reuses the web
  client ID as its Credential Manager `serverClientId` by design.
- Updated `docs/designs/authentication/technical.md`'s Cross-App Impact section, which incorrectly stated
  Ultrasonic was unaffected by the Google/Subsonic-credential-forwarding requirement.
- Bumped Ultrasonic's own `versionCode`/`versionName` (`233`/`6.5.3` -> `234`/`6.5.4`).

## [0.0.21] - 2026-07-28

> **Automated the Ultrasonic Android release APK build and publish flow, end to end.** This CI/CD automation already existed in the codebase from earlier work, but had never actually produced a real signed release: the original signing keystore could no longer be located anywhere, so official release APKs were never built by CI before.

### Added
- **Ultrasonic release APK now built and published entirely by CI**: generated a brand-new, dedicated signing keystore (the original could not be recovered) and configured it, together with the `apk-hoster` upload credentials, as GitLab CI/CD variables. `ultrasonic:build-release` now runs automatically on every `release/*` pipeline, builds a signed APK, and uploads it to `https://apk.example.com` alongside `deploy:prod` - no manual local build/upload is needed anymore.
- **Fixed `SIGNING_STORE_FILE` handling**: `scripts/ci/ultrasonic-build-upload.sh` now base64-decodes `SIGNING_STORE_FILE` before use, since GitLab CI/CD variables (even file-type ones) are transmitted as text and can't reliably carry raw binary `.jks` bytes; documented the required `base64 -w0` encoding in `docs/deployment.md`.
- **Clean slate on `apk-hoster`**: removed all previously, manually-published APKs (and their DB records) from `apk-hoster`, since none of them can be validly updated-from once we move to CI-built, newly-signed releases.
- Removed the stale, unusable `services/ultrasonic/ultrasonic-keystore.enc` (an encrypted backup with no known password/decryption method) from the repository.
- **Fixed `ultrasonic:build-release` always failing on `publish.sh`**: `services/ultrasonic/dist` was a machine-specific symlink (`-> /mnt/user/ultrasonic-builds`) that had accidentally been committed to the repository; `mkdir -p dist` fails with `File exists` when `dist` already exists as a (dangling, in CI) symlink, so every CI build of Ultrasonic was doomed to fail at the publish step regardless of signing. Removed the symlink from the repository (`dist/` is already gitignored for local use).
- Bumped Ultrasonic's own `versionCode`/`versionName` (`232`/`6.5.2` -> `233`/`6.5.3`) to mark this as the first official, CI-built and signed release.

### ⚠️ Breaking
- **The Android app's signing key changed.** Anyone who previously installed a manually-built signed release APK (e.g. `v6.5.2-214`) must uninstall it before installing this or any future release, since Android rejects updates signed with a different key and there is no way to keep the old key.

## [0.0.20] - 2026-07-28

> **Continued production log sweep uncovered the `importer_worker` logging the same ~15+ misleading "OS error: check disk space/filesystem" lines on every single import cycle**, for release folders that had actually already been imported successfully before.

### Fixed
- **Importer duplicate folders stuck in `__TODO` forever (`bug 008`)**: `Mover._move_folder()` already handled the "already imported" conflict via `except FileExistsError`, but `shutil.move()` raises `shutil.Error` (not `FileExistsError`) when the destination directory already contains an identically-named entry - this was silently swallowed by the generic `except OSError` branch, mislabeled as a disk/filesystem error, and never cleaned up the duplicate source folder. Now `shutil.Error` is treated identically to `FileExistsError`: the duplicate source is removed so it stops being retried and re-logged as an error on every cycle. Genuine `OSError`s (e.g. actual disk-full) are unaffected.

## [0.0.19] - 2026-07-28

> **Production log sweep uncovered the `telegram_worker` crashing on startup** while loading its `.session` file, and a second, deeper bug that had silently prevented this exact fix from ever reaching production despite a fully green release pipeline.

### Fixed
- **Telegram worker session schema mismatch (`bug 007`)**: `docker/Dockerfile.telegram` ran an unpinned `pip install telethon` in addition to the pinned version from `requirements.txt`, so different rebuilds could install different `telethon` releases. `telethon` changed its session SQLite schema (added a `tmp_auth_key` column) starting with `1.43.0`; an older rebuild could no longer read a `.session` file a newer rebuild had upgraded. Pinned `telethon~=1.44.0` in `requirements.txt` (matching the schema already on disk) and removed the redundant unpinned install so the image always uses a single, reproducible version.
- **`release:build-images` never covered background worker images (`bug 007`)**: `scripts/ci/build-and-push-images.sh` only ever built/pushed `music-manager` and `lms`; `muma-base`, `muma-downloader`, `muma-telegram`, `muma-importer`, and `muma-tools` were never rebuilt or pushed by CI, so `deploy:prod`'s `docker compose pull` kept re-pulling stale, manually-pushed images for every background worker — the telegram fix above went through a fully green `release/*` pipeline including `deploy:prod` without actually reaching production. Extended the script to build and push all five of these images on every `release/*` pipeline.

## [0.0.18] - 2026-07-28

> **The "Artist Images" manager tab was permanently stuck at "0 / 0 artiesten"** with a non-functional search and rescan, even though the artist/image data itself was correctly populated. Root cause: a reverse-proxy routing bug, not a data problem.

### Fixed
- **Artist Images tab always showing 0 / 0 artists (`bug 006`)**: LMS's reverse-proxy `MumaResource.cpp` intercepted every `/api/artists/*` request before it could reach the generic MuMa pass-through proxy, but only correctly implemented two shapes (`.../image` and a plain numeric artist ID for the player's own genre lookup); every other path used by the manager UI (`/images/stats`, `/search`, `/search-all`, `/fetch-progress`, `/{id}/fetch-image`) was rejected with `400 Invalid artist ID` before ever reaching `music-manager`. Narrowed the interception to only those two shapes; everything else now correctly falls through to the generic proxy.

## [0.0.17] - 2026-07-28

> **Fixed a production outage** where every login (username/password and delegated Google auth) crashed with `no such column: u.password_salt`. Root cause: a maintenance sync in `music-manager` dropped the player's real, persistent `user` table (based on an incorrect "it's volatile" assumption), racing with an incomplete fallback table-creation statement in the player itself.

### Fixed
- **`music-manager` LMS DB sync (`bug 005`)**: removed the destructive `DROP TABLE IF EXISTS user, auth_token, ui_state` from `sync_single_server_db()`; `user` is real, persistent state the player reads/writes directly (unlike `auth_token`/`ui_state`, which only ever exist in the player's private in-memory schema and were never actually reachable from this code path anyway).
- **Player schema fallback (`bug 005`)**: `Session::createIndexesIfNeeded()`'s raw-SQL `CREATE TABLE IF NOT EXISTS user` fallback was missing the `password_salt`/`password_hash` legacy columns the ORM mapping requires; added them so this fallback can no longer produce an incompatible schema.
- **Production**: repaired the live database directly (added the missing columns, restarted the player) ahead of this release to restore service immediately; documented in `docs/bug-reports/005-lms-user-table-corruption.md`.

## [0.0.16] - 2026-07-28

> **Fixed artist images not showing in the manager tab (and consequently in the player's Artists view).** Two independent bugs found and fixed: an unauthenticated image request in the manager UI, and a production deployment path mismatch that silently broke the LMS DB sync.

### Fixed
- **Manager tab artist images (`bug 004`)**: `ArtistImagesTab.svelte` requested artist images without any authentication, so every request was rejected with `401 Unauthorized`; the manager's API key is now passed along as an `apiKey` query parameter, matching how other authenticated image requests work.
- **LMS DB sync path mismatch (`bug 004`, production deployment)**: `docker/docker-compose.yml` mounted `music-manager`'s view of the `lms`/`alpha-lms` stacks' native databases (used to sync users/playlists and push artist image references) from a path under this stack's own `HOST_DATA_PATH` that never actually existed on production; it now defaults to the real `lms`/`alpha-lms` stacks' own data directories (`LMS_DATA_PATH`/`ALPHA_LMS_DATA_PATH`, overridable if needed).

## [0.0.15] - 2026-07-28

> **Configured home page "alles tonen" buttons to correctly redirect to their respective tabs with view mode switches.** Release Radar redirects to Release Radar, Songs redirects to songs (with songs view mode active), and Sets redirects to sets (with sets view mode active).

### Changed
- **Home page "alles tonen" buttons (`Dashboard.svelte`)**:
  - **Release Radar**: redirects to the Release Radar tab (`activeView = 'radar'`).
  - **Songs**: sets the view mode to songs and redirects to the songs tab (`viewMode.set('songs'); activeView = 'songs'`).
  - **Sets**: sets the view mode to sets and redirects to the sets tab (`viewMode.set('sets'); activeView = 'sets'`).

## [0.0.14] - 2026-07-28

> **Removed redundant "MuMa Beheer" button from the profile dropdown menu.** Streamlined navigation by relying solely on the persistent sidebar player/management toggle.

### Changed
- **Profile menu (`ProfileButton.svelte`)**: removed the "MuMa Beheer" menu item since system management is already fully accessible via the sidebar header toggle.

## [0.0.13] - 2026-07-28

> **Fixed popular genres statistics semicolon delimiter aggregation and artist image background fetching.** Resolved bug 002 (stats top_genres splitting compound semicolon-delimited genres correctly) and bug 003 (background artist image fetching selecting all missing primary images without image_status filtering bottlenecks).

### Fixed
- **Popular genres semicolon delimiter (`bug 002`)**: updated statistics top-genres aggregation (`stats.py`) to split compound genre strings separated by semicolons (`;` / `,`), trim whitespace, and count individual subgenres accurately.
- **Artist image fetching (`bug 003`)**: updated `run_fetch_missing()` (`artist_images.py`) to process all artists with missing primary images (`primary_image_id IS NULL`) regardless of previous `image_status`, ensuring reliable background and manual fetching of artist images.

## [0.0.12] - 2026-07-28

> **Implemented structured bug reporting workflow and resolved artist image fetch-progress reporting.** Established 2-step bug report markdown files under `docs/bug-reports/` and documented the workflow in `AGENTS.md`.

### Added / Changed
- **Structured Bug Reports (`docs/bug-reports/00#-<title>.md`)**: Added template format (`title`, `status`, `reported problem`, `Possible reason`, `solution`) and updated `AGENTS.md`.
- **Artist Image Fetch Progress**: Ensured progress endpoints handle background fetch statuses cleanly.

## [0.0.9] - 2026-07-28

> **Minor UI cleanups in the sidebar and profile menu.** Removed the legacy UI link, integrated all library sections directly into the main sidebar menu, and removed the redundant "Systeembeheer" item.

### Changed
- **Removed legacy UI button**: removed the "Oude UI (Legacy)" link from the profile dropdown menu in `ProfileButton.svelte`.
- **Consolidated library navigation**: moved all library items (playlists, artists, albums, genres, history, starred) directly into the main sidebar menu in `Sidebar.svelte` with appropriate icons, and removed the separate "JOUW BIBLIOTHEEK" section header.
- **Removed redundant "Systeembeheer" sidebar item**: removed the "Systeembeheer" entry from the sidebar since the play/management toggle in the header already provides this capability.

## [0.0.8] - 2026-07-28

> **Logging out after logging in with Google Auth (or MuMa session) no longer leaves session state behind.** Previously, `handleLogout` only reset `credentials` and cleared `lms_active_view`, leaving `mumaSessionActive`, `mumaApiKey`, `mumaRefreshToken`, `userPermissions`, and `mumaUser` (and their localStorage counterparts) intact. This caused unauthenticated users logging out to remain stuck as 'Gebruiker' with no music access.

### Fixed
- **Thorough logout session cleanup**: `handleLogout` (`ProfileButton.svelte`) now clears all session stores and localStorage entries (`mumaApiKey`, `mumaRefreshToken`, `mumaSessionActive`, `userPermissions`, `mumaUser`) alongside `credentials`, ensuring a clean slate upon logout.

## [0.0.7] - 2026-07-28

> **The login modal was detached into a dedicated full-screen login page, and unauthenticated users are now always redirected there.** Previously, unauthenticated users saw the main music app layout with a floating modal overlay on top; now, logging out or visiting the app without a valid session presents a clean, full-screen dedicated login page (`LoginPage.svelte`) at `/login` and redirects all non-authenticated navigation there.

### Added / Changed
- **Dedicated full-screen login page**: refactored `AuthOverlay.svelte` into `LoginPage.svelte` (`services/frontend/src/lib/LoginPage.svelte`), removing the floating modal overlay.
- **Mandatory login redirection**: `App.svelte` now strictly checks session state (`!$credentials.username && !$mumaSessionActive`), rendering the login page and enforcing URL redirection to `/login` whenever the user is not logged in.

## [0.0.6] - 2026-07-27

> **A Google-authenticated user was logged in as "Gebruiker" and could not see any music.** Google
> Sign-In correctly authenticated against `music-manager` (permissions, admin badge, etc.), but the
> frontend's `credentials` (username/password) store -- which every Subsonic call (`getGenres`,
> albums, streaming, ...) and the profile display name are derived from -- was never populated after
> a Google login, since a Google sign-in never learns the account's real password.

### Fixed
- **Google-signed-in users saw "Gebruiker" and no music at all (`getGenres` failing with "Required
  parameter 'c' is missing")**: `AuthOverlay.svelte`'s `handleGoogleResponse` only ever set
  `mumaUser`/`userPermissions`/`mumaApiKey`, never the `credentials` store that `authParams`
  (and therefore every Subsonic/LMS REST call across the app) and `ProfileButton`'s displayed
  username are derived from -- so a Google-authenticated session had no way to actually talk to
  Subsonic at all. `POST /api/auth/login` now also accepts a user's own `api_key` as a valid
  `password` (in addition to the real, bcrypt-hashed password), and `handleGoogleResponse` uses
  that to populate `credentials` with `{username: user.username, password: api_key}` right after a
  successful Google login -- restoring the user's real username in the UI and making all Subsonic
  calls (and, through LMS's `MusicManagementPasswordService`, Subsonic streaming itself) work
  exactly the same regardless of which login method was used, per the linked-account requirement
  from 0.0.3/0.0.5.

## [0.0.5] - 2026-07-27

> **The "Sign in with Google" button disappeared from production again, and the server would have
> silently accepted a Google ID token from ANY Google OAuth client, not just ours.** Root cause: the
> `GOOGLE_CLIENT_ID` (backend) and `VITE_GOOGLE_CLIENT_ID` (frontend build-arg) CI/CD variables were never
> actually populated in `PROD_ENV_FILE`/`PROD_ENV_FILE_LMS` -- they were only ever set directly on the
> production host, outside of the CI/CD pipeline, so the first CI-driven rebuild after 0.0.2 wiped them out.

### Fixed
- **Google Sign-In button missing in production, username/password-only login shown**: `VITE_GOOGLE_CLIENT_ID`
  was empty when the `lms` image's frontend bundle was built by `release:build-images`, so Vite's dead-code
  elimination stripped the entire `if (GOOGLE_CLIENT_ID) { ... }` branch in `AuthOverlay.svelte` (including
  the Google Identity Services script load and the `#googleBtn` render call) out of the production bundle.
  The `PROD_ENV_FILE_LMS` CI/CD variable now includes `VITE_GOOGLE_CLIENT_ID`, matching the value already
  configured directly on Google Cloud Console for this app.
- **Google login would have silently accepted a token issued for a *different* Google OAuth client**:
  `GOOGLE_CLIENT_ID` was empty for the same reason, and `google.oauth2.id_token.verify_oauth2_token()`
  silently skips its `aud` (audience) check entirely when `audience=None` -- so the backend was verifying
  only the token's signature and issuer, not that it was actually issued for *our* app.
  `_verify_google_id_token()` (`services/music_manager/routers/user_requests.py`) now raises a `500` with a
  clear message instead of degrading into that unauthenticated-by-omission state, and `PROD_ENV_FILE` now
  includes `GOOGLE_CLIENT_ID` too.
- Both username/password (Subsonic) login and Google Sign-In already resolved to the exact same underlying
  `User` row (see 0.0.3's "Merge duplicate user accounts" / "Link a Google access request to an existing
  account"); this fix restores that both methods are actually *available* on the login screen again, with
  identical resulting permissions/session regardless of which one was used.
- **The LMS `/api/...` proxy (`MumaResource`) collapsed every non-`200` response from MuMa into a generic
  `502 Bad Gateway`**, discarding the real status code and error body MuMa returned (e.g. `401 Invalid
  username or password`, `404 Track not found`). Root cause: `core::http::SendQueue` only ever invoked
  `onSuccessFunc` for a `200` response and routed everything else through `onFailureFunc` (which every proxy
  call in `MumaResource` hard-codes to `502`) — appropriate for the client's other, non-proxy callers (which
  only care "worked" vs. "didn't"), but wrong for a reverse proxy, where the exact upstream status/body must
  reach the original caller. Added an opt-in `ClientRequestParameters::treatAnyStatusAsSuccess` flag (default
  `false`, so every existing caller is unaffected) and set it on all of `MumaResource`'s raw pass-through
  proxy calls (generic `/api/*` GET/POST/PUT/DELETE, artist image, track refresh, per-app user settings).
- **Added a `release:check-secrets` CI job** (`scripts/ci/check-required-secrets.sh`) that fails a
  `release/*` pipeline immediately, before any image is built, if `GOOGLE_CLIENT_ID`
  (`PROD_ENV_FILE`) or `VITE_GOOGLE_CLIENT_ID` (`PROD_ENV_FILE_LMS`) is missing or empty — the actual root
  cause of the button disappearing again was an unrelated edit to one of those CI/CD variables silently
  dropping this key, with nothing in the pipeline noticing. See `docs/deployment.md` and `AGENTS.md`
  ("Testing & Stability") for the policy: this job's pass/fail result is a hard requirement for a release,
  the same as any other check in this list, even though GitLab itself has no way to enforce it structurally.

## [0.0.4] - 2026-07-27

### Fixed
- **A successful Google login could still show "Kon geen verbinding maken met de Google login API"**:
  `POST /api/auth/google` (and `/api/auth/login`, `/api/auth/refresh`) returned the account fields spread
  directly onto the top-level response object instead of nested under a `user` key, while
  `AuthOverlay.svelte` (and every other frontend caller) reads `data.user.permissions`/`data.user` — matching
  what `/api/auth/verify` already returns. That mismatch made `data.user` `undefined`, throwing inside the
  `try` block right after a `200 OK` response and landing in the generic connection-error `catch`, even
  though the login itself had actually succeeded server-side (the user was left stuck on the login screen
  despite the account being valid and linked). `login`, `refresh_access_token`
  (`services/music_manager/routers/users.py`) and `google_login`
  (`services/music_manager/routers/user_requests.py`) now all return `{status: "ok", user: {...}, api_key,
  access_token, refresh_token}`, matching the documented contract in
  `docs/designs/authentication/technical.md`.
- **Google Sign-In popup could silently fail with "Cross-Origin-Opener-Policy policy would block the
  window.postMessage call."**: no response served by the LMS reverse proxy set a `Cross-Origin-Opener-Policy`
  header at all, which some browsers treat as reason to sever the window reference to Google's Sign-In
  popup, breaking the postMessage-based token hand-off back to `AuthOverlay.svelte` before the ID token
  ever reaches `/api/auth/google`. `services/music-management-server/nginx/reverse-proxy.conf` now sends
  `Cross-Origin-Opener-Policy: same-origin-allow-popups`, which keeps same-origin window isolation while
  explicitly allowing the trusted Google popup to keep talking back to the page.

## [0.0.3] - 2026-07-26

> **Google Sign-In is now fully wired up end-to-end: the button actually renders, the login it produces
> actually works, and duplicate accounts can be cleaned up.** The frontend/backend code for "Sign in with
> Google" already existed, but the `VITE_GOOGLE_CLIENT_ID` build-arg was never passed to any of the three
> places that build the `lms` image (so the button never rendered), the LMS proxy layer blocked the
> Google auth endpoints and swapped every caller's identity for a generic one (so logins that did render
> failed with `401` and admins lost their management buttons), and there was no way to merge an account
> created via a Google access request into an already-existing local/Subsonic account for the same person.

### Added
- **Google Sign-In build wiring**: `build.sh`, `services/music-management-server/scripts/build.sh`, and
  `scripts/ci/build-and-push-images.sh` now all pass `--build-arg VITE_GOOGLE_CLIENT_ID=...` when building
  the `lms` image, sourced from a new `VITE_GOOGLE_CLIENT_ID` entry in
  `services/music-management-server/.env` (mirroring the backend's existing `GOOGLE_CLIENT_ID`). Documented
  in a new "Google Sign-In setup" subsection of `docs/deployment.md`.
- **Merge duplicate user accounts**: new `POST /api/users/{id}/merge` endpoint (permission `users.merge`)
  moves everything owned by a secondary account (login identities, sessions, dynamic playlists, per-app
  settings, ListenBrainz link, ratings and scrobble history) onto the primary account and then deletes the
  secondary account. Conflicts on a shared unique key are resolved by keeping the primary account's
  existing data. Exposed in the "Beheer" tab as an "Accounts samenvoegen" panel.
- **Link a Google access request to an existing account**: approving a pending access request
  (`POST /api/user-requests/{id}/approve`) now accepts an optional `link_user_id`, which links the Google
  identity to that account instead of always creating a brand-new one — preventing this kind of duplicate
  from happening again.

### Fixed
- **`/api/auth/google` / `/api/auth/access-request` / `/api/auth/setup*` were never reachable**: the LMS
  proxy (`MumaResource::handleRequest`) required an already-authenticated caller for every endpoint, which
  made it impossible for a brand-new Google identity (which by definition has no credentials yet) to ever
  call the very endpoints meant to grant it access. These are now explicitly treated as public,
  unauthenticated pass-throughs, exactly like the existing `/api/auth/login`.
- **Caller identity was discarded on every proxied request**: `MumaResource` always forwarded the
  server-wide `MUSIC_MANAGEMENT_API_KEY` to MuMa instead of the caller's own `X-API-Key`, so MuMa saw every
  request (Subsonic or Google-authenticated) as a generic, permission-less "system" caller rather than the
  actual logged-in user. The caller's own key is now forwarded first, falling back to the system key only
  when the caller didn't send one.
- **Frontend never recognized the "system" identity as an admin**: because Subsonic admins authenticate via
  the shared system key (which MuMa itself always grants full access to), the "Beheer" tab's
  `hasPermission()` checks (gating "add user", "delete user", role changes, ...) always evaluated to
  `false` for them, hiding those actions even for a real admin. The frontend now mirrors MuMa's own "system
  key = full access" rule.
- **`isAdmin` never accounted for a Google-authenticated admin's RBAC role**, and was never refreshed from
  a persisted session after a page reload — both are now covered so the "Beheer" nav entry and page gating
  work the same regardless of login method.
- **Deleting a user could fail with a generic, unhelpful error**: `DELETE /api/users/{id}` now explicitly
  cleans up dependent rows (login identities, sessions, dynamic playlists, per-app settings, ListenBrainz
  link) before deleting the account, protects the last remaining admin account from being deleted, and
  returns a clear `Verwijderen mislukt: ...` message instead of a bare `500` on failure.
- **Delete-user button visibility check used the wrong permission**: the "Beheer" tab's delete button was
  gated on `users.create` instead of `users.update`, which no longer matched what the backend actually
  requires.

### Notes
- A separate, lower-severity issue was found but intentionally **not** fixed here: the shared HTTP client
  used by `MumaResource` (`core::http::SendQueue`) treats any non-2xx response from MuMa as a transport
  failure, collapsing it into a generic `502 Bad Gateway` instead of relaying the real status code/body.
  This doesn't block real logins (a valid Google token returns `200`), but it does hide legitimate error
  details (e.g. an actually-invalid token, or a `403`) behind a generic gateway error. Fixing it would
  touch a shared component used by every other `IClient` consumer in the codebase, so it's flagged here as
  a follow-up rather than changed as part of this fix.

## [0.0.2] - 2026-07-26

> **Fix: production was deploying stale images.** After cutting `0.0.1`, `music.example.com`
> kept showing old behavior post-deploy. Root cause: `deploy:prod` only ever ran
> `docker compose pull`, but nothing in the pipeline actually *built and pushed* fresh
> `music-manager`/`lms` images first — it silently kept re-pulling whatever image had last been
> pushed **manually**, so a release could "deploy successfully" while production kept running old
> code.

### Fixed
- **Missing image build/publish step in the release pipeline**: added a new `release:build-images`
  CI job (stage `release`, before `deploy`) that builds and pushes fresh `music-manager` and `lms`
  (`music-management-server`) Docker images to Docker Hub on every `release/*` branch, via the new
  `scripts/ci/build-and-push-images.sh`. `deploy:prod` now always pulls an image that was just built
  from the code actually being released, instead of a possibly-stale, manually-pushed one.
- `release:build-images` is gated on the new `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN` CI/CD variables
  and runs in the same `release` stage as `release:version-check`, so `deploy:prod` (stage `deploy`)
  cannot start until both have succeeded — a failed or skipped image build blocks the deploy.

## [0.0.1] - 2026-07-26

> **Version reset.** This release intentionally restarts the overarching monorepo version number at
> `0.0.1`, replacing the previous `2.x` line. It marks the first official release produced under the
> new `develop` → `release/*` → `master` branching/release-management flow described in
> `docs/release-management.md`, and the first release of this project as a single, unified monorepo
> (backend services + Music Management Server + frontend + Ultrasonic client, one shared history). The
> root `VERSION` is the *overarching* version for this monorepo release line; individual components
> (e.g. Ultrasonic's own `versionName`/`versionCode`) keep their own, independent version numbers, as
> documented in the versioning policy.

### Added
- **Unified release process**: introduced the `develop` (integration) → `release/x.y.z` (stabilization +
  production deploy) → `master` (tagged, append-only production record) branch model. Production deploys
  now only happen from `release/*` branches, gated by an automated `release:version-check` that fails the
  pipeline if `VERSION`, `CHANGELOG.md`, or `RELEASE_NOTES.md` weren't updated. See
  `docs/release-management.md` for the full design and rationale.
- **CI-driven git tagging**: merges into `master` now automatically create an immutable `release-vX.Y.Z`
  tag (and `ultrasonic-vX.Y.Z` when an Ultrasonic release is included), so "what's actually live" can
  always be answered from `master`'s tag history, with no manual `git tag` step.
- **Automated Ultrasonic APK distribution**: CI now automatically builds and uploads a debug Ultrasonic
  APK to `apk-hoster` on every `develop` merge, and the official, signed APK on every `release/*` branch
  (previously both were fully manual, local-only steps).

### Changed
- **Repository**: merged the previously split-out `music-management-server` (LMS) and `ultrasonic`
  Android app repositories directly into this repository as a single monorepo, with their full commit
  history preserved (via `git subtree`). The `frontend` (which never had its own separate history) is
  now tracked here too. There are no more submodules or separate gitlab remotes for these projects —
  see `AGENTS.md` for the rationale (solo developer, tightly-coupled apps, one shared history).
- **Production deployment**: the `deploy:prod` pipeline job was fixed to use dedicated, CI-managed SSH
  key authentication and now reliably deploys both production stacks (`music-management` and `lms`)
  idempotently from a `release/*` branch, instead of the previously broken/manual `main`/`develop` flow.

## [2.6.0] - 2026-07-20

### Added
- **Mobile Integration (Ultrasonic)**: Formalized the integration of the Ultrasonic Android app into the ecosystem documentation.
- **Client Settings Sync**: Enabled server-side backup and synchronization for mobile application settings via the Music Manager API.
- **Subsonic API Support**: Standardized Subsonic API responses in the Music Management Server for seamless compatibility with mobile clients.
- **APK Distribution**: Integrated `apk-hoster` for independent distribution of mobile updates.

## [2.5.0] - 2026-07-11

### Changed
- **Path Migration**: Migrated the entire application from `/music` to `/mnt/music` across Docker configurations, environment variables, and application logic.
- **API Architecture**: Centralized `common/api` into `music-manager`. Workers now push updates to the `music-manager` hub instead of running their own API servers, simplifying the architecture.
- **Project Structure**: Removed the intermediate `music-management/` folder and moved `services/` to the root, resulting in a cleaner layout and simplified `PYTHONPATH`.
- **Worker Integration**: Fully integrated YouTube and SoundCloud downloaders with the centralized `job_manager` for real-time progress tracking.

### Added
- **Test Isolation**: Introduced `services/conftest.py` for aggressive mocking of heavy dependencies (`pymysql`, `mutagen`, `yt-dlp`), enabling tests to run without a live database.

### Fixed
- **API Routing**: Fixed path mismatches in tests and standardized all API routes under the `/api` prefix in `music-manager`.
- **Code Quality**: Removed over 80 redundant proxy methods in `management.py` and improved robustness of `Tag.to_string` and path resolution logic.

## [2.4.1] - 2026-07-10

### Added
- **Redownload Feature**: Added a "Redownload" button to the Library UI for SoundCloud and YouTube tracks.
- **Archive Integration**: The system now automatically finds the original source URL from the download archives to facilitate redownloads.
- **Downloader Enhancements**: Added `redownload_mode` to SoundCloud and YouTube downloaders to allow bypassing existing archive entries when explicitly requested.

## [2.4.0] - 2026-07-10

### Changed
- **Architecture**: Integrated the `tagger` and `scanner` services directly into the `music-manager` service.
- **Workflow**: Tagger and Scanner now run as background threads within the music manager process, reducing inter-service communication overhead and simplifying Docker deployment.
- **API**: Moved `/tag/*` and `/scan/*` endpoints to `/api/tagger/*` and `/api/scanner/*` respectively within the music manager API.
- **Performance**: Track rescan in the library now uses direct function calls for tagging and scanning instead of internal HTTP requests.

## [2.3.4] - 2026-07-10

### Fixed
- **Rescan Workflow**: Fixed a race condition where the scanner would run before the tagger finished by making single-file API calls synchronous.
- **Tagger Metadata**: Fixed an issue where manual rescans wouldn't clear the `needs_rescan` flag in the database.
- **Docker Networking**: Corrected internal service URLs in `docker-compose.yml` to use internal container ports instead of host-mapped ports.

## [2.3.3] - 2026-07-10

### Added
- **Scanner Service API**: Integrated a FastAPI-based REST API on port 8002 for the scanner service.
- **Immediate DB Sync**: Library track rescan now triggers both the tagger and the scanner for instant database updates.

## [2.3.2] - 2026-07-10

### Added
- **Tagger Service API**: Integrated a FastAPI-based REST API on port 8001 for the tagger service.
- **On-Startup Full Scan**: Service now explicitly performs a full tagging scan immediately upon startup.
- **Tagging Control Endpoints**: New `/tag/all` and `/tag/file` endpoints to trigger metadata enforcement via API.

## [2.3.1] - 2026-07-10

### Added
- **Tagger Auto-Detection**: New `TagSingleFile(path)` utility function that automatically determines the song source (SoundCloud, YouTube, Label, etc.) based on its file location and applies the appropriate tagging rules.

## [2.3.0] - 2026-07-05

### Added
- **MuMa Cloud Sync**: New server-side backup system for application settings (User App Settings API).
- **Settings API**: Endpoints for saving and retrieving JSON-based application configurations per user and app ID.
- **Enhanced Scrobble Imports**: Implemented robust pagination for ListenBrainz imports, allowing retrieval of up to 10,000 tracks.
- **Artist Image Synchronization**: Centralized artwork management for multi-LMS environments (Stable and Alpha).
- **Consolidated Versioning**: Unified version reporting for all internal worker services in the dashboard.

### Changed
- **Authentication**: Streamlined API key flow; keys returned at login are now universally valid for user-specific actions.
- **Security**: Removed sensitive API key displays from the frontend, relying on session-based auth.
- **Database Architecture**: Added `user_app_settings` and `scrobble_imports` tables to core initialization.
- **Stats Engine**: Refactored statistics queries to provide more accurate match rates and genre distributions.

## [2.2.0] - 2026-07-05

### Added
- **Dynamic Playlists**: Support for storing and managing dynamic playlist definitions (modifiers) in the database.
- **Management API**: New endpoints to create, update, and retrieve dynamic playlists.
- **User Service**: Added dynamic playlist management to the user-centric API.
- **LMS Integration**: Added a feedback hook to receive and process real-time playlist updates from LMS.

## [2.1.35] - 2026-07-05
### Fixed
- **User Management**: Fixed an issue where deleting or creating users in MuMa did not reflect in LMS due to a read-only database mount.
- **Service Integration**: Changed the `lms.db` mount in `user-service` to read-write by mounting the parent directory, allowing SQLite to handle journal files.
- **Logging**: Added enhanced logging and permission checks in the User Service to monitor LMS database connectivity.

## [2.1.34] - 2026-07-05
### Added
- **User Management**: Added ability to delete users and set default passwords in the Control Center.
- **LMS Synchronization**: Implemented immediate bidirectional synchronization with the Lightweight Music Server (LMS) database.

## [2.1.33] - 2026-07-05
### Fixed
- **Stats Service**: Resolved build and deployment issues for the new stats microservice.
- **Database**: Cleaned up redundant indices on the `rules_genres` table.

## [2.1.32] - 2026-07-05
### Added
- **Stats Microservice**: Decoupled library statistics into a dedicated microservice (`stats-service`).
- **Improved Management API**: Integrated statistics module directly into the Control Center via proxy to the new microservice.
- **Library Stats CLI**: Added a `stats` command to `install.sh` to quickly view library statistics from the terminal.

## [2.1.31] - 2026-07-05
### Added
- **Health & Activity Dashboard**: New tab in the Control Center for real-time monitoring of Docker containers.
- **Docker Logs Viewer**: View the logs of all Muma-related containers directly from the UI.
- **Recent Activity**: Overview of recently added and tagged tracks, categorized by source (YouTube, SoundCloud, etc.).

## [2.1.30] - 2026-07-05
### Added
- **LMS Subsonic API Key**: The Subsonic API key in LMS can now be configured via the environment variable `LMS_SUBSONIC_API_KEY`, facilitating integration with external apps.

## [2.1.29] - 2026-07-05
### Added
- **Centralized Authentication**: Introduced a centralized `/auth/verify` endpoint in the User Service to validate both system-wide and user-specific API keys.
- **Enhanced Security**: Repurposed the `user-service` as an Identity Provider, allowing services to offload credential verification.

### Fixed
- **Network Hardening**: Minimized the attack surface by removing public port exposures for internal services (Rating, Scrobble, User) in Docker Compose.
- **Internal Communication**: Optimized service-to-service communication by using the shared `music-management_db` Docker network and internal DNS.

## [2.1.28] - 2026-07-04
### Fixed
- **Infrastructure**: Added `LMS_SUBSONIC_API_KEY` to the main `docker-compose.yml` for correct propagation to the User Service.

## [2.1.27] - 2026-07-04
### Fixed
- **LMS Sync**: Resolved mismatch in API keys. Now uses a specific `LMS_SUBSONIC_API_KEY` for LMS, while the Muma services retain their own key.
- **Service Stability**: Improved error handling in the User Service for LMS sync responses.

## [2.1.26] - 2026-07-04
### Fixed
- **LMS Sync**: Resolved authentication issue with the LMS Subsonic API by explicitly adding the `apiKey` parameter to the sync URL.

## [2.1.25] - 2026-07-04
### Fixed
- **API Security**: Resolved inconsistencies in API keys between microservices and the Control Center in Docker Compose configurations.
- **LMS Sync**: Confirmed that the `user-service` sends the correct `X-API-Key` to LMS during user synchronization.

## [2.1.24] - 2026-07-04
### Added
- **YouTube Management**: YouTube accounts can now be managed via the Control Center.
- **Cookie Support**: Added support for Firefox cookies from a shared Docker volume for both YouTube and SoundCloud downloaders.

### Fixed
- **UI Consistency**: SoundCloud and YouTube management pages are now consistent and support removing accounts.

## [2.1.23] - 2026-07-04
### Fixed
- **User Service**: Fixed syntax and logic errors in LMS synchronization (`run_lms_sync`).
- **Configuration**: Added `LMS_HOSTS` support for multiple LMS instances and fixed `LMS_HOST` typo in `.env`.

## [2.1.22] - 2026-07-04
### Added
- **API Security**: Implemented system-wide API key validation (`X-API-Key`) for all microservices.
- **Control Center**: Added ability to set and save the API key in the dashboard.
- **User Service**: Added `user-service` to the `full` Docker Compose configuration.

### Fixed
- **API Consistency**: The `API_KEY` is now synchronized across all modules in the `music-manager`.
- **LMS Configuration**: Corrected default LMS host to `lms.example.com`.

## [2.1.20] - 2026-07-04
### Fixed
- **LMS Configuration**: Corrected default LMS host to `lms.example.com` and updated CORS origins to the correct production IP (192.0.2.27).

## [2.1.19] - 2026-07-04
### Added
- **User Password Management**: Set passwords via Control Center with automatic synchronization to LMS.
- **Security**: Implemented Bcrypt hashing for secure storage of user passwords.

## [2.1.18] - 2026-07-04
### Added
- **User Migration**: Imported users from `lms.db` to the User Service.
- **LMS Integration**: Added support for direct SQLite database synchronization from LMS.
- **UI Enhancements**: Added new synchronization options to the Users dashboard.

## [2.1.17] - 2026-07-04
### Added
- **User Service**: New microservice for centralized user management and external account links (ListenBrainz).
- **Control Center**: New "Users" dashboard for managing users and their API keys.
- **LMS Sync**: Ability to synchronize users/players directly from Logitech Media Server.
- **Scrobble Integration**: Integrated ListenBrainz imports based on saved user profiles.

## [2.1.16] - 2026-07-04
### Fixed
- **Scrobble Service**: Fixed ListenBrainz import crash caused by missing `json` import and improper data serialization.
- **Scrobble Service**: Added required `User-Agent` header to ListenBrainz API requests to prevent blocking.
- **Scrobble Service**: Improved database error handling during background import tasks.

## [2.1.15] - 2026-07-04
### Added
- **Control Center**: New Scrobble Service dashboard with ListenBrainz import monitoring.
- **Scrobble Service**: Added `scrobble_imports` table for tracking background task progress.
- **Scrobble Service**: New endpoints for polling import status and fetching recent history.
- **Frontend**: Real-time polling for active imports and visual progress bars.

## [2.1.14] - 2026-07-04
### Added
- **Scrobble Service**: New microservice for tracking listens and importing history from ListenBrainz.
- **ListenBrainz Integration**: Support for importing user listening history and automatic track matching.
- **Smart Matching**: Fallback logic for matching tracks via Artist/Title when MBIDs are unavailable.
- **Infrastructure**: Added Scrobble Service to the build pipeline and Control Center dashboard.

## [2.1.13] - 2026-07-04
### Changed
- **Rating System**: Renamed database table from `track_ratings` to `rating_tracks` for better consistency.
- **UI Refinement**: Global override of focus rings to eliminate blue browser defaults in favor of Spotify Green.
- **Styling**: Further alignment with `styleguide.md` for a consistent dark theme experience.

## [2.1.12] - 2026-07-04
### Added
- **Debug Support**: Added `--debug` flag to `build.sh` and `publish.sh` for detailed execution logging.
- **Design System**: Created `styleguide.md` to formalize the Spotify-inspired dark theme (Green/Black/Gray).
- **UI Refinement**: Standardized all UI accent colors to Spotify Green (`#1DB954`) and improved focus/selection states.

## [2.1.11] - 2026-07-04
### Added
- **Centralized Release Notes**: The Control Center now aggregates and displays release notes and changelogs from all modular services.
- **Service API Expansion**: Added versioning and release notes endpoints to the Rating System service.

## [2.1.11] - 2026-07-05
### Added
- **Library Stats CLI**: Added a `stats` command to `install.sh` to quickly view library statistics from the terminal.
- **Improved Management API**: Integrated statistics module directly into the Control Center.

## [2.1.10] - 2026-07-04
### Added
- **Modular Containerization**: Split the monolithic application into 10 specialized, lightweight services (`muma-scanner`, `muma-tagger`, `muma-downloader`, etc.).
- **Smart Build System**: Introduced `scripts/affected.sh` and optimized `install.sh` to skip builds for unedited modules.
- **Unified Base Image**: Created `muma-base` to share core music logic and dependencies, reducing image size and ensuring consistency.
- **Parallel Builds**: Optimized `build.sh` and `publish.sh` to execute Docker operations in parallel.

### Fixed
- Fixed missing `pymysql` and other dependencies in `ml-analyzer` worker.
- Silenced database permission warnings in workers when tables/views are already managed by migrations.
- Improved Telegram worker stability with dedicated `asyncio` loop management.
- Resolved circular dependencies by consolidating core logic in the base image.

## [2.1.9] - 2026-07-04
### Fixed
- Fixed `ml-analyzer` being offline by setting up a repeat loop and proper Docker command.
- Resolved `RuntimeError` in Telegram worker by improving `asyncio` loop management and explicitly passing it to Telethon.
- Removed redundant `yt-dlp` updates on service startup to speed up container initialization.

## [2.1.8] - 2026-07-04
### Fixed
- Improved Telegram worker stability by using a dedicated event loop and modern `asyncio` patterns.

## [2.1.7] - 2026-07-04
### Fixed
- Fixed `KeyError` in YouTube downloader by aligning configuration keys with `ConfigStore`.
- Added missing `muma-rating-system` to build and deployment scripts.

## [2.1.6] - 2026-07-04
### Fixed
- Consolidated all service code into the base image to resolve circular and cross-service dependencies.
- Added all common dependencies (`yt-dlp`, `telethon`, `patool`, etc.) to the base image to ensure all workers can share the same entry points.

## [2.1.5] - 2026-07-04
### Fixed
- Fixed API server crash due to missing dependencies (`markdown`, `pydantic`) in worker images.
- Fixed `UnboundLocalError` in API initialization.
- Fixed package recognition for `services.tagger` in modular workers by including `__init__.py` in the base image.

## [2.1.4] - 2026-07-04
### Fixed
- Fixed missing `requests` dependency in Management API.
- Fixed `ModuleNotFoundError` in modular worker images by moving core music logic (`BaseSong`, etc.) to the base image.
- Improved Management API Dockerfile to inherit from the shared base image.

## [2.1.3] - 2026-07-04
### Changed
- **Consolidated Deployment**: Unified root `deploy.sh` and `scripts/deploy-stack.sh` into a single `scripts/deploy.sh`.
- **Streamlined Workflow**: Updated `install.sh` to use the new centralized deployment script.

## [2.1.2] - 2026-07-04
### Fixed
- Fixed SQL syntax errors in `migrate_v2.sql` for MariaDB compatibility.
- Unified artist and label genre rule tables into a normalized structure with backward-compatible views.
- Improved database initialization logic to handle table renames and view creation.

## [2.1.1] - 2026-07-04
### Added
- Formalized `scanner_service` in Docker Compose configurations for production deployment.
- Created `docker-compose.full.yml` as a consolidated configuration for Portainer and manual stack management.

## [2.1.0] - 2026-07-04

### Added
- **Artist-Genre Editor**: A new Spotify-inspired UI for mapping artists and labels to genres.
- **Library Scanner**: A new `muma-library-scanner` service that automatically indexes audio files into the database.
- **ReadonlySong**: A specialized song class for metadata extraction without file modification.
- **Database Schema v3**: Added tables for `rules_artist_genres`, `rules_label_genres`, `library_artists`, and `library_labels`.
- **API Endpoints**: New REST endpoints for artists, labels, and genre-mapping rules.

### Fixed
- Improved database connection reliability in the Management API.
- Standardized Docker worker configurations.

## [2.0.0] - 2026-07-04
### Added
- Created `scripts/deploy-stack.sh`, a generalized Docker stack deployment tool supporting Portainer discovery, SSH transfer, and intelligent fallbacks.
- Support for initial stack creation: the deployment script now automatically creates the stack if it does not exist yet using a local template.
- Modular build system with separate `build.sh`, `publish.sh`, and `deploy.sh` scripts.
- Versioned Docker tagging: images are now tagged with both `:latest` and the repository version (e.g., `:2.0.0`).
- Portainer Webhook support for automated Stack updates.
- Automatic Docker group permission handling via `sg docker` re-execution.
- Standardized `.env` configuration for all deployment targets.
- `install.sh` shortcut for the full build-publish-deploy pipeline.
- Proactive Docker registry authentication checks.
- Advanced audio feature extraction (MFCC, ZCR, Rolloff, Chroma) in ML analyzer.

### Changed
- **Deployment**: Refactored `deploy.sh` to use the new generalized `deploy-stack.sh` helper, simplifying per-project deployment scripts.
- **Deployment**: Enhanced stack discovery to support `PORTAINER_HOST` for pulling master templates.
- **Deployment**: Improved robustness with `base64` template transfer and automated tab-to-space conversion in compose files.
- Refactored core to use normalized database schema v2.
- Updated `install.sh` to automate environment setup and dependency installation.
- Optimized Docker builds by using system FFmpeg packages instead of source builds.
- Unified deployment variables across repositories.

### Fixed
- Fixed Docker Hub push denial by adding pre-flight authentication checks.
- Fixed path typos in configuration store and downloader modules.
- Improved database storage robustness for high-load analysis jobs.
