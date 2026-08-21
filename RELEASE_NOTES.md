# Release Notes - Music Management Suite

This project is now modularized. Detailed release notes for each module can be found in their respective directories:

- [Scanner Module](services/scanner/RELEASE_NOTES.md)
- [Tagger Module](services/tagger/RELEASE_NOTES.md)
- [Downloader Module](services/downloader/RELEASE_NOTES.md)
- [Importer Module](services/importer/RELEASE_NOTES.md)
- [Music Manager](services/music_manager/RELEASE_NOTES.md)
- [ML Analyzer](services/ml-analyzer/RELEASE_NOTES.md)

## Unreleased

### Changed
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

## Global Version 0.22.0 (2026-08-21)

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
- **De Android-app opent meteen op wat er de vorige keer stond.** Het startscherm en de
  bladerschermen — genres, jaren, labels, festivals, line-ups — lieten bij elke start pulserende
  vakjes zien terwijl ze de server opnieuw bevroegen om lijsten die sinds de vorige keer bijna
  nooit veranderd waren. De caches die er al waren leefden alleen in het geheugen en gingen met
  het proces mee dood. De kaarten worden nu op schijf bewaard en direct weer neergezet, met een
  dunne voortgangsbalk onder de kop zolang de verse kopie onderweg is; aantikken kan meteen.
  Mislukt het verversen, dan blijven de kaarten staan en stopt de balk.

### Fixed
- **Een dynamische afspeellijst kwam bijna leeg terug.** Een lijst als "Hardstyle" die om 500
  nummers vroeg leverde er een handvol, wat eruitzag alsof de bibliotheek gewoon weinig hardstyle
  bevatte. De waarderingsfilter stond echter altijd in de query, ook op zijn standaardwaarde 0 tot
  100 — bedoeld als "geen filter". Waarderingen komen binnen via een LEFT JOIN, dus een nummer
  zonder waardering heeft er geen, en niets is nooit groter dan nul: daarmee viel elk ongewaardeerd
  nummer af. Dat zijn er 301.340 van de 302.561. Een bereik dat de hele schaal beslaat bouwt nu geen
  filter meer op; vraag je wel om vier sterren en hoger, dan blijven ongewaardeerde nummers er
  gewoon buiten.
- **Sterren geven in de auto werkt weer.** Bij een nummer dat al sterren had deed de knop na een
  paar minuten niets meer: de app las de sterren dan terug uit een kopie die niet meebewoog, kwam op
  hetzelfde getal uit als bij de vorige tik en stuurde niets meer door. Stond een nummer op vijf
  sterren, dan sprong het daardoor terug naar geen.
- **Een gegeven waardering blijft nu overal staan.** Wat je in de auto of in een lijst waardeerde
  ging wel naar de server, maar werd in de app zelf nergens bijgewerkt. Kwam je later terug bij het
  nummer, dan stond de oude waardering er weer, alsof hij was gewist.

## Global Version 0.21.1 (2026-08-21)

### Changed
- **Android-builds worden gepubliceerd onder de eigen naam van de app.** Elke APK ging omhoog naar
  apk-hoster als `ultrasonic-*`. Die dienst groepeert builds op het voorvoegsel van de bestandsnaam,
  en precies dat voorvoegsel vraagt een geïnstalleerde app op bij het controleren op updates — het
  hernoemen op zichzelf zou elke telefoon voorgoed "je bent bij de tijd" hebben verteld, wat eerder
  al een keer gebeurd is. Uploads heten nu `muma-mobile-*`, de updatecontrole vraagt om die reeks,
  en oudere installaties die nog om de oude naam vragen worden er door apk-hoster naartoe gewezen
  via de nieuwe instelling `APK_ALIASES`. Ook het account waarmee een build bij apk-hoster inlogt is
  meeverhuisd; het oude account blijft staan zolang er builds zijn die ermee inloggen.
- Apk-hoster zelf draagt de naam van de app die het toevallig hostte niet langer: het inlogscherm
  heet nu APK Hoster in plaats van ultrasonic.

## Global Version 0.21.0 (2026-08-21)

### 🧭 Een instelwizard die na een update laat zien wat er veranderd is
- Tweeënzestig instellingen stonden op één doorlopend scherm, en niets daarop zei welke er vorige
  week bij kwamen. De wizard loopt er negen één voor één langs — server, stijl, app-icoon,
  interfacegrootte, herinneringen op het startscherm, offline opslag, alleen downloaden op wifi, de
  balk met wat er speelt, en MuMa-synchronisatie — elk met uitleg én de knop zelf, zodat je een
  instelling wijzigt op de plek waar hij wordt uitgelegd.
- Instellingen die nieuw zijn sinds de versie waar je vandaan komt krijgen het label Nieuw en komen
  vooraan, waardoor een update-ronde kort blijft. De wizard staat ook altijd in het overloopmenu, en
  een update die geen instellingen toevoegt toont gewoon de changelog zoals voorheen.
- Stijl, app-icoon en interfacegrootte werken nu ook echt vanuit de wizard. Die drie hadden hun
  werking in het instellingenscherm zitten, dat niet meeloopt als de wizard open staat: een gekozen
  stijl deed tot de volgende koude start niets, en een gekozen app-icoon liet het opgeslagen
  antwoord en het werkelijke pictogram blijvend uit elkaar lopen.

### 📖 Een handleiding aan boord, onder Help in het overloopmenu
- Alles wat MuMa kan was tot nu toe alleen te ontdekken door overal op te drukken. Help is twaalf
  hoofdstukken in leesvolgorde, dichtgeklapt tot je er één opent, elk met een schermafbeelding en,
  waar lezen de langzaamste manier is om het te leren, een knop rechtstreeks naar het scherm dat
  beschreven wordt.

### 🧹 Het Over-scherm wijst niet meer naar vreemde sites
- "Website openen" en "Bug melden" stuurden je naar adressen die niets met deze installatie te
  maken hebben. Beide knoppen zijn weg; bijwerken, de wijzigingslijst en het logboek blijven.
- De vertaalde Over-tekst beschreef in negen talen nog het oude Ultrasonic-product en de
  Subsonic-servers waarvoor dat gemaakt was. Die vertalingen vallen nu terug op de MuMa-tekst.
- Waar de oude productnaam nog in een vertaling opdook — welkomstscherm, crashmelding,
  versiewaarschuwing — staat nu MuMa, en in het beheerscherm heet de app MuMa Mobile.

## Global Version 0.20.0 (2026-08-21)

### 📻 Het nieuws van het uur, ook onderweg
- Geen enkele feed publiceert het NOS-radiobulletin op afroep, dus MuMa neemt het nu zelf op van de
  live stream van NPO Radio 1. Elk heel uur wordt tien minuten getapt en de laatste twaalf opnames
  blijven staan; een opname korter dan een minuut gaat weg in plaats van bewaard te worden, want een
  afgekapt bulletin in de auto is erger dan geen bulletin.
- In Android Auto staat er een Nieuws-map naast Radio en een nieuwsknop bij de bediening: één tik legt
  de wachtrij vast, speelt het bulletin, en zet daarna de muziek terug op de seconde waar je was.
  Radio is de uitzondering, want die tijdlijn is van de server: dat kanaal wordt na het nieuws
  opnieuw afgestemd.
- De webspeler doet hetzelfde, en het beheerscherm kreeg een Nieuws-tab met bron, schema,
  bewaartermijn en een knop om meteen op te nemen.

### ⚡ De Android-app bouwt in seconden in plaats van soms een uur
- De pijplijn gaf elke gelijktijdige taak zijn eigen Gradle-map, dus de eerste bouw op een verse plek
  haalde alle afhankelijkheden opnieuw op: dezelfde controle die warm drie minuten duurde liep dan
  vijftig tot negentig minuten en sloeg tegen de tijdslimiet aan.
- De mobiele taken draaien nu gegarandeerd één voor één en delen daardoor veilig één warme Gradle-map.
- Daarbovenop verdwenen twee dingen die de app nooit gebruikte maar wel elke bouw betaalde: de
  kapt-annotatieverwerker, waarvoor geen verwerker meer bestond sinds Room op KSP overging, en
  DataBinding, dat in geen van de 78 layouts voorkwam. Zonder DataBinding kon ook de
  configuratiecache aan.
- Precies deze tijdslimiet blokkeerde de uitrol van 0.19.0: `muma-mobile:check` viel om, waardoor het
  bouwen van de images en de productie-uitrol werden overgeslagen. 0.19.0 staat daardoor wel getagd
  op master maar heeft productie nooit bereikt; deze release brengt beide alsnog naar buiten.

- MuMa Mobile gaat naar 6.19.0.

## Global Version 0.19.0 (2026-08-20)

### 🎤 Een genre hardop vragen werkt nu ook als de telefoon je verkeerd verstaat
- "Uptempo hardcore" leverde het brede genre Hardcore op, of helemaal niets. Er waren drie dingen
  tegelijk mis, en één ervan repareren had het probleem laten staan.
- De spraakherkenning had nooit te horen gekregen welke genres deze bibliotheek bevat, dus die
  antwoordde met het gewone Nederlands dat er het dichtst bij lag. Ze krijgt nu de genres met de
  meeste muziek mee voordat ze begint te luisteren.
- Een naam die net verkeerd terugkwam was daarna niet te redden. Hij kwam nergens exact overeen en
  viel dan terug op het genre dat er toevallig in zát: "temple hardcore" bevat "hardcore", dus een
  verzoek om het ene genre antwoordde met alles wat onder het andere valt. Zo'n naam wordt nu
  gelezen als het genre waar hij op lijkt — maar alleen als alle woorden op één na exact kloppen,
  dat ene woord minstens vier letters heeft, en het om een van de grote genres gaat.
- En waar de bibliotheek één genre op meerdere manieren spelt wint nu de spelling waar de muziek in
  zit, in plaats van degene die de server toevallig het eerst noemde.
- De drempels zijn beredeneerd, niet gemeten tegen de echte genreverdeling. Of de herkenning zelf
  merkbaar beter wordt blijkt pas na een rit; het diagnosescherm laat zien wat er binnenkomt.

### 🔍 Android Auto toont een zoekknop binnen MuMa
- De app gaf nooit aan dat er gezocht kon worden, dus verborg de auto zijn eigen zoekknop en was de
  globale zoekbalk van de auto de enige ingang.
- Zoeken vanuit MuMa loopt door dezelfde spraakparser als de microfoon en het tekstveld.

- MuMa Mobile gaat naar 6.18.0.

## Global Version 0.18.2 (2026-08-20)

### 🎤 Een gesproken genre vindt nu al zijn muziek
- Om hardstyle vragen leverde helemaal niets op, terwijl de zin goed begrepen werd en er
  twintigduizend hardstyle-nummers in de bibliotheek staan.
- De bibliotheek bewaart een genre onder elke schrijfwijze die ooit in een tag stond: "Hardstyle",
  "HARDSTYLE" en "hardstyle" zijn drie losse ingangen. MuMa hield degene die als eerste terugkwam —
  een restant met vier lange mixen — dus een verzoek om nummers vond er geen één van.
- Een uitgesproken genre draagt nu élke schrijfwijze die de bibliotheek ervan heeft. Een genre dat
  het uitgesproken genre alleen maar bevat, zoals "Mainstream Hardstyle", blijft er buiten.
- Dit lost het zoeken op, niet de dubbele genres zelf. Die verdwijnen pas als de bestanden opnieuw
  getagd worden; van de 1651 genreregels wachten er nog 728 op een beslissing en die laat de tagger
  bewust met rust.
- MuMa Mobile gaat naar 6.17.2.

## Global Version 0.18.1 (2026-08-20)

### 🎤 MuMa Voice start nu ook echt de muziek
- Een gesproken of getypte opdracht las de zin goed, doorzocht de bibliotheek goed, en sloot dan de
  app af op het moment dat er iets gevonden was. Dat is opgelost.
- Het viel juist niet op als een fout: precies de opdrachten die *wel* iets vonden klapten eruit,
  dus het leek alsof MuMa Voice niets kon vinden.
- MuMa Mobile gaat naar 6.17.1. Er is verder niets veranderd — de rest van 0.18.0 blijft zoals het
  was.

## Global Version 0.18.0 (2026-08-20)

### 🎤 MuMa Voice: praat tegen de app, niet alleen tegen de auto
- Er staat een microfoonknop in de werkbalk. Tik erop en zeg wat er moet spelen.
- Het gaat door precies dezelfde parser en zoekmachine als Android Auto, dus een zin die in de auto
  werkt werkt hier ook — en andersom.
- De spraakherkenning geeft meerdere lezingen van dezelfde zin terug en MuMa probeert ze op
  volgorde. Dat is wat "hard style" alsnog op "hardstyle" laat uitkomen zonder dat je iets merkt.
- Op hetzelfde scherm staat een tekstveld, zodat je een formulering kunt uitproberen zonder te
  praten.

### 🤔 MuMa vraagt het na als een naam meer dan één ding kan zijn
- "Speel Thunderdome" kan het label zijn, het album, of de playlist. MuMa Voice laat de
  mogelijkheden zien en vraagt welke je bedoelde; je tikt het aan of je zegt "het label".
- In de auto kan dat niet — een mediasessie heeft geen weg terug om iets te vragen — dus daar kiest
  hij de sterkste lezing en legt hij de afgewezen lezingen vast.

### 🗣️ Meer soorten opdrachten
- Albums, playlists en losse titels: "speel album thunderdome af", "speel de afspeellijst zomer af",
  "speel het nummer dragonborn af".
- Sterren: "speel hardstyle met minstens 4 sterren af".
- Twee waarden tegelijk: "speel hardstyle en hardcore af" is één zoekopdracht. "Drum and bass"
  blijft gewoon één genre.

### 🔍 Voice diagnostics, onder Over
- Elke spraakopdracht laat nu een volledig spoor achter: via welke callback hij binnenkwam, de
  zoekopdracht precies zoals ontvangen, élke extra die Android meestuurde, welke parserregel welk
  woord opeiste, wat de bibliotheek over elke term zei, en het verzoek dat er uitging.
- De laatste vijftig blijven bewaard en zijn als tekst te delen.
- Hiermee is eindelijk te zien wat Google van een gesproken zin maakt vóór MuMa hem krijgt —
  vermoedens daarover waren tot nu toe afgeleid, niet afgelezen.

### 🩹 Twee dingen die hierbij rechtgezet zijn
- Vond geen enkel filter iets, dan werd er gezocht op de hele zin. "Speel het nummer dragonborn af"
  zocht dus letterlijk daarnaar en vond niets. Nu wordt er op "dragonborn" gezocht.
- Een gesproken sterrenfilter sleepte elke ongewaardeerde track mee, omdat de server een losse
  ondergrens oprekt tot alles wat niemand ooit beoordeeld heeft. Er gaat nu altijd een bovengrens
  mee.

## Global Version 0.17.1 (2026-08-20)

### 🩹 De hele site gaf 504, en dat lag niet aan het scherm waar je op stond
- LMS heeft net zoveel HTTP-threads als de machine cores heeft. Elke aanvraag die een
  artiestafbeelding bij MuMa ophaalde, hield er daar één van bezet zolang hij op antwoord wachtte.
- Stonden er genoeg tegels tegelijk op het scherm, dan was er geen thread meer vrij. De server bleef
  draaien en zijn poort open houden, maar beantwoordde niets meer — een scrobble niet, een gewone
  ping ook niet — tot iemand hem herstartte.
- Die afbeeldingen wachten nu naast de threads in plaats van erop. Voor de overige MuMa-calls geldt
  een harde limiet: hooguit de helft van de threads mag tegelijk staan wachten.
- Loopt LMS toch ooit vast, dan herstart hij nu zichzelf in plaats van te wachten tot iemand merkt
  dat de site eruit ligt.

### 🔑 Sleutels overleven voortaan een herstart
- Subsonic-sleutels stonden in een database die alleen in het geheugen bestond. Elke herstart van
  LMS gooide ze weg, en voor een client is dat niet te onderscheiden van een verkeerde sleutel: die
  blijft eindeloos proberen met iets dat nooit meer gaat werken.
- **Eenmalig na deze update:** zet het Subsonic-token voor muma-radio opnieuw onder Beheer →
  Gebruikers. Daarna blijft hij staan. Verder hoeft niets opnieuw in te loggen — de webspeler en de
  mobiele app gebruiken gewoon je gebruikersnaam en wachtwoord en raken dit niet.

### 🧹 Kleiner spul dat hieruit voortkwam
- Eén mislukte call naar MuMa legde dertig seconden lang al het uitgaande verkeer stil, scrobbles en
  ratings incluis. Dat gebeurt nu pas als MuMa meerdere keren achter elkaar niet reageert.
- Een ongeldige API-sleutel greep bij elke poging de exclusieve databaselock, ook al bestond die
  sleutel niet. Tijdens een scan stond zo'n aanvraag daarmee achter de scanner in de rij.
- "Geen afbeelding voor deze artiest" werd in het log gemeld als een gateway-fout in plaats van als
  de 404 die het is. Dat is waarom het log vol stond met fouten die geen fout waren.


## Global Version 0.17.0 (2026-08-20)

### 🏷️ Vastgelopen releases staan nu als voorstel in het beheerscherm

- De importer sloeg een release over zodra het catalogusnummer niet in de labeltabel stond, of
  zodra er helemaal geen catalogusnummer in de mapnaam zat. Die bleef liggen in de importmap en
  werd elke ronde opnieuw als waarschuwing gelogd. Op de productiemap gaat dat om 1.197
  verschillende onbekende catalogusnummers en 7.625 mappen zonder bruikbaar nummer.
- Het label blijkt in de meeste gevallen al in de bestanden zelf te staan: in een steekproef van
  25 vastgelopen mappen droegen er 16 een bruikbaar labelveld. De importer leest dat nu uit — de
  labelvelden van een FLAC, het publisher-frame van een MP3 — en valt anders terug op de `.nfo`.
- De voorstellen staan onder **Labelvoorstellen**, gegroepeerd op voorgesteld label. Eén
  bevestiging handelt alle releases van datzelfde label af.
- Bevestig je een voorstel met catalogusnummer, dan wordt die koppeling onthouden en lopen alle
  volgende releases van dat label vanzelf door. Zonder catalogusnummer valt er niets te onthouden
  en wordt alleen die ene map weggezet.
- Het labelveld kiest uit labels die de bibliotheek al kent, zodat een afwijkende schrijfwijze
  geen tweede labelmap aanmaakt. Een afgewezen voorstel komt niet meer terug.

De tabel `rules_label_proposals` wordt bij het opstarten aangemaakt; `migrate_v7_label_proposals.sql`
ligt ernaast voor een handmatige migratie. De lijst vult zich bij de eerstvolgende importronde.

## Global Version 0.16.0 (2026-08-19)

### 🎨 De app heeft nu twee stijlen: Spotify en MuMa
- De instelling onder Uiterlijk bood Groen en Blauw. Dat verwisselde één accentkleur en liet
  verder alles hetzelfde, dus je kon er weinig mee.
- Er staat nu **Spotify** en **MuMa**. Spotify is de app precies zoals hij was. MuMa houdt hetzelfde
  groen voor nummers en blauw voor sets, maar staat op een warmere en diepere achtergrond, scheidt
  lijstregels met een haarlijn in plaats van ze als kaartjes te laten zweven, dimt de minder
  belangrijke tekst echt in plaats van alles hetzelfde grijs te geven, rondt hoeken strakker af en
  kleurt een ingevulde ster goud.
- Spotify blijft de standaard, dus er verandert niets tot je zelf wisselt. Wisselen werkt meteen,
  zonder de app opnieuw te starten.
- Het blauwe accent vervalt. Het blauwe app-icoon is een aparte instelling en blijft gewoon staan.
- Twee dingen die onderweg zijn rechtgezet: een geselecteerde regel versprong van vorm, en het
  uitklapvak was nog een witte balk met zwarte tekst uit een lichte modus die de app niet meer heeft.

## Global Version 0.15.0 (2026-08-19)

### 📦 Weekpakketten worden uitgepakt tot op de release
- Zet je een weekpakket zoals `HHC-2026-WEEK-33.rar` in de importmap, dan bleef na het uitpakken de
  map van het pakket zelf staan, met alle releases daarin.
- De importer keek alleen naar de bovenste laag, vond daar geen catalogusnummer, logde "No valid
  CAT ID found" en keek er nooit in. Geen enkele release uit zo'n pakket is ooit geïmporteerd.
- Er zit nu een stap tussen die de releases uit de pakketmap omhoog haalt, zodat ze precies zo
  verwerkt worden als een losse download. De pakketmap verdwijnt daarna, met de losse `.nfo`- en
  `.sfv`-bestanden erin.
- Een pakketmap wordt herkend aan de inhoud, niet aan de naam: een release bevat zijn audio direct,
  een pakketmap bevat alleen mappen. Een album waarvan de nummers in één submap staan, zoals `CD1`,
  wordt daarom met rust gelaten.
- Bestaat een release al in de importmap, dan blijft die staan en wordt er niets overschreven.

## Global Version 0.14.0 (2026-08-19)

### 🎙️ De stemzoekopdracht begrijpt een heel verzoek
- "Speel willekeurige favorieten uit 2023 af" kwam vroeger bij de vrije-tekstzoekopdracht terecht.
  Die kent alleen artiest-, album- en titelnamen, dus op zo'n zin bleef het stil.
- De zin wordt nu uit elkaar gehaald in de onderdelen waar de bibliotheek op kan filteren: een
  genre, een artiest ("van headhunterz"), een label ("label art of creation"), een jaar ("uit
  2021"), je favorieten, en nummers of livesets. Daarbovenop een volgorde: "willekeurig" schudt,
  "recent" speelt op releasedatum, "recent toegevoegd" op de datum dat de bibliotheek bijkwam.
- Alles is combineerbaar en alles is optioneel, in het Nederlands en in het Engels. "Speel recent
  af" speelt je hele bibliotheek op releasedatum.
- Een naam die de bibliotheek niet kan plaatsen valt weg en de rest speelt gewoon door, dus "speel
  zwabberkore uit 2021 af" speelt 2021. Kan er niets geplaatst worden, dan neemt de gewone
  zoekfunctie het over.
- Nieuw onder Over: een pagina met alle spraakcommando's, want bovenstaande formulering vind je
  niet door tegen de auto te praten en te hopen.

### 🔀 Een tracklijst in de app is zelf te sorteren
- Open je een genre, een label, een festival, een jaar, een podcast, een line-up of een
  sterrenfilter, dan kwam die lijst altijd terug op releasedatum, zonder manier om dat te wijzigen.
- Boven de lijst staat nu dezelfde keuzelijst als in de webinterface: recent uitgebracht, recent
  toegevoegd, meest gespeeld, recent gespeeld, op waardering, op naam en willekeurig.
- De lijst opent op de sortering waarmee je binnenkwam, dus zonder een keuze te maken verandert er
  niets, en je keuze blijft staan als je het scherm draait.
- Albums, afspeellijsten en podcastafleveringen houden hun eigen volgorde en krijgen de keuzelijst
  niet. In offlinemodus blijft hij verborgen, omdat de sortering daar bij de server vandaan zou
  moeten komen.

### ⭐ De Android Auto-bibliotheek toont "Favorieten" nog maar één keer
- De nummers met een ster en de map met favoriete genres en tegels heetten in het Nederlands
  allebei "Favorieten", dus in de auto was niet te zien welke welke was.
- Er is nu één map Favorieten, met daarin "Favoriete nummers" naast de favoriete genres en
  playlists.

## Global Version 0.13.3 (2026-08-19)

### 🎙️ Een genre dat je met je stem opvraagt speelt nu op releasedatum
- "Speel genre hardstyle af" gaf je de nummers die het laatst in je bibliotheek waren beland. Bij
  een importronde is dat honderd nummers uit twintig jaargangen die op één middag binnenkwamen, en
  die verslaan allemaal een release van vorige week.
- De stemzoekopdracht gebruikt nu dezelfde sortering als het blok "Recent uitgebracht" op de
  startpagina: nieuwste release eerst.
- Een nummer zonder releasedatum valt terug op zijn bestandsdatum en sluit de rij, dus er verdwijnt
  niets uit het resultaat zolang de releasedatums nog niet compleet zijn.
- De bladerboom onder Genres is niet veranderd en sorteert nog op datum toegevoegd.

## Global Version 0.13.2 (2026-08-19)

### 🔑 De beheerpagina herkent je weer als beheerder
- De pagina zag niet dat je beheerder bent en laadde vaak helemaal niet. De gedeelde systeemsleutel
  staat in de productie-instellingen onder een andere naam dan de servers doorkregen, en die tweede
  naam was leeg -- dus draaide productie zonder sleutel.
- Dat trof meer dan de beheerpagina: ook de scrobbles en waarderingen die LMS terugstuurt werden
  stilzwijgend geweigerd. Beide schrijfwijzen worden nu doorgegeven, en een release kan niet meer
  uitgerold worden als geen van beide is ingevuld.
- Een sleutel die de server niet meer accepteert blokkeert de pagina ook niet langer. Die bleef
  eeuwig in je browser hangen: elk bezoek "kan niet verbinden", en je beheerstatus leek willekeurig
  te verdwijnen. Hij wordt nu weggegooid en je logt opnieuw in met je spelerwachtwoord. Bij een
  haperend netwerk gebeurt dat expres niet -- dat is geen bewijs dat je sleutel fout is.

### ☁️ SoundCloud kijkt slimmer welke accounts aandacht nodig hebben
- Accounts worden nu gecontroleerd op een ritme dat volgt hoe recent ze iets plaatsten: zesuurlijks
  voor wie deze week postte, en verder dagelijks, driedaags, wekelijks en maandelijks voor accounts
  die al meer dan een jaar stilliggen. De vier nieuwe wachttijden staan onder Systeembeheer →
  Downloaders → Timing.
- Een controle begint met één enkel verzoek om het nieuwste nummer, en slaat het account over zodra
  dat nummer al binnen is. Voorheen werd de hele catalogus doorgebladerd voordat er iets gebeurde --
  een groot account kostte 28 verzoeken per controle, of er nu nieuw werk was of niet.
- Een ronde begint bij de accounts die het verst over hun eigen wachttijd heen zijn, in plaats van
  alfabetisch.

### 🏷️ "File saved" betekent voortaan dat het bestand ook echt geschreven is
- De tagger meldde de opslag één stap vóór het schrijven, dus een bestand dat het bestandssysteem
  weigerde kwam er alsnog als succes uit. Bij de backfill over de bibliotheek waren dat 17356
  meldingen voor 8885 werkelijk geschreven bestanden.


## Global Version 0.13.1 (2026-08-18)

### 🎙️ "Speel mainstream hardstyle af" speelt nu dat genre
- Het woord "genre" was het enige signaal waar de spraakzoekactie op afging, en juist dat woord
  haalt Google Assistent uit je zin zodra hij begrijpt dat je een genre bedoelt. Wat overbleef ging
  naar de gewone zoekactie -- die kent alleen artiest, album en titel -- en landde op een album.
- Een zin zonder het woord "genre" wordt nu ook als genrenaam geprobeerd, en speelt dat genre zodra
  hij precies overeenkomt met een genre uit je bibliotheek.
- Komt hij niet precies overeen, dan verandert er niets: een titel die alleen maar op een genre
  lijkt blijft gewoon door de zoekactie gaan.
- Bij een precieze treffer wint het genre wel van een artiest of album met dezelfde naam. Dat is de
  prijs van de bewoording die de rit overleeft.
- "... af op MuMa" wordt voortaan van de zin afgehaald. Dat gebeurde eerder niet, en de zoekterm
  bevatte dus letterlijk "af op muma".

## Global Version 0.13.0 (2026-08-18)

### 🎙️ Een genre vragen in de auto werkt nu
- De spraakzoekopdracht draaide altijd de vrije-tekstzoekactie, en die kijkt naar artiest, album en
  titel. Een genre komt daar niet in voor, dus "speel genre hardstyle af" liet de auto stil of
  landde op een willekeurig album dat toevallig een woord deelde.
- Een uitgesproken genre draait nu dezelfde lijst als het bladermenu: de laatst toegevoegde nummers
  van dat genre, tot het maximum uit de instellingen, ongeacht waardering.
- "Speel hardstyle sets" of "livesets" geeft de lange opnames in plaats van de nummers.
- Spraakherkenning knipt en plakt namen, dus "hard style" en "tech house music" vinden hun genre
  alsnog. Een genre dat de bibliotheek niet kent valt terug op de oude zoekactie.

### ⏭️ "Speel X hierna af op MuMa"
- Google Assistent kent geen wachtrij-werkwoord voor externe muziekapps: "voeg X toe aan MuMa" wordt
  binnen Assistent zelf geweigerd en bereikt MuMa nooit.
- De instructie reist daarom mee in het speelverzoek zelf, als markeerwoord aan het eind van de zin:
  "speel X hierna af op MuMa", "play X next on MuMa".
- Het gevonden nummer schuift achter wat er speelt; de rest van de wachtrij blijft staan.
- Markeerwoorden tellen alleen aan het eind, dus een titel als "The Next Level" blijft heel.

### 🛠️ Onder de motorkap
- `LmsScanTrigger` kan na een download-, import- of tagronde meteen een incrementele LMS-scan
  aanzetten, zodat LMS' eigen schema van uurlijks naar dagelijks kan zonder dat de bibliotheek
  achterloopt. De helper is er wel, maar draait nog nergens mee -- die aansluiting hoort bij het
  retag-invalidatie- en BPM-plan dat in deze release is vastgelegd.
- Het ontwerp voor twee kiesbare stijlen in MuMa Mobile (Spotify en MuMa) is vastgelegd.
- De backfill-scripts voor releasedatums laden de `.env` van de repository voordat ze de database
  aanspreken. Vanuit een checkout liep het seeding-script eerst de hele bibliotheek af en faalde het
  pas daarna op het wegschrijven.

## Global Version 0.12.2 (2026-08-18)

### 🚗 "Speel alles" in de auto speelt op volgorde
- Shuffle bleef aan staan tussen luisterbeurten door: zette je hem ooit aan op de telefoon, dan bleef
  hij aan tot je hem zelf uitzette. Het bladermenu van Android Auto raakte die stand niet aan, dus
  een wachtrij die je in de auto startte erfde hem -- alleen op de ritten na een geshuffelde
  luisterbeurt, waardoor het willekeurig leek.
- Een wachtrij die in de auto begint, of dat nu via bladeren of via een spraakopdracht is, zet
  shuffle nu uit en speelt in de volgorde die je voor je zag.
- De shuffle-knop in de auto verandert niet: die hutselt de wachtrij zelf door elkaar.

## Global Version 0.12.1 (2026-08-18)

### 📱 "Onlangs beluisterd" doet weer wat het belooft
- Het raster bewoog niet meer. De lijst waar een wachtrij vandaan kwam werd blijvend onthouden in
  plaats van per wachtrij, dus het laatste bladerscherm waaruit je speelde bleef de bron van alles
  daarna — van het beginscherm, uit zoeken, uit de notificatie, uit de auto. Een bron hoort nu bij
  precies één wachtrij.
- Een snelkoppeling verschijnt zodra je op play drukt. Hij werd pas weggeschreven als een nummer
  scrobbelde, en dat gebeurt alleen als het uitspeelt — een lijst starten en doorskippen liet het
  raster onaangeroerd.
- Een genre-, label-, festival-, podcast- of jaarlijst wordt eindelijk als zichzelf herkend. Elk
  bladerscherm draagt zijn tag in de filters in plaats van in een eigen argument, en de historie las
  alleen die argumenten. Spelen uit Raw Hardstyle legde daardoor de compilatie vast waarop het
  nummer stond — Dirty Workz in plaats van het genre. Nu staat Raw Hardstyle er.
- "Speel nu" op één nummer onthoudt de lijst waaruit je het speelde. "Speel hierna" en "Achteraan"
  laten de bron van de lopende wachtrij met rust.

### 🖼 De hoezen zijn terug
- Een album of afspeellijst werd opgeslagen zonder het id waarop de hoes hangt, dus het raster
  tekende een placeholder waar eerst de hoes stond.
- Een genre, festival, label of podcast heeft zelf geen hoes en leent er nu één van een nummer met
  die tag, net zoals een artiest zijn foto al leende — één keer opzoeken per snelkoppeling, daarna
  bewaard.

### Nog niet
- Een sessie die volledig vanuit Android Auto of de notificatie start heeft geen bladerscherm
  erachter en laat dus geen spoor na op het beginscherm. Het album van wat er speelde vastleggen is
  bewust weggehaald: dat is niet de plek waar je heen ging.

## Global Version 0.12.0 (2026-08-17)

### ⭐ Livesets zijn eindelijk per festival te vinden
- De Festivals-tab liet vijftien namen zien, terwijl je bibliotheek sets bevat van Qlimax, Reverze,
  Ground Zero, Q-BASE, X-Qlusive, Thunderdome, Masters of Hardcore en Pussy Lounge. Die staan er nu
  allemaal in: 63 festivals, elk met de schrijfwijzen waaronder ze in titels en mapnamen voorkomen.
- De herkenning hing alleen aan YouTube-downloads. Juist de map met je livesets kwam er dus nooit
  langs. Hij draait nu ook op Livesets, Warm Up Mixes, de generieke mappen en SoundCloud.
- Naast de titel wordt nu ook naar de map gekeken. Bij scene-releases noemt de titel de artiest en
  de map het evenement, dus `Livesets/Qlimax 2022/` is daar de betere bron.

### 🛠 Waarom er zo weinig in stond
- Een festival moest per editie ingevoerd worden voordat het überhaupt herkend werd. Eén rij is nu
  genoeg om te labelen; een editie voegt alleen de datum toe.
- Bestanden die los in Warm Up Mixes stonden werden helemaal overgeslagen — ook voor genre en
  artiest. De tagger liep alleen over de submappen.
- Herkenning gaat op genormaliseerde tekst, dus accenten, leestekens en een spatie te veel maken
  niet meer uit. En "Rise" matcht niet langer op "Sunrise".

### 🎙 Radioshows en podcasts zijn een eigen categorie geworden
- Isaac's Hardstyle Sessions, Hard With Style en The Uptempo Tribe Podcast waren niet te
  onderscheiden van welke andere lange mix dan ook. Ze hebben nu een eigen label, een eigen
  overzichtspagina en een afleveringenlijst per show.
- Gemeten over de bibliotheek: 14.222 bestanden passen op een show- of afleveringspatroon, en
  daaruit komen 208 series met acht of meer afleveringen. De grootste zijn KTRA (818), Twisted's
  Darkside Podcast (313), B2S TV (308), Hardcore Italia (308) en Monstercat Podcast (301).
- De map `Podcasts` had helemaal geen serieregel, dus daar stond bijvoorbeeld een aflevering van
  The Magic Show als uren naamloze mix in je bibliotheek.
- Welke shows meedoen bepaal je zelf onder Beheer > Podcasts, met dezelfde goedkeuren-, afwijzen- en
  samenvoegenknoppen als bij genres. Eén show heeft vaak meerdere schrijfwijzen, dus die kun je vanaf
  het begin aan elkaar knopen in plaats van ze los te laten staan.
- De showlijst wordt voorgesteld door de bibliotheek zelf te meten, niet met de hand geschreven.

### 🛠 Waar een showtitel juist géén show is
- De regel draait bewust niet op de map `EPs`. "Hard With Style" (200 bestanden) en "Hardcore
  Blasters" (720) zijn daar platenlabels, en dat is precies de plek waar een shownaam en een
  labelnaam op elkaar lijken.
- Herkennen gebeurt op titel én pad, dus een show die zichzelf alleen in de mapnaam noemt telt ook
  mee. Een afleveringsnummer wordt meegenomen als het er staat, maar is niet verplicht.
- `ALBUM` en het tracknummer worden met rust gelaten. Die overschrijven is niet terug te draaien.

### 📻 Sneller zichtbaar
- Na een tagronde vraagt MuMa de muziekserver zelf om te scannen, in plaats van te wachten tot die
  er uit zichzelf aan toe is.

### 📱 MuMa Mobile
- Het beginscherm is opnieuw ingedeeld. Memories staat nu als één balk bovenaan in plaats van een
  carrousel van jaren, en verdwijnt op een dag waar niets in zit.
- De snelkoppelingen gaan niet meer over welke schermen je opent, maar over wat je echt geluisterd
  hebt: "Onlangs afgespeeld" wordt geschreven als je op afspelen drukt, en onthoudt de lijst waar de
  wachtrij uit kwam.
- "Onlangs bijgewerkt" is vervangen door twee echte nummerlijsten — "Onlangs uitgebracht" en
  "Onlangs toegevoegd" — allebei met een knop om verder te kijken.
- Hoeveel je te zien krijgt stel je zelf in: het aantal snelkoppelingen (2 tot 10) en het aantal
  regels per lijst (1 tot 10).
- Er is een Podcasts-pagina bijgekomen, met dezelfde shows als in de webspeler.

### 🧭 Wat nog niet kan
- Radio is nog geen bron voor een snelkoppeling. Het bestaat alleen in de Android Auto-verkenner en
  heeft nog geen eigen plek in de telefoon-app.
- Een snelkoppeling naar een genre onthoudt het genre, niet de sortering die op dat moment op het
  scherm stond. Je krijgt hem dus terug in de standaardvolgorde.

### 🧰 Na het uitrollen
- Deze uitgave verandert wat de tagger zou schrijven, maar niet wanneer hij het schrijft: bestanden
  die hij al eens verwerkt heeft blijft hij overslaan zolang hun wijzigingsdatum gelijk blijft. Om de
  nieuwe labels op bestaande bestanden te krijgen zijn `migrate_v7_festivals.sql` en
  `migrate_v9_podcasts.sql` nodig, moet `PODCAST` bij de extra tags van de muziekserver, en moet
  `needs_rescan` gezet worden. Zonder die stappen verandert er aan je bestaande bibliotheek niets.

## Global Version 0.11.0 (2026-08-17)

### ⭐ Labelnummers hebben nu een releasedatum op de dag
- Een import las alleen het jaartal uit de tags. Daardoor stond alles van 2026 als één blok door elkaar,
  kwam er niets van dit jaar bovenaan bij "recent uitgebracht", en kon Memories er nooit een verjaardag
  op vinden.
- De exacte datum blijkt meestal al mee te komen: de scene-NFO in de releasemap noemt hem letterlijk
  (`Str.date : 16-01-2026`). Gemeten over 150 releases staat daar voor 63 een datum in, tegen 17 in de
  audiotags zelf.
- Die datum wordt nu als originele releasedatum in de bestanden geschreven, en de bibliotheek, LMS en de
  telefoon-app lezen allemaal diezelfde waarde. Sorteren op releasedatum werkt daarmee overal hetzelfde.
- Staat er alleen een dubbelzinnige datum (`05.06.2026` kan 5 juni of 6 mei zijn), dan wordt de volgorde
  bepaald door waar het jaartal staat. Voor de 30 scene-groepen die het Amerikaans opschrijven is dat
  uitgemeten en vastgelegd, in plaats van gegokt.

### 🛠 Oude muziek blijft oud
- Een NFO noemt vaak de ripdatum in plaats van de releasedatum. Die wordt alleen geaccepteerd als het
  jaar klopt met het jaartal van de release, dus een vinylrip uit 1995 die in 2024 gerippt is blijft
  netjes uit 1995 staan.

### 📱 MuMa Mobile
- De app gebruikt de originele releasedatum als de server die stuurt, en valt terug op de datum van deze
  uitgave als die preciezer is.

## Global Version 0.10.0 (2026-08-17)

### ⭐ Je ratings komen weer aan in music-management
- De koppeling die een rating doorgeeft zoekt het nummer op via het bestandspad, maar kende alleen de
  schrijfwijze `/mnt/music/...`. Sinds de muziekbibliotheek onder `/music` hangt vond die zoekopdracht
  niets meer, en werden 202 van de 336 doorgegeven ratings weggeschreven onder een nummer-id dat niet
  meer bestaat. Beide schrijfwijzen worden nu herkend, in allebei de richtingen.
- Er is een herstelscript bijgekomen dat de sterren terugzet die verdwenen toen de bibliotheek opnieuw
  werd toegevoegd. Het leest de twee kopieën die dat overleefden — de RATING-tags in de bestanden zelf
  en de doorgegeven ratings in music-management — en raakt een rating die er al staat nooit aan.

### 🔗 De adresbalk klopt nu overal
- Schermen die geen eigen adres hadden — luistergeschiedenis, favorieten, een geopende afspeellijst,
  en elk tabblad in Instellingen en Beheer — hebben er nu wel een. `/management/scanner` en
  `/playlist/1234` kun je dus bookmarken, verversen en doorsturen.
- `/settings` of `/management` zonder tabblad opent nog steeds het tabblad dat je het laatst gebruikte.
  Een adres met een tabblad dat niet meer bestaat opent het eerste tabblad in plaats van een leeg scherm.
- Terug en vooruit lopen door de schermen die je bezocht, tabbladwissels meegerekend.
- Genres en labels houden hun naam in het adres, dus eerder gedeelde links blijven werken.

### 🐛 Verversen op een genre met een punt erin
- Een genre als `nu.jazz` gaf bij verversen "File not found": LMS zag de punt aan voor een
  bestandsnaam. Alleen echte bestandsextensies worden nu nog zo behandeld.

### 🔒 LMS serveert geen bestanden meer van buiten de webmap
- Een adres met `..` erin kwam uit op een echt bestand op schijf en werd gewoon teruggegeven. Zulke
  verzoeken krijgen nu een 404.

## Global Version 0.9.3 (2026-08-15)

### 🛠️ Opgelost

- **Bij elk genre stond "0 nummers".** De genrepagina telde nergens meer iets op, terwijl er
  bijvoorbeeld 67.653 Hardstyle-nummers in de bibliotheek zitten. De server bewaart die aantallen
  apart van de nummers zelf, en werkte ze alleen bij als een scan iets nieuws vond. Een scan die
  halverwege afbrak liet ze daardoor op nul staan, en elke volgende scan sloeg het bijwerken over
  omdat er niets te doen was. De scan controleert nu of die aantallen nog kloppen en herstelt ze
  vanzelf.
- **Op de telefoon kwam je niet meer uit het beheerscherm.** De tabbladen binnen beheer en
  instellingen stonden in een zijbalk die op een klein scherm verborgen is, dus het scherm opende op
  het laatst gebruikte tabblad zonder uitweg. Er zit nu een menuknop in de bovenbalk die de zijbalk
  als uitschuifpaneel opent.

## Global Version 0.9.2 (2026-08-15)

### 🛠️ Productiefouten uit de logs

- **De muziekscan legde LMS plat.** Elke scan (elk uur) liet het proces crashen op een
  databasefout, goed voor 835 herstarts per dag. Geen enkele scan kwam ooit af, dus afspeellijsten
  uit m3u-bestanden verschenen nooit in de speler. Oorzaak: een afspeellijst heeft geen eigenaar,
  en dat werd verkeerd opgeslagen — als een ongeldig gebruikersnummer in plaats van "leeg".
- **De workers lieten databaseverbindingen openstaan.** Tien plekken openden een verbinding zonder
  hem te sluiten. De importer alleen al was goed voor 841.000 waarschuwingen per dag in de
  database. Dat is opgelost bij de bron.
- **De radio kreeg letterlijk de tekst van een instelling doorgestuurd** in plaats van de sleutel
  zelf, door een schrijfwijze in het configuratiebestand die de versie van docker-compose op de
  server niet ondersteunt. Let op: hiermee werkt de radio nog niet volledig — LMS bewaart deze
  sleutels alleen in het geheugen, dus ze overleven geen herstart. Dat punt staat nog open.
- **SoundCloud-downloads werkten weer tegen de 403-blokkade aan** doordat een benodigd onderdeel
  ontbrak in het downloader-image.
- **MusicBrainz-fouten vulden het log** met zo'n 2.300 regels per dag. De wachttijd is verruimd, er
  wordt één keer opnieuw geprobeerd, en een tijdslimiet telt niet langer als fout.

## Global Version 0.9.1 (2026-08-14)

### 📄 Alleen ontwerpdocumenten
- Twee ontwerpen die al geschreven waren maar nog niet gemerged: origin-metadata sidecars voor de
  downloaders en de importer, en navigatie uit het track-info-scherm in MuMa Mobile.
- Er is geen enkele regel uitvoerende code gewijzigd. De images zijn inhoudelijk gelijk aan 0.9.0;
  deze release verandert het versienummer en verder niets.

## Global Version 0.9.0 (2026-08-14)

### 🔔 De webspeler vertelt het nu als er iets misgaat
- Een scrobble die de server nooit haalde, een rating die geweigerd werd, muziek die niet wilde
  starten, een stream die niet laadde — dat verdween allemaal in de browserconsole, waar niemand
  kijkt. Het verschijnt nu rechtsboven als melding.
- Fouten blijven staan tot je ze wegklikt of de pagina ververst; waarschuwingen en bevestigingen
  verdwijnen vanzelf. Dezelfde melding twee keer telt op in plaats van te stapelen.
- Alleen speler-fouten en dingen die jij zelf deed worden gemeld. Achtergrondwerk blijft stil, en
  de beheertabbladen houden hun eigen statuspanelen.

### 🚫 Geen blokkerende alert-popups meer
- Een nummer verversen en de wachtrij als afspeellijst opslaan gebruikten nog `alert()`-popups.
  Die zetten de pagina stil en pasten nergens bij. Beide melden nu via de meldingen.

### ⭐ Geweigerde ratings en verloren scrobbles
- In 0.8.3 stopten de sterren met doen alsof een geweigerde rating was opgeslagen. Nu krijg je er
  ook een melding van, en dezelfde controle geldt voortaan voor scrobbles — die gingen tot nu toe
  op precies dezelfde manier stilletjes verloren.

## Global Version 0.8.3 (2026-08-14)

### 🎬 YouTube-downloads worden nu getagd zoals SoundCloud-downloads
- De artiesten bleven in de titel staan. De YouTube-tak had helemaal geen artiest-herkenning; er zat
  één handgeschreven split in die alleen werkte zolang de artiest-tag nog gelijk was aan de
  kanaalmap. Zodra YouTube z'n eigen muziek-credits meegaf, klopte dat niet meer en gebeurde er
  niets. `Deadly Guns & The Dark Horror - In The Pit (Official Videoclip)` bleef dus zo staan.
- Ook plakte hij de gevonden artiest ernaast in plaats van erover, waardoor de kanaalnaam als
  tweede artiest bleef hangen.
- YouTube draait nu dezelfde regels als SoundCloud: streepje, `@`, `by`, `presents`, `feat.` en
  losse artiesten, gecontroleerd tegen je artiestenlijst. Het album, de uitgever, de festival-
  herkenning en de kanaal-naar-genre-lookup blijven YouTube-eigen.

### 🏷️ Geen genre `Music` meer op YouTube-nummers
- yt-dlp valt voor het genre terug op de YouTube-categorie van de video als er geen echt genre is,
  en die is bij muziek altijd `Music`. Bij video's zonder categorie kwamen zelfs de YouTube-
  trefwoorden als genre binnen. Allemaal belandden ze in je genre-wachtrij.
- Nieuwe downloads krijgen dit niet meer. Voor wat al binnen is zet de migratie de YouTube-
  categorieën op de zwarte lijst en vraagt hij de tagger de YouTube-map opnieuw te bekijken, zodat
  bestaande nummers ook opgeschoond worden.

### 🔐 De systeem-API-sleutel staat niet meer in de broncode
- De sleutel zat als fallback in tien routers. Dat is eruit; er is nu één plek die hem uitleest en
  die weigert te werken als er geen sleutel is ingesteld.
- **De sleutel zelf is hiermee niet vervangen.** Hij staat nog in de git-geschiedenis en blijft
  geldig tot je hem overal roteert.

### 🗂️ De browse-weergaven zitten onder één inklapbare Library
- Scheelt ruimte in de navigatie.

## Global Version 0.8.2 (2026-08-12)

### 🏷️ Genres worden nu herkend ongeacht hoofdletters
- SoundCloud levert het genre precies zoals de uploader het typte. `uptempo` werd geaccepteerd,
  maar `Uptempo`, `UPTEMPO`, `techno`, `hardcore` en `frenchcore` gingen de prullenbak in als
  "onbekend genre", terwijl het genre wél in je regels stond — alleen met andere hoofdletters.
- Dat matcht nu hoofdletter-ongevoelig, en er wordt weggeschreven zoals jij het genre hebt
  opgeslagen. Je krijgt dus geen `uptempo` meer náást `Uptempo Hardcore` bij hetzelfde nummer.

### ⏱️ De genre-fetcher verspilt geen minuut meer aan verdwenen nummers
- Na elke bevraging wachtte hij een volle minuut, ook na een verwijderd nummer (404) of een nummer
  dat SoundCloud alleen versleuteld uitlevert. Een weigering (403) werd bovendien genegeerd, waarna
  de volgende duizend nummers tegen dezelfde weigering aanliepen.
- Nu wordt onderscheid gemaakt: verdwenen nummers kosten 5 seconden, een weigering leidt tot een
  oplopende pauze van 5 minuten tot maximaal een uur, en vijf weigeringen op rij stoppen de ronde.
- Het eindoverzicht laat zien hoeveel nummers verdwenen waren, hoeveel weigeringen er waren en wat
  er anders misging.

## Global Version 0.8.1 (2026-08-08)

### 🎵 Elk genre van een nummer is nu een eigen link
- Staan er meerdere genres bij een nummer, dan was de hele reeks één link — klikken op
  `hardstyle, hardcore` zocht naar een genre met precies die naam, dat niet bestaat.
- Nu is elk genre apart aanklikbaar en kom je gewoon bij het genre waar je op klikt.
- De kolom leest verder onveranderd; alleen de links zijn opgesplitst.

## Global Version 0.8.0 (2026-08-07)

### 🎨 Groen of Ultrasonic-blauw, en het icoon kies je los
- De app heeft nu twee accentkleuren: het vertrouwde MuMa-groen, of het indigo van het oude
  Ultrasonic. Je vindt het onder Instellingen → Uiterlijk.
- Het app-icoon is een aparte instelling in dezelfde twee kleuren. Blauw accent met een groen icoon
  mag gewoon; de twee staan los van elkaar.
- De oude thema-instelling bood Dag & Nacht, Donker en Zwart aan, en alle drie leverden precies
  hetzelfde zwarte thema op. Die keuze doet nu eindelijk iets.
- Sets-modus houdt in beide thema's een eigen kleur, zodat je in één oogopslag ziet of je in
  nummers of in sets zit.
- Sommige launchers halen de app van je beginscherm als het icoon verandert; de app zegt dat erbij
  op het moment dat je wisselt.

### 🎧 De laatste koptelefoontjes zijn weg
- De meldingen voor downloads en afspelen tonen het MuMa-merkteken in plaats van het geërfde
  Ultrasonic-koptelefoontje.

## Global Version 0.7.0 (2026-08-07)

### 📜 Een logboek in plaats van een meldingenlijst
- Elke dienst schrijft nu gebeurtenissen met een niveau — `INFO`, `WARNING`, `ERROR`, `CRITICAL` —
  rechtstreeks naar een nieuwe `events`-tabel. Die tabel is de bron van waarheid; ntfy is voortaan
  een afnemer in plaats van de enige plek waar een melding ooit bestond.
- De tab **Meldingen** heet nu **Logboek** en heeft filters die er toe doen: chips per niveau met
  een teller, een filter per dienst, een tijdvenster en zoeken. De tellers blijven staan als je een
  niveau uitzet, want juist dan wil je zien wat er achter schuilgaat.
- Een nieuw ntfy-onderwerp krijgt automatisch alles vanaf `WARNING`, met een eigen prioriteit en tag
  per niveau. Herhalingen binnen vijf minuten worden samengevoegd, zodat één haperende verbinding je
  telefoon niet plat legt.
- `GET /health` rapporteert nu echt de database en de achtergrondlussen en geeft 503 bij problemen,
  in plaats van altijd `ok` te zeggen.

### 🎵 Nummerinfo in de app met één tik
- Tik op de titel van het spelende nummer en er schuift een venster omhoog met alles wat we weten:
  de hoes op een vervaagde versie van zichzelf, de vijf sterren, en artiest en album als regels waar
  je op door kunt klikken.
- Songtekst, delen, bookmark en verversen staan er als knoppen. Daaronder genre, tracknummer,
  uitgiftedatum en duur, met de technische details dichtgeklapt. Lang indrukken op het pad kopieert
  het.
- Het overloopmenu rechtsboven raakt daarmee zeven regels kwijt en gaat weer over de wachtrij en de
  speler. Velden die het nummer niet heeft verdwijnen nu, in plaats van als `Jaar: ` te blijven staan.

### 🔎 Sorteren en filteren op genres, labels en afspeellijsten
- De drie overzichten hadden geen enkele knop: genres alfabetisch met alles onder tien tracks
  stilzwijgend weggelaten, labels alfabetisch zonder aantallen, afspeellijsten in willekeurige
  volgorde. Ze delen nu een zoekveld, een sorteersleutel met richting, een favorietenchip en een
  live "getoond van totaal".
- Genres en labels krijgen chips voor **minimaal 10/50/100** in plaats van de vaste drempel, dus de
  lange staart is verborgen maar bereikbaar. Afspeellijsten sorteren op lengte en laatste wijziging
  en krijgen een chip voor van mij / openbaar / privé.
- Labels en afspeellijsten kun je nu favoriet maken, net als genres al kon, en die lijsten volgen je
  account.

### 🐛 Opgelost
- Op een label klikken filterde op het verkeerde: `label:Kompakt: Total` werd op elke dubbele punt
  gesplitst. Namen worden nu heel genomen. Een genre of zoekterm van een ander scherm versmalde
  bovendien stilletjes het label dat je net had aangetikt; die filters worden nu gewist.
- Het beheerscherm bleef na sluiten doorvragen naar de voortgang van artiestafbeeldingen.

## Global Version 0.6.0 (2026-08-06)

### 📻 Radiokanalen die ergens over gaan
- Een kanaal was voorheen "de hele bibliotheek" of hooguit één genre. Nu is een kanaal een
  **opgeslagen filter**: label, genre, artiest, lengte, jaar of waardering, in elke combinatie.
  Q-dance Records en Dirty Workz zijn daarmee twee kanalen in plaats van allebei "hardstyle".
- Kanalen beheer je op de **beheerderspagina**: aanmaken, bewerken, in en uit de lucht halen. Met
  **proefdraaien** zie je vóór het opslaan hoeveel tracks een filter oplevert, met een voorproefje.
  Dat is meteen de plek waar een labelnaam die de server niet kent boven water komt.
- De speler laat je **kiezen** zodra er meer dan één kanaal in de lucht is, met per kanaal een
  regeltje over wat het draait. Is er maar één kanaal, dan begint die gewoon meteen.

## Global Version 0.5.5 (2026-08-06)

### 🎨 MuMa stond er twee keer
- Het logo met de naam **MuMa** stond zowel links in de zijbalk als rechtsboven naast je profielknop.
  Die rechterbovenhoek is nu leeg op de profielknop na.

## Global Version 0.5.4 (2026-08-06)

### 🐛 Drie foutjes die bij het testwerk boven water kwamen
- **"Zie meer" in de zoekresultaten werkt weer.** Klikken op die link deed niets — de volledige
  resultatenlijst ging niet open.
- **Een kapot m4a-bestand op een alleen-lezen schijf** liet de tagger struikelen met een
  onbegrijpelijke foutmelding in plaats van het bestand netjes over te slaan.
- Een interne hulpklasse (`BoundedTreeSet`) leverde een lege lijst op als je hem met bestaande
  inhoud aanmaakte. Niets in de app gebruikte dat, maar de valkuil is nu weg.

### 🧹 Opgeruimd
- Twee schermen in het beheergedeelte die nergens meer werden gebruikt zijn verwijderd.

## Global Version 0.5.3 (2026-08-05)

### 🧪 Veel meer van MuMa wordt nu automatisch getest
- De webinterface ging van 25% naar 80% getest, de Python-diensten van 78% naar 88%. Concreet: het
  inlogscherm inclusief de Google-toegangsaanvraag, het startscherm, de speler, artiest- en
  albumpagina's, dynamische afspeellijsten, tagger-regels, genre-curatie, de ListenBrainz-import en
  de bibliotheekbrowser worden nu bij elke wijziging nagelopen.
- De ml-analyzer had helemaal geen tests. Die zijn er nu voor de analyzer zelf, de
  onderhoudsscripts en de voorspeller.

### 🔧 Het dekkingscijfer van de muziekserver klopte niet
- Het rapport voor de server keek naar 18 bestanden van de 818, oftewel 453 van de 76 000 regels.
  De "36,9%" ging dus over minder dan 1% van de code. Oorzaak: een bouwoptie die veel bronbestanden
  samenvoegt, waardoor de meting niet meer bij de echte bestanden kon komen. Die staat nu uit tijdens
  het meten en blijft aan voor wat er wordt uitgerold. Het rapport dekt nu 686 bestanden en 44 034
  regels.
- Voor de Android-app telt de meting niet langer automatisch gegenereerde databasecode mee — dat was
  bijna een vijfde van de app, en daar hoort niemand tests voor te schrijven.

## Global Version 0.5.2 (2026-08-05)

### 🎨 MuMa heeft eindelijk een eigen naam en een eigen logo
- De app op je telefoon heette "MuMa Mobile" en het tabblad in je browser "MuMa Spotify". Dat is nu
  overal gewoon **MuMa** — Spotify noemt zijn app tenslotte ook geen "Spotify Mobile".
- Er is een eigen beeldmerk: vijf staafjes in een groene schijf, waarvan de bovenrand een M vormt.
  Van een afstand een equalizer, van dichtbij de M van MuMa. Je ziet hem op je startscherm, in het
  tabblad van je browser, op het inlogscherm, in de zijbalk en rechtsboven in de webpagina.
- Tot vandaag stond er in de zijbalk letterlijk het logo van Spotify. Dat is vervangen.
- De app installeert gewoon over de vorige heen; je hoeft niets opnieuw in te stellen.

### ⏮️ "Onlangs afgespeeld" onthoudt weer wat je hebt geluisterd
- Het raster op de startpagina bewaarde alleen wat je zelf aantikte in een lijst. Wie via Android
  Auto, de melding of de wachtrij luisterde, liet dus niets achter: een avond muziek in de auto
  veranderde er niets aan.
- Ook "Laatst gespeelde genres" werd nergens meer bijgewerkt, terwijl Android Auto die lijsten wél
  bleef tonen — ze waren daardoor altijd leeg.
- Allebei worden ze weer bijgehouden: elk nummer dat je uitluistert zet zijn album in het raster en
  zijn genres in de genrelijst.

## Global Version 0.5.1 (2026-08-05)

### 📲 "Controleer op updates" ziet nieuwe versies weer
- Sinds de naamswijziging heette het geüploade installatiebestand `muma-mobile-...` in plaats van
  `ultrasonic-...`, en de downloadsite gebruikt precies dat stukje naam om bij te houden welke
  versies bij elkaar horen. De app vroeg nog naar de oude naam en kreeg daardoor niets terug:
  versie 6.9.0 was onzichtbaar en je telefoon meldde netjes dat je bij was.
- De bestandsnaam staat weer op het oude, en de app vindt zijn updates weer. Verder verandert er
  niets — de app blijft MuMa Mobile heten.

## Global Version 0.5.0 (2026-08-05)

### 🎬 Muziekvideo's worden nu echt als video binnengehaald
- In de database stond al jaren per kanaal of het audio of video moest zijn, en acht kanalen —
  Q-dance, Intents, Bass Events, Art of Dance, Da Tweekaz, Elektrum, Supremacy en B2S — stonden op
  video. Daar werd nooit iets mee gedaan: ze werden gewoon als audio opgehaald. Vanaf nu niet meer.
- Video komt binnen in de hoogste kwaliteit die YouTube aanbiedt. Geen limiet: waar er 4K is, krijg
  je 4K.
- De video's landen in `/mnt/music/Youtube_Video`, netjes per kanaal, buiten je muziekbibliotheek.
  Je speler en de scanner zien er dus niets van, en er komt geen mkv tussen je nummers te staan.
- Audio gaat voor. Een ronde haalt eerst alle muziekkanalen op en pas daarna de videokanalen, dus
  als YouTube ons onderweg afknijpt kost dat de video's en niet je muziek.
- **De 360p-bestanden waren geen keuze maar een storing.** Zonder ffmpeg kan yt-dlp beeld en geluid
  niet samenvoegen en pakt het het enige kant-en-klare bestand dat YouTube nog geeft: 640x360. De
  downloader weigert nu te draaien als ffmpeg ontbreekt, in plaats van daar stilletjes nog meer van
  te maken.
- Wat er al aan losse videobestanden in je muziekmap rondslingert kun je opvragen met
  `tools/list_youtube_video_residue.py`. Die laat zien welke het zijn en hoe groot; weggooien doe je
  zelf.

**Let op:** zet `youtube_video_folder` op `/mnt/music/Youtube_Video` in je `.env` of in het
instellingenscherm, anders slaat de downloader de videokanalen over.

## Global Version 0.4.0 (2026-08-05)

### ⭐ Favoriet bestaat niet meer los: 5 sterren *is* favoriet
- Je had twee manieren om te zeggen dat je iets goed vindt, en die konden elkaar tegenspreken: een
  nummer op vier sterren dat ook een hartje had, of een hartje zonder waardering. Vanaf nu is er
  één schaal, van 0 tot 5, en het hoogste cijfer is je favoriet.
- Je favorietenlijsten blijven staan waar ze stonden. Ze tonen voortaan wat vijf sterren heeft.
- De hartjes en losse sterknoppen zijn weg: in de app uit de nummerlijsten, uit de speler en uit
  het menu daarachter, en in de webinterface van de server. De vijf sterren blijven over.
- **Albums kun je nu ook waarderen.** De ster op een albumregel zet vijf sterren in plaats van een
  vlaggetje dat nergens heen ging — en die waardering belandt wél in je bestandstags.
- Waardeer je vanuit een andere Subsonic-app? Die knop blijft werken en zet vanaf nu vijf sterren.
  Voorheen ging zo'n hartje onderweg naar je tags verloren.
- Alles wat je eerder als favoriet had gemarkeerd wordt omgezet naar vijf sterren. Had je al een
  eigen waardering op iets staan, dan blijft die staan — een echte beoordeling wint altijd.

### 📱 De app heet nu MuMa Mobile
- De Android-app heet niet langer Ultrasonic maar **MuMa Mobile**, in lijn met de rest van MuMa.
  Je ziet de nieuwe naam op je startscherm, in de meldingen en in de app zelf.
- Je servers, instellingen en downloads gaan gewoon mee — de update installeert er overheen, je
  hoeft niets opnieuw in te stellen en niet opnieuw in te loggen.
- **Heb je een widget op je startscherm staan? Haal die er na het bijwerken één keer af en zet hem
  er opnieuw op.** Je startscherm onthoudt de oude naam van de widget, dus tot je dat doet meldt hij
  "kan widget niet laden". Dit is eenmalig.
- De vaste server in de app heet nu "MuMa" in plaats van "LMS".

## Global Version 0.3.0 (2026-08-05)

### ⭐ In Android Auto kon je alleen 1 ster geven
- Stond een nummer op 5 sterren, dan werd het 1. Stond het op 1, dan bleef het 1. En een nummer
  zonder waardering kreeg er ook 1 — een andere waardering was in de auto niet te geven.
- De knop geeft de waardering die erop staat mee aan de auto, maar Android Auto stuurt die
  informatie niet terug. De app begon daardoor elke tik weer bij nul en kwam altijd op 1 uit.
- De knop kijkt nu naar het nummer dat speelt en loopt weer netjes door 0, 1, 2, 3, 4, 5 en terug
  naar 0. Een waardering die je op de telefoon geeft, staat nu ook meteen goed op de knop in de auto.

### 🎚️ Zelf kiezen hoeveel nummers een genre oplevert
- Op het genre-scherm in de Android-app staat nu een keuzelijst: 10, 25, 50, 100 of 500 nummers.
- Het genre dat je daarna aantikt, laadt precies dat aantal.
- De instelling onder Instellingen deed tot nu toe niets — die werd onder een andere naam
  opgeslagen dan de app uitlas, dus je kreeg altijd 100 nummers. Beide gebruiken nu dezelfde
  waarde.

## Global Version 0.2.1 (2026-08-03)

### 🔑 Uitgelogd worden na een deploy is voorbij
- Na elke deploy werd iedereen er binnen enkele seconden weer uitgegooid: "verkeerde
  gebruikersnaam of wachtwoord", terwijl er niets mis was met het wachtwoord.
- De muziekserver stuurde zijn wachtwoordcontroles door dezelfde verbinding die bedoeld is voor
  beleefde aanvragen aan diensten als ListenBrainz: één tegelijk, opnieuw proberen bij een fout, en
  bij elke storing dertig seconden lang helemaal niets meer versturen. Eén verbindingsfout — en die
  levert elke deploy op, want music-manager wordt opnieuw opgebouwd — legde dus *alle* aanmeldingen
  dertig seconden stil. Alles wat stond te wachten liep in zijn eigen time-out van tien seconden, en
  zo'n time-out werd naar buiten gemeld als een fout wachtwoord. Apps gooiden daarop hun opgeslagen
  inloggegevens weg en probeerden opnieuw, wat de rij weer vol hield: het herstelde nooit uit
  zichzelf, alleen een herstart van de server hielp.
- Wachtwoordcontroles gaan nu rechtstreeks en los van elkaar, met een time-out van twee seconden in
  plaats van tien. Een gezonde controle is in minder dan een tiende seconde klaar.
- En als de inlogdienst echt even onbereikbaar is, krijg je dat nu ook te horen in plaats van
  "verkeerd wachtwoord". Je app houdt je gegevens gewoon vast en probeert het opnieuw.

## Global Version 0.2.0 (2026-08-03)

### 📱 Tracklijst met drie regels
- In de Android-app staan album en artiest samengeperst op één regel, waardoor beide afkappen
  zodra een titel wat langer is.
- Onder Instellingen > Appearance kies je nu tussen 2 regels (zoals het was) en 3 regels: titel,
  album en artiest onder elkaar, met rechts de sterren, de releasedatum en de speelduur.
- De compacte weergave blijft de standaard en ziet er onveranderd uit.

### 🛠️ Beheer-tabblad was voor iedereen verborgen
- Ook beheerders zagen het Beheer-tabblad niet meer.
- De controle op beheerdersrechten gaat naar `api/auth/verify`, en dat adres viel onder het
  `/api/auth/`-voorvoegsel dat de app behandelt als "hier hoeft geen sleutel bij". Het verzoek
  vertrok dus zonder sleutel: 401, leeg antwoord, geen beheerder.
- De app noemt nu de vier inlogadressen apart in plaats van een heel voorvoegsel, en de controle
  wordt opnieuw gedaan zodra de app terugkomt uit de achtergrond en zodra het automatisch inloggen
  een sleutel heeft opgehaald.

### 🔁 Scherm draaien verdubbelde de afspeellijst
- Honderd nummers werden er tweehonderd, tweehonderd werden er vierhonderd.
- Bij het draaien wordt het scherm opnieuw opgebouwd en zet de app de opgeslagen sessie terug —
  maar de speler zelf blijft gewoon draaien met de lijst er nog in, en terugzetten betekent
  toevoegen.
- De opgeslagen sessie wordt nu alleen nog teruggezet in een lege speler. Draait de speler al, dan
  is die de bron van waarheid en blijft de lijst zoals hij was.

## Global Version 0.1.3 (2026-08-02)

### 🔐 Inloggen hield het maar een paar seconden vol
- Wie inlogde, stond er even later weer buiten: op Android verscheen "The server rejected the stored
  credentials" en daarna "Logging out", in de webinterface kwam het inlogscherm terug.
- De snelheidsbegrenzer op de inlogpunten, deze cyclus toegevoegd, ging ervan uit dat
  `/api/auth/login` een inlogformulier is. Het is óók het punt waar de muziekserver bij *elk*
  Subsonic-verzoek het wachtwoord laat controleren, over een interne verbinding die geen
  clientadres meedraagt. Alle gebruikers deelden daardoor één tegoed van tien aanroepen per minuut,
  en een beginscherm dat zijn secties tegelijk ophaalt was er in een paar tellen doorheen.
- Daarna las de muziekserver de weigering als "verkeerd wachtwoord" en logde elke client zichzelf
  netjes uit. Opnieuw proberen maakte het erger: die afwijzingen voedden ook de eigen begrenzer van
  de muziekserver, die vervolgens het IP-adres van de gebruiker begon te weren.
- Alleen afgewezen pogingen tellen nu nog mee, en een login telt per account in plaats van per
  beller. Bladeren door de bibliotheek kost dus niets meer, en één account waarop wordt gegokt sluit
  niemand anders meer buiten. Een wachtwoord raden blijft begrensd, en spraying blijft afgevangen
  door de begrenzer van de muziekserver zelf, die wel het echte clientadres ziet.

## Global Version 0.1.2 (2026-08-02)

### 🎧 Eén ontoegankelijke track legde de hele SoundCloud-downloader stil
- yt-dlp meldt een abonnee-only, geoblokkeerde of verwijderde track als een 403. De downloader las elke
  403 als "SoundCloud duwt ons weg", parkeerde daarop de hele bron, brak de resterende accounts van een
  ronde langs 1110 accounts af, en noteerde het account niet als gecontroleerd — waardoor de volgende
  ronde dezelfde track raakte en dezelfde 403 kreeg.
- De teller daarachter ging alleen terug naar nul na een ronde langs álle accounts zonder ook maar één
  403, wat met één permanent ontoegankelijke track nooit gebeurt. De wachttijd klom zo naar het plafond
  van 24 uur en bleef daar. Downloads lagen twee dagen stil terwijl SoundCloud zelf gewoon antwoordde.
- Een 403 wordt nu gelezen voor wat het is. Losse tracks worden onthouden en bij volgende rondes
  overgeslagen, en de bron wordt alleen nog geparkeerd bij een expliciete 429 of wanneer meerdere
  accounts op rij niets opleveren. De wachttijd zakt vanzelf terug met de tijd en het plafond gaat van
  een dag naar een uur.

### 🦊 De downloader presenteert zich consistent
- Er ging een Chrome 120 user-agent uit terwijl de meegestuurde cookies van Firefox kwamen; precies de
  ongerijmdheid waar de botdetectie vóór SoundCloud op let. Dat is nu Firefox, passend bij de container
  waar de cookies vandaan komen, en het is een instelling geworden in plaats van een vaste waarde.
- Cookies worden bovendien volledig gelezen. yt-dlp kopieert alleen de cookiedatabase, terwijl Firefox
  via een logbestand schrijft waar de nieuwste cookies nog in kunnen staan — juist de cookie die de
  botdetectie steeds ververst. Het profiel wordt nu eerst samengevoegd en dan pas gelezen.

### ⏱️ yt-dlp veroudert niet meer tussen releases
- yt-dlp levert reparaties voor wijzigingen bij SoundCloud en YouTube binnen dagen, maar de images
  werden alleen tijdens een release gebouwd. De downloader kon dus een yt-dlp draaien die ouder was dan
  het probleem waar hij op stuitte. Een wekelijkse geplande pijplijn bouwt en publiceert de
  downloader-image nu opnieuw vanaf master.

## Global Version 0.1.1 (2026-08-02)

### 🔧 De scanner liep op elk bestand stuk
- Het indexeren van genres uit tags las de genres via een methode die niet op `BaseSong` bestaat.
  Elk bestand gaf daardoor een fout die de scanner opving, logde en verder negeerde: op productie
  waren 1427 van de 1429 scannerregels deze ene fout.
- De schade reikte verder dan alleen ontbrekende genres. De fout viel vóór het wegschrijven van de
  bestandsgegevens, en de databaseverbinding bevestigt elke stap meteen. Nummers en artiesten
  werden dus wel opgeslagen, wijzigingsdatums van bestanden niet — waardoor elke scan de hele
  bibliotheek opnieuw doorliep en de genretabel leeg bleef.
- De tests zagen dit niet, omdat ze een nummer beschreven met een dubbel dat elke denkbare
  methodenaam accepteert. Ze gebruiken nu een dubbel dat alleen de echte methodes kent, zodat een
  verzonnen aanroep voortaan in de testsuite sneuvelt in plaats van op productie.

### 🔁 Een downloadcontainer startte zichzelf elke minuut opnieuw
- De volledige SoundCloud-sweep is bedoeld om één ronde te doen en te stoppen, maar stond ingesteld
  om bij elke afsluiting herstart te worden — precies wat hij per ontwerp doet. Hij was 21 keer
  opnieuw gestart toen dit gevonden werd. Hij wordt nu met rust gelaten zodra zijn ronde klaar is.

### ▶️ YouTube kon de JavaScript-controles van de site niet oplossen
- De downloader-image had geen JavaScript-runtime, waardoor elke video meldde dat het oplossen van
  de handtekening mislukte en alleen formaten zonder controle bereikbaar bleven. De image bevat nu
  de oplosscripts en Deno om ze uit te voeren.
- Dit haalt de waarschuwingen weg, maar heft de snelheidsbeperking die YouTube op dit moment
  oplegt niet op.

## Global Version 0.1.0 (2026-08-02)

### 🕰️ Memories: wat er op deze dag werd uitgebracht
- De bibliotheek bevat releasedatums waar tot nu toe niets mee gebeurde. De webinterface en de
  Android-app openen nu met een korte rij "Vandaag, 8 jaar geleden", met daarachter een volledig
  scherm met per jaar een sectie die je in één tik afspeelt.
- Alleen tags met een volledige datum kunnen zeggen wat er op een bepaalde dag gebeurde; een tag
  met alleen een jaar, of alleen een jaar en een maand, verschijnt dus niet.
- Levert een dag geen enkele treffer op, dan wordt er drie dagen naar beide kanten gekeken. In dat
  geval staat er "deze week" in plaats van "vandaag", zodat de kop nooit meer precisie claimt dan
  de tags hebben.
- De rij op de startpagina kun je uitzetten in de instellingen. Memories zelf blijft staan waar het
  staat: in de zijbalk op het web, en in het Bibliotheek-tabblad op Android.
- Je apparaat stuurt zijn eigen datum mee, dus een telefoon in een andere tijdzone krijgt zijn
  eigen "vandaag".
- Het aanvullen van ontbrekende releasedatums via MusicBrainz of Discogs is apart werk en zit hier
  nog niet in.

### 🩺 Diagnostiek versturen zonder op een crash te wachten
- **Diagnostiek versturen zonder op een crash te wachten.** Crashrapportage kwam pas bij de
  volgende start op gang, en alleen als de app echt was gestopt. Bij een mislukte call of een leeg
  scherm blijft de app draaien, dus dat bereikte de server nooit. In Instellingen staat nu "Send
  diagnostics now" onder Muma: die stuurt het log van de huidige sessie op en zet een kopie in
  Downloads/UltrasonicLogs. De knop staat bewust buiten de debug-categorie, want die is verborgen
  in release builds. Anders dan het automatische rapport trekt hij zich niets aan van de
  "Crash detection"-schakelaar — op de knop drukken is toestemming genoeg — en hij gooit nooit een
  crashbestand weg dat nog niet gerapporteerd is.

### 🖼️ Artiestenplaatjes op de startpagina
- Een artiest-snelkoppeling die je bewaarde toen de server nog geen foto had, bleef grijs. Zo'n
  kaart zoekt de afbeelding nu alsnog op en repareert de bewaarde kopie: één keer opzoeken per
  artiest.
- Artiesten zonder afbeelding kostten bij elk terugscrollen opnieuw een mislukte aanvraag. Die
  worden nu twaalf uur onthouden, en alleen als de server echt "niet gevonden" zei — een time-out
  of een storing zegt niets over of de foto bestaat.

### 🔎 Minder zoekvelden waar ze niets toevoegen
- Het tabblad Ratings is vijf vaste kaarten die allemaal tegelijk in beeld staan, en Jaren is een
  korte lijst getallen in een vaste volgorde. Op allebei is het zoekveld weg; de tabbladen die wél
  met je bibliotheek meegroeien houden het.
- Jaren staat nu met het nieuwste jaar bovenaan.

### 🧹 "MuMa Sync"-scherm verdwenen
- Het scherm met zes knoppen (inloggen, tegels laden/schrijven, tegels wissen, instellingen
  laden/schrijven) is weg. Tegels synchroniseren zichzelf via de tegelbewerker en het inloggen
  gebeurt al bij het opslaan van een server. De back-up/herstel-knoppen dumpten elke voorkeur en
  konden een werkende installatie overschrijven met de staat van een ander apparaat. Je MuMa-ID en
  API-sleutel blijven gewoon in de instellingen staan.

## Global Version 0.0.61 (2026-08-02)

### ⭐ De sterknop in Android Auto zet nu een cijfer
- De knop zette voorheen alleen de favoriet-vlag aan of uit. De waardering van 1 tot 5 sterren —
  waar de rest van de app op sorteert en filtert — was vanuit de auto niet te bereiken.
- De knop loopt nu door zes standen: een lege ster voor geen waardering, daarna een ster met het
  cijfer 1 tot en met 5 erin, en vanaf 5 weer terug naar leeg.
- Favorieten blijven op de telefoon gewoon werken; alleen hun knop in de auto vervalt. Zo blijven
  shuffle en herhalen op de hoofdbalk staan in plaats van in het overloopmenu.

## Global Version 0.0.60 (2026-08-02)

### 👤 De artiestenpagina begint nu bij de artiest
- Op een artiest tikken bracht je meteen bij de albumlijst; alleen de naam in de balk bovenaan
  verschilde per artiest. Bovenaan staat nu een kop met de foto van de artiest, de naam,
  "12 albums · 143 nummers", de jaren waarin de discografie loopt en de genres.
- De "alles afspelen"-knop zit in die kop en zet de nummers van de artiest in de wachtrij, net
  zoals "nu afspelen" in het ingedrukt-houden-menu al deed.
- Kom je via zoeken of via het beginscherm bij een artiest, dan werden de aantallen nergens
  bewaard; die worden nu uit de albums op het scherm zelf afgeleid in plaats van weggelaten.

### 🏷️ Labels doorbladeren op Android
- Je kon nummers al filteren op platenlabel, maar nergens zien welke labels je bibliotheek
  bevat — je moest de naam dus al kennen. Labels staan nu als tabblad in Library, naast Genres,
  en een tik opent de nummers van dat label.

### 🗣️ De app praat Sallaands en Brabants, en het Nederlands is af
- Dezelfde twee dialecten die de webinterface in 0.0.59 kreeg, kies je nu ook in de app via het
  taalmenu in Instellingen.
- Het Nederlands was 163 teksten korter dan het Engels, en 28 teksten van deze fork stonden in
  het Nederlands in de Engelse bestanden — een Engelstalige telefoon liet dus "Artiesten",
  "Jaren" en "Goedkeuren" zien. Beide zijn nu compleet.

### 🖼️ Artiesten zonder opgehaalde foto zijn niet langer grijs
- Van de 51378 artiesten in de bibliotheek heeft de fotodienst er pas 11762; voor de rest liet
  elke client een grijs vlak zien. De server antwoordt nu met wat de artiest al heeft: de
  ingescande artiestfoto, of anders de hoes van zijn oudste release. Zodra er alsnog een echte
  artiestfoto binnenkomt, neemt die het over.

## Global Version 0.0.59 (2026-08-02)

### 🌍 De webinterface is vertaald — en praat Sallands en Brabants
- De hele interface is nu beschikbaar in het Nederlands en het Engels, van de speler tot de
  beheerpagina's. Voorheen stond de tekst vast in de schermen zelf, in een mengelmoes van beide
  talen: de knoppenbalk op je telefoon zei "Home", "Nummers", "Sets", "Bieb" en "Beheer" door elkaar
  heen. Je kiest je taal in Instellingen; de keuze gaat mee naar je andere apparaten.
- Voor de lol zitten er twee dialecten bij: **Sallands** en **Brabants**. Die dekken de speler-kant
  en de knoppen die je overal tegenkomt; de diepere beheerschermen blijven gewoon Nederlands, want
  daar valt weinig aan te lachen. Kies "Sallaands" of "Brabants" in Instellingen.
- Aantallen kloppen nu grammaticaal: "1 nummer" in plaats van "1 nummers".

## Global Version 0.0.58 (2026-08-01)

### 🔎 Zoeken en sorteren in de Library-tabbladen (Android)
- Boven Artiesten en Albums staat nu een zoekveld. Zoeken kijkt door je hele bibliotheek, niet
  alleen door wat er toevallig geladen is, dus "angerfist" vindt die artiest ook als je nog
  bovenaan de A's staat.
- Sorteren kan op naam, aantal nummers, aantal albums, recent toegevoegd en willekeurig; bij albums
  ook op artiest en jaar. Bij elke artiest staat nu hoeveel albums en nummers je van hem hebt.
- De tabbladen Genres, Jaren, Festivals, Lineups en Ratings hebben hetzelfde zoekveld.
- Op een artiest tikken opende voorheen een leeg scherm; je komt nu op het album-overzicht van die
  artiest.

### ⚙️ Serverbeheer zit nu in de beheerpagina, niet meer in de instellingen van de speler
- Scanner en mediabibliotheken zijn eigen tabbladen in het beheerscherm geworden, zodat alles
  waarvoor je beheerder moet zijn op één plek staat. In de speler blijven alleen je persoonlijke
  instellingen over.
- Subsonic-tokens worden voortaan door een beheerder uitgegeven vanuit het gebruikersscherm.

### 🔎 Zoeken en sorteren in de Library-tabbladen (Android)
- Boven Artiesten en Albums staat nu een zoekveld. Zoeken kijkt door je hele bibliotheek, niet
  alleen door wat er toevallig geladen is, dus "angerfist" vindt die artiest ook als je nog
  bovenaan de A's staat.
- Sorteren kan op naam, aantal nummers, aantal albums, recent toegevoegd en willekeurig; bij albums
  ook op artiest en jaar. Bij elke artiest staat nu hoeveel albums en nummers je van hem hebt.
- De tabbladen Genres, Jaren, Festivals, Lineups en Ratings hebben hetzelfde zoekveld.
- Op een artiest tikken opende voorheen een leeg scherm; je komt nu op het album-overzicht van die
  artiest.

### ⚙️ Serverbeheer zit nu in de beheerpagina, niet meer in de instellingen van de speler
- Scanner en mediabibliotheken zijn eigen tabbladen in het beheerscherm geworden, zodat alles
  waarvoor je beheerder moet zijn op één plek staat. In de speler blijven alleen je persoonlijke
  instellingen over.
- Subsonic-tokens worden voortaan door een beheerder uitgegeven vanuit het gebruikersscherm.

### 🌍 Taal instellen in de webinterface
- Onder Instellingen → Algemeen kun je nu kiezen tussen Nederlands en Engels. Je keuze wordt bij je
  account opgeslagen, dus hij gaat mee naar je andere apparaten en browsers. Ben je niet ingelogd, dan
  start de interface in de taal van je browser.
- Dit is de eerste stap: de techniek eronder is er nu, maar alleen de taalkeuze zelf is al vertaald.
  De rest van de schermen volgt stap voor stap.


## Global Version 0.0.57 (2026-08-01)

### 🔗 Knoppen op "Over" wezen naar de verkeerde site
- "Website openen" en "Bug melden" openden nog de pagina's van het originele Ultrasonic-project.
  Ze gaan nu naar muma.example.com en naar de issue-tracker van dit project zelf.

## Global Version 0.0.56 (2026-08-01)

### 🐛 Instellingen crashte de app
- Sinds 0.0.55 sloot de app meteen af zodra je Instellingen opende. Dat kwam door de nieuwe
  "Interface size"-optie: de percentages erin (100%, 75%, ...) werden per ongeluk als opmaakcode
  gelezen in plaats van als gewone tekst, waardoor het misging op het moment dat die regel getekend
  werd. Opgelost — Instellingen opent weer gewoon.

## Global Version 0.0.55 (2026-08-01)

### 📻 Radiomodus (beta): één uitzending, iedereen tegelijk
- De server bepaalt wat er speelt en houdt zelf de tijdlijn bij. Stem je later af, dan val je
  midden in het nummer binnen — precies waar de rest ook zit — in plaats van weer bij seconde nul
  te beginnen.
- Werkt in de webspeler en in Android Auto. Loopt je speler iets uit de pas, dan wordt dat met een
  onhoorbare snelheidscorrectie rechtgetrokken; alleen bij een groot verschil wordt er gesprongen.
- Hiermee is ook het oude "jam"-probleem weg, waarbij een meeluisteraar de positie van de host
  terugzette naar het begin.

### 📚 Library Browser: één overzicht over je collectie
- De tabbladen Library, Advanced Library en Statistieken zijn vervangen door één scherm.
- Zoeken op genre werkte hier nooit: de genres uit je bestandstags werden helemaal niet
  opgeslagen, en het scherm gaf bij elke serverfout een lege lijst zonder melding. Beide zijn
  verholpen — de scanner leest genres nu mee, en een fout laat zich zien als een fout.

### 📱 Android-app
- **De interface is kleiner**, standaard 75% van het oude formaat, ongeveer even compact als
  Spotify. Terug te zetten via Instellingen > Weergave > "Interface size".
- **Favoriete genres**: houd een genre ingedrukt in Library → Genres. Favorieten staan bovenaan met
  een sterretje, en het is dezelfde lijst als in de webspeler.
- **Een Favorieten-map in Android Auto**, met favoriete genres en playlists. Een favoriet genre
  begint direct met spelen, zonder eerst een jaar of sortering te kiezen.
- **Geen crashmelding meer bij het opstarten.** De app zag elke normale afsluiting door Android als
  een crash. Crashdetectie staat nu uit, en is aan te zetten onder Instellingen > Debug-opties.
- **Tijdvak-tegels** op Nummers/Livesets in plaats van tegels die alleen op één genre filterden.

### 🧰 Reparatiegereedschap voor dubbel geneste EP-mappen
- EP's die twee keer zijn gedownload belandden een map te diep, waardoor ze een verkeerd label
  kregen en de labellijsten vervuilden. `tools/fix_nested_ep_dirs.py` spoort die mappen op en vraagt
  per geval wat ermee moet gebeuren.

### 🖼️ Artist Images is nu een echte beheerpagina
- Zoeken werkt weer. Je krijgt nu álle artiesten die op je zoekterm passen te zien — mét én zonder
  afbeelding — in één lijst, met een filter voor "alle", "met afbeelding" en "zonder afbeelding".
- Per artiest kun je nu zelf ingrijpen: automatisch laten zoeken, een bestand uploaden, een
  afbeelding-URL plakken, de huidige afbeelding weghalen, of een eerder gevonden afbeelding alsnog
  als hoofdafbeelding instellen.
- Gaat er iets mis, dan zie je nu de foutmelding met een knop om het opnieuw te proberen, in plaats
  van een lege pagina zonder uitleg.

## Global Version 0.0.54 (2026-08-01)

### 🔀 Genres met een schuine streep worden nu gesplitst
- `Hardstyle/Hardcore` telde tot nu toe als één genre. Dat wordt nu netjes twee losse genres, die elk
  hun eigen status krijgen. Combinaties komen daardoor niet meer in je beoordeellijst terecht — die
  kwamen daar toch nooit een tweede keer voorbij.
- Artiesten blijven ongemoeid, dus een naam als **AC/DC** blijft heel.
- Bestaat er ooit toch een genre dat de streep echt nodig heeft? Keur het één keer goed en het wordt
  nooit meer gesplitst.
- Slash-genres die alleen door de vorige migratie waren goedgekeurd, worden bij het bijwerken meteen
  automatisch uit elkaar getrokken. Genres waar jij zelf een beslissing over nam blijven zoals je ze
  liet.

### 🧬 Samentrekkingen naar meerdere genres
- Een genre kan nu naar **meerdere** genres tegelijk gecorrigeerd worden: **Upterror** wordt
  `Uptempo Hardcore` én `Terror`, in plaats van dat je moet kiezen of het weggooien.
- In het Genre Curatie-scherm vink je bij "Corrigeren naar" gewoon meerdere genres aan.

## Global Version 0.0.53 (2026-08-01)

### 🔧 Genre Curatie werkt nu ook echt in productie
- De databasewijziging die bij 0.0.52 hoorde, is nooit meegeleverd: een regel in `.gitignore` hield
  alle `.sql`-bestanden tegen, dus de migratie stond wel lokaal maar nooit in de repository.
  Productie draaide daardoor nieuwe code op de oude databasestructuur, waardoor het
  Genre Curatie-scherm een foutmelding gaf en de tagger stilletjes geen genres meer wegschreef.
- De migratie wordt nu meegeleverd en bij de eerstvolgende deploy automatisch uitgevoerd. Je
  bestaande witte lijst, negeerlijst en backlog krijgen daarbij alsnog hun status.

## Global Version 0.0.52 (2026-08-01)

### 🎵 Genres: goedgekeurd, geweigerd of nog te beoordelen
- Elk genre heeft nu een duidelijke status. **Goedgekeurde** genres worden toegepast, **geweigerde**
  genres (`Entertainment`, `Arts`) verdwijnen van je tracks, en een genre kan ook **gecorrigeerd**
  worden in plaats van weggegooid: `uptempo` wordt `Uptempo Hardcore`.
- Genres die je nog niet beoordeeld hebt, blijven voortaan met rust gelaten. Ze worden geteld en op
  een lijst gezet, gesorteerd op hoe vaak ze voorkomen, zodat een handvol beslissingen het grootste
  deel van je bibliotheek opruimt.
- Hiermee is een fout verholpen waardoor élk genre dat de tagger ooit tegenkwam automatisch geldig
  werd. Je bestaande witte lijst, negeerlijst en backlog blijven behouden en krijgen de bijbehorende
  status.

### 🧹 Genres beoordelen in het beheer
- Nieuw tabblad **Genre Curatie** in het beheerscherm. Je begint bij de lijst die nog beoordeeld moet
  worden, met de genres die het vaakst voorkomen bovenaan.
- Per genre: goedkeuren, afkeuren, of corrigeren naar een genre dat je al hebt goedgekeurd. Bij elk
  genre staat in gewone taal wat er met je tags gebeurt, dus je hoeft de statussen niet te kennen.
- Een beslissing kun je altijd terugdraaien of veranderen. Wijzigingen gelden vanaf de volgende
  tagger-run.

## Global Version 0.0.51 (2026-07-31)
### 📱 Android-app: uitloggen, sneller opstarten en niet meer vastlopen op een fout wachtwoord
- Er zit nu een **uitlogknop** in het menu rechtsboven. Hij vraagt om bevestiging, stopt het
  afspelen en brengt je terug naar het inlogscherm; gedownloade muziek blijft staan.
- De **startpagina toont grijze plaatshouders** zolang hij laadt, en elke sectie verschijnt zodra
  die klaar is in plaats van pas als alles klaar is. De onderdelen worden bovendien tegelijk
  opgehaald, dus opstarten gaat merkbaar sneller.
- **Wordt je wachtwoord door de server geweigerd terwijl je al ingelogd was**, dan kom je nu terug
  op het inlogscherm met uitleg, in plaats van een app waarin elk scherm een foutmelding geeft.

## Global Version 0.0.50 (2026-07-31)
### 🚑 De Android-app crashte bijna elke keer dat je iets afspeelde
- In de uitgebrachte versie konden de **genres van een nummer** niet teruggelezen worden, waardoor
  de app onderuit ging zodra er een nummer in de speler geladen werd. Dit zat achter 15 van de 16
  crashmeldingen van 6.5.14 tot en met 6.5.18. Afspelen, "alles afspelen" en teruggaan naar het
  spelerscherm werken weer.
- **Een foutmelding die verscheen terwijl de app op de achtergrond stond, kon de app afsluiten** in
  plaats van de fout te tonen. Zo'n fout komt nu als gewone melding, of als korte toast wanneer er
  geen scherm beschikbaar is.

### 🚗 Android Auto liet weer lijsten zien
- Auto hield de serververbinding vast die het bij het starten had opgepakt. Wisselde je van server,
  paste je inloggegevens aan, of was de server even onbereikbaar, dan bleef Auto met de dode
  verbinding zitten: de mappen waren er nog, maar elke lijst kwam leeg terug — ook nadat het op de
  telefoon allang weer werkte. Auto haalt de verbinding nu bij elke aanroep opnieuw op.

### 🐌 Downloaders gaan zichzelf afremmen
- Een nieuw tabblad **Timing** onder Systeembeheer → Downloaders stelt de sweep-interval,
  wachttijden per account, batchgrootte en de backoff-ladders van SoundCloud, YouTube en Telegram
  in. Voorheen stonden die vast in de code.
- Krijgt een bron een **429**, dan verdubbelt de app zelf alle wachttijden voor die bron en parkeert
  hem tot de cooldown voorbij is. Dat overleeft nu een herstart, en halveert weer na genoeg schone
  rondes. Het tabblad toont de huidige factor, wanneer de bron weer wakker wordt, en wanneer de
  laatste 429 was.
- **SoundCloud wordt standaard veel rustiger bevraagd**: elke vijf minuten alle accounts is nu elk
  kwartier, met daarbovenop zes uur cooldown per account — ruwweg 72 keer minder verkeer.

### 🔑 Duidelijkere foutmeldingen bij inloggen (Ultrasonic)
- Een verkeerd wachtwoord zei voorheen **"Kon geen verbinding maken met LMS"**, ook als de server
  gewoon antwoordde. Dat leidde tot zoeken naar een storing die er niet was. Nu staat er
  "Verkeerde gebruikersnaam of wachtwoord ... of vraag de beheerder om een account".
- Mislukt inloggen met Google noemt nu **de concrete oorzaak** in beeld (foutcode of HTTP-status)
  in plaats van alleen in het logboek van het toestel, zodat een screenshot genoeg is om te zien
  wat er misging.
- Debug-APK's uit de pijplijn worden voortaan met de echte keystore ondertekend. Daarvoor kregen ze
  bij elke build een ander wegwerpcertificaat, waardoor "Inloggen met Google" in een debugbuild
  nooit kón werken.

## Global Version 0.0.49 (2026-07-31)
### 📚 Meer manieren om te bladeren in Ultrasonic
- De Library-tab heeft er vier tabbladen bij: **Jaren**, **Festivals**, **Lineups** en **Ratings**,
  naast Playlists, Genres, Artiesten, Albums en Opgeslagen. Zoeken op lineup kan daarmee weer.
- **In sets-modus tonen de carrousels op de startpagina festivals in plaats van labels.** Livesets
  zijn festivalopnames, dus een platenlabel zegt er weinig over.

### 🛠 Beheer vanaf je telefoon
- Onderin is er een **Beheer**-tab bijgekomen die de beheerpagina's van de webui spiegelt. Voor nu:
  Downloaders (SoundCloud-accounts en YouTube-kanalen), Gebruikers (bekijken, in- en uitschakelen)
  en Verzoeken (goedkeuren, terugdraaien, afwijzen).
- De tab is alleen zichtbaar als je beheerder bent. De server bewaakt die grens sowieso zelf.

## Global Version 0.0.48 (2026-07-31)
### 🐞 Drie dingen op de Ultrasonic-startpagina werkten niet
- **Een artiest aantikken leverde niets op.** De carrousels bevatten ook remixers en gastartiesten
  zonder eigen albums; die hebben nu eenmaal een leeg detailscherm. Er staan nu alleen nog artiesten
  met eigen releases in.
- **Een label aantikken leverde niets op.** De labels kwamen uit een andere tabel dan waarop
  gefilterd wordt, dus zoeken op zo'n naam gaf nul resultaten. Beide gebruiken nu dezelfde bron.
- **Artiestafbeeldingen** worden weer onder de juiste sleutel en op groot formaat opgehaald, zodat
  ze gedeeld worden met de rest van de app in plaats van bij elke weergave opnieuw geladen.

## Global Version 0.0.47 (2026-07-31)
### 📚 Bladeren kan weer: nieuwe Library-tab in Ultrasonic
- In 0.0.46 verdween met de filterknoppen op de startpagina ook de enige ingang naar filter-
  afspeellijsten, genres, de albumlijst en de artiestenlijst. Een filter-afspeellijst maken kon
  daardoor helemaal niet meer. Dat is hersteld.
- Onderin staat nu een **Library**-tab met vijf schuifbare pagina's: Playlists (je filter-
  afspeellijsten, inclusief nieuwe maken), Genres, Artiesten, Opgeslagen afspeellijsten en Albums.
- De onderbalk bestaat nog uit drie knoppen: Home, Library en Favorieten. Zoeken is eruit omdat het
  zoekveld al bovenin de balk zit; je opgeslagen afspeellijsten zitten nu in Library.

### ⭐ De Favorieten-tab toont weer echte favorieten
- Die tab liet sinds 0.0.46 gewoon een kopie van de startpagina zien, omdat hij werkte door een
  filterknop aan te vinken die niet meer bestond.
- Nu staan er je albums en artiesten met een ster, plus alles wat je vier sterren of hoger gaf.
  Tik je op zo'n nummer, dan speelt het meteen.

## Global Version 0.0.46 (2026-07-31)
### 🏠 De Ultrasonic-startpagina is opnieuw opgebouwd
- Bovenaan staat nu een raster met de acht dingen die je het laatst geopend hebt: albums, artiesten,
  labels, gewone afspeellijsten en filter-afspeellijsten door elkaar. Open je iets opnieuw, dan
  schuift het vooraan; dubbel verschijnen doet niets meer.
- Daaronder staan twee schuifrijen: "Recent bijgewerkt" laat zien waarvan de gegevens onlangs zijn
  aangepast, "Recent toegevoegd" laat zien wat er nieuw in de bibliotheek is. Beide tonen artiesten,
  labels en albums.
- Het raster wordt lokaal bewaard, dus het staat er meteen — ook zonder verbinding. Voorheen moest de
  app bij elk bezoek elk item apart bij de server opvragen.
- De filterknoppen bovenaan (Recent, Favorieten, Nieuw, Genres, Afspeellijsten) zijn verdwenen.
  Genres blijven gewoon elders in de app te doorzoeken.
- Nieuwe instelling **"Geschiedenis per modus scheiden"**: bepaalt of losse nummers en livesets een
  eigen lijstje recent geopende items houden. Staat standaard aan.

## Global Version 0.0.45 (2026-07-30)
### 🏷️ Labels zijn nu een eigen manier om je bibliotheek te doorzoeken
- Er is een Label-tab bijgekomen, naast artiesten en genres. Je vindt hem in de zijbalk en op het
  dashboard.
- De zoekbalk zoekt voortaan ook op labels, en labeltreffers verschijnen gewoon tussen je
  zoekresultaten.
- De mobiele apps kunnen dezelfde labelgegevens opvragen, dus dit blijft niet beperkt tot de webUI.

### 📱 Ultrasonic stuurt voortaan een crashrapport na een crash tijdens achtergrondafspelen
- Crashte de app terwijl hij op de achtergrond muziek speelde, dan was er tot nu toe niets terug te
  vinden — de app was simpelweg weg. Dat maakte zulke crashes vrijwel niet te onderzoeken.
- De app houdt nu doorlopend een klein logboek bij en onthoudt of hij netjes is afgesloten. Wordt hij
  door het systeem stilletjes afgeschoten, dan merkt hij dat bij de volgende start en stuurt hij het
  logboek plus de foutmelding als één rapport door.

### 🧭 Eenvoudiger navigatie in de Ultrasonic-app
- Het uitschuifmenu aan de zijkant is verdwenen. Alles wat erin stond zit nu in het menu rechtsboven
  in de balk.
- Onderin staat nu een Favorieten-tab. Downloads is daar weggehaald.
- Bladwijzers zijn voortaan bereikbaar vanaf het Afspeellijsten-scherm.

### 🔧 Testpijplijn liet releases ten onrechte falen
- Draaiden er twee pijplijnen tegelijk, dan sloopten hun browsertests elkaar omdat ze dezelfde
  netwerkpoort claimden. Dat liet werk stranden dat inhoudelijk prima in orde was, waaronder de
  labelfunctie en de crashrapportage hierboven.
- Elke testrun kiest nu zijn eigen vrije poort, dus gelijktijdige pijplijnen storen elkaar niet meer.

## Global Version 0.0.44 (2026-07-30)
### 🔧 Officiële Ultrasonic-release werd soms ongemerkt overgeslagen in het releaseproces
- Een release-branch die geen bestanden binnen de Ultrasonic-app zelf wijzigde, sloeg de officiële,
  ondertekende Ultrasonic-build+upload stilzwijgend over — terwijl een release altijd de officiële
  build hoort te bouwen en uit te rollen.
- Dit is nu gecorrigeerd: elke release bouwt en publiceert voortaan altijd de officiële Ultrasonic-app.
  Het optioneel, handmatig bouwen van een test(debug)-versie vanuit een merge request blijft
  ongewijzigd mogelijk.

## Global Version 0.0.43 (2026-07-30)
### 🔓 Inloggen in de Ultrasonic-app kan nu nooit meer helemaal vastlopen
- Als inloggen (met Google of met gebruikersnaam/wachtwoord) niet lukte, kon je eerder nergens
  anders heen: het inlogscherm liet zich niet sluiten zonder geslaagde login.
- Het inlogscherm is nu een volledig scherm geworden, laat onderin meteen zien of de server
  bereikbaar is, en heeft nu een klein "overslaan"-knopje rechtsboven waarmee je (na een
  bevestiging) verder kunt in een beperkte offline modus - met eerder gedownloade muziek. De
  volgende keer dat je de app opent, wordt gewoon weer gevraagd om in te loggen.
- Zit je in offline modus, dan zie je dat nu altijd duidelijk bovenin de app, met een knop om
  direct weer in te loggen.
- We hebben ook uitgezocht waarom inloggen met Google recent weer misging: in de code zelf is geen
  fout gevonden (alles wat eerder al gerepareerd was, werkt nog steeds correct) - de oorzaak lijkt
  buiten de app te liggen (bijvoorbeeld bij Google zelf). De app legt bij een volgende mislukking nu
  wel veel specifiekere details vast, zodat dit sneller te achterhalen is.

### ⭐ Sterren-rating was onzichtbaar op Android
- Op het "nu afspelen"-scherm van de Ultrasonic-app zat de 5-sterren beoordeling er wel, maar zat
  hij verstopt achter de albumhoes - je kon er dus niet bij.
- De albumhoes en de sterren streden om dezelfde plek op het scherm; de albumhoes won altijd. Dat
  is nu omgedraaid, dus de sterren zijn weer gewoon zichtbaar en aan te tikken.
- Ook in de webspeler (mobiel) stond de sterren-rating er nog helemaal niet bij; die is nu ook
  toegevoegd naast titel/artiest.

## Global Version 0.0.42 (2026-07-30)
### 🔁 Vorige fix (0.0.41) werd niet daadwerkelijk uitgerold naar productie
- Door een race condition in het releaseproces zelf werd de vorige versie (met de fix voor zwarte
  artiestenfoto's) wel samengevoegd en getagd, maar niet daadwerkelijk naar productie gedeployed.
- Geen functionele wijziging in deze versie — dit rolt puur de al samengevoegde fix opnieuw uit.

## Global Version 0.0.41 (2026-07-30)
### 🖼️ Artiestenfoto's waren zwart
- De grote profielfoto op een artiestenpagina, en foto's van gerelateerde artiesten, toonden een
  zwart vlak in plaats van de echte foto — terwijl de foto's zelf wel gewoon aanwezig en op te
  vragen waren.
- Oorzaak: een adres-verwerkingsfout in de server, waardoor het verzoek om de foto op te halen
  intern naar een verkeerd samengesteld adres ging en nooit aankwam.
- Dit is nu gerepareerd; artiestenfoto's die eerder zwart waren, laden nu weer gewoon.

## Global Version 0.0.40 (2026-07-30)
### ⭐ Favorite genres are now saved to your account
- Genres you mark as favorite in the web player used to only be remembered in your browser, so they
  were gone as soon as you used a different browser or device, or cleared your browser data.
- Your favorite genres are now saved to your account, and loaded automatically as soon as you log in
  to the web interface — on any device.
- Already had favorite genres set before this change? Those are automatically carried over to your
  account the next time you log in, so nothing gets lost.

### 📶 Ultrasonic: duidelijkere foutmelding bij inloggen, plus een verborgen bug gevonden
- Bij een mislukte login in de Ultrasonic-app kreeg je altijd dezelfde vage "netwerkfout"-melding,
  ongeacht of de server écht onbereikbaar was of dat er iets anders mis ging. De app laat nu apart
  zien of de server niet bereikbaar was, of dat het inloggen zelf niet lukte.
- Daarnaast gevonden en gefixt: als de instelling "Automatisch schakelen tussen online/offline" nog
  aan stond (de standaardinstelling van vóór versie 0.0.34), kon de allereerste login-controle in
  de welkomstpop-up stilletjes "geslaagd" melden zonder ooit echt contact met de server te maken.
- App-versie opgehoogd naar 6.5.12 (242).

## Global Version 0.0.39 (2026-07-29)
### 🛠️ Kleine interne verbetering aan het releaseproces
- Een van de automatische opruimstappen na een release faalde af en toe met een technische
  foutmelding, terwijl er in werkelijkheid niets mis was — GitLab had alleen nog even tijd nodig
  om te controleren of de wijziging kon worden samengevoegd.
- Het script wacht nu even en probeert het opnieuw voordat het opgeeft, zodat deze stap
  betrouwbaar slaagt. Geen zichtbare wijziging voor gebruikers.

## Global Version 0.0.38 (2026-07-29)
### 🔁 De vorige fix werd per ongeluk teruggedraaid door een oude, vergeten release
- Na het uitrollen van de vorige fix (versie 0.0.37) stond er even later toch weer de oude,
  kapotte versie op de server, alsof de fix niet had gewerkt.
- Oorzaak: er stond nog een héél oude, al lang niet meer gebruikte tussenversie klaar op de
  server om verwerkt te worden, en die kwam toevallig precies ná de nieuwe fix aan de beurt,
  waardoor hij de oude code er per ongeluk weer overheen zette.
- Alle van dat soort oude, al verwerkte tussenversies zijn nu opgeruimd, en het proces zorgt er
  vanaf nu automatisch voor dat zo'n tussenversie meteen wordt opgeruimd zodra hij is verwerkt,
  zodat dit niet meer kan gebeuren.
- Er is geen zichtbare functionele wijziging in de app zelf in deze versie — dit is puur het
  opnieuw correct uitrollen van de vorige fix, plus deze structurele bescherming.

## Global Version 0.0.37 (2026-07-29)
### 🛠️ Twee achtergrondtools op de server crashten steeds bij het opstarten
- Bij een controle van de productieomgeving bleken de `genre-processor`- en
  `muma-soundcloud-fetcher`-containers steeds direct af te breken met een foutmelding, terwijl al
  het andere (afspelen, downloaden, importeren, taggen) gewoon goed draaide.
- Oorzaak: een eerdere opschoning van de code had een instellingenbestand verplaatst/hernoemd, maar
  deze twee losstaande hulpscripts waren daarbij per ongeluk niet meegenomen, waardoor ze naar een
  bestand verwezen dat niet meer bestond.
- Beide scripts zijn hersteld zodat ze weer normaal opstarten; er is ook een automatische test
  toegevoegd zodat een soortgelijke fout voortaan meteen bij het bouwen wordt opgemerkt in plaats
  van pas op de server.

## Global Version 0.0.36 (2026-07-29)
### 🖥️ Beheer: Overzicht-tabblad crashte
- Het "Overview"-tabblad in het beheerpaneel gaf een foutmelding zodra er meerdere recente
  activiteiten waren om te tonen, in plaats van gewoon de lijst te laten zien.
- Dit is nu verholpen; het tabblad laadt weer gewoon.

## Global Version 0.0.34 (2026-07-29)
### 🎨 Ultrasonic-app: inlogschermen in nieuwe stijl
- Het welkomstscherm, het scherm om een server te bewerken, en het scherm voor toegang aanvragen
  zien er nu hetzelfde uit als de webversie: afgeronde invulvelden, een echte "Inloggen met
  Google"-knop met het Google-logo, en duidelijke gekleurde meldingen bij een openstaande,
  afgewezen of goedgekeurde toegangsaanvraag.
- De app schakelt niet langer automatisch over naar offline-modus; dit kan nog steeds handmatig
  aangezet worden in de instellingen.
- De app-versie is opgehoogd naar 6.5.11 (241).

## Global Version 0.0.33 (2026-07-29)
### 📱 Google Sign-In: choosing an account led back to the login screen
- After choosing an account in the Google account picker, you ended up back on the login screen,
  which could only be left by manually entering a username and password anyway — with no error
  message at all.
- Cause: the app didn't recognize the account data returned by Android, due to a subtle bug in how
  that data is read. This silently aborted the Google sign-in right after you picked an account,
  before the server was even contacted.
- This has now been fixed, and an unexpected error now also shows a clear error message instead of
  nothing.
- App version bumped to 6.5.10 (240).

## Global Version 0.0.32 (2026-07-29)
### 🖼️ Artist photos in the web player
- In the web interface, the bottom playback bar only showed the album art and the artist name(s)
  as text — no photo of the artist itself anywhere, even though that already worked elsewhere in
  the app (artist page, dashboard, search results).
- The playback bar (both mobile and desktop) now also shows a small round artist photo next to the
  name, via the same existing integration with the manager that fetches and caches the photos.

## Global Version 0.0.30 (2026-07-29)
### 📱 Google Sign-In on the welcome screen kept the dialog stuck open
- After choosing a Google account on the very first welcome screen, the dialog didn't close and
  the app kept asking you to log in, even though the sign-in itself had actually already succeeded.
- Cause: there was an extra connectivity check behind the Google sign-in that had nothing to do
  with the Google sign-in itself, and that sometimes failed for unrelated reasons — causing a
  successful Google sign-in to be rejected anyway.
- This unnecessary check has been removed; the welcome screen now closes immediately after a
  successful Google sign-in, exactly as it already worked on the existing-server login screen and
  in the web version.
- App version bumped to 6.5.9 (239).

## Global Version 0.0.29 (2026-07-29)
### 📱 Google Sign-In still didn't work on a real device
- Even with a correctly configured Google sign-in key (`GOOGLE_WEB_CLIENT_ID`) and a real
  Google account on the device, "Sign in with Google" still showed "No Google accounts found on
  this device."
- The cause was twofold: the app used a sign-in option that only reliably works for accounts that
  had already authorized the app before (now fixed), and Google also requires a separate
  registration of the app itself (package name + signing key) in the Google Cloud project, in
  addition to the existing sign-in key.
- ⚠️ Note: the code fix alone isn't enough — a one-time manual step is also needed in Google Cloud
  Console (registering two Android OAuth clients, one for the official build and one for debug
  builds) before Google Sign-In actually works. See
  `docs/bug-reports/011-google-signin-no-credential-real-device.md` for the exact steps.
- App version bumped to 6.5.8 (238).

## Global Version 0.0.28 (2026-07-29)
### 📱 "No Google account found" instead of a confusing network error
- When testing in a simulator without a Google account, the "Sign in with Google" button always
  showed the same network error as a real server outage, making it look like the server was
  unreachable.
- The app now specifically recognizes the case where there's no Google account on the device, and
  shows the clear message "No Google accounts found on this device." instead of the network error.
  Cancelling the Google sign-in screen is now also just handled silently (no more error message).
- The app now also logs a clear warning if the Google sign-in key (`GOOGLE_WEB_CLIENT_ID`) isn't
  correctly configured in the build, so a misconfiguration is now visible directly in the logs
  instead of only showing up as a failed sign-in attempt - see
  `docs/bug-reports/010-google-signin-no-account-generic-error.md`.
- ⚠️ Note: if there's still no Google account on the test device/simulator, or
  `GOOGLE_WEB_CLIENT_ID` isn't configured, signing in with Google itself remains impossible —
  those are environment/device settings outside the scope of this code fix.
- App version bumped to 6.5.7 (237).

## Global Version 0.0.27 (2026-07-29)
### 📱 "Sign in with Google" on the very first login screen gave a network error
- The Google sign-in button on the very first welcome screen of a new install always showed
  "A network error occurred. Check the server address and try again later.", while the same
  button further into the app (after setting up a server) worked fine.
- Cause: on that very first screen there was no server configured yet, causing the request to
  accidentally be sent to a local test address instead of the real server.
- This screen now always sends the Google sign-in request to the correct, fixed production
  server, so signing in with Google works right away the very first time.
- App version bumped to 6.5.6 (236).

## Global Version 0.0.25 (2026-07-28)
### 📱 Default server changed + Google button now shown on the very first sign-in
- The fixed server in the phone app is now `music.example.com`; the separate "alpha" test
  server (which no longer existed on the production environment anyway) has been removed from the
  app.
- "Sign in with Google" is now also shown on the very first login screen you see on a new install,
  instead of only further into the app - exactly as requested, so you can make that choice right
  away.
- App version bumped to 6.5.5 (235).

## Global Version 0.0.23 (2026-07-28)
### 📱 Signing in with Google now actually works in the phone app
A button to sign in with Google already existed in the phone app, but two small bugs meant it
never really worked properly.
- After signing in with Google on your phone, your music (playback, library) now actually works,
  exactly like on the website - previously this incorrectly stayed on "not logged in".
- The build pipeline now automatically passes the correct Google setting to the phone app, so this
  also works in the versions built automatically from now on.
- App version bumped to 6.5.4 (234).

## Global Version 0.0.21 (2026-07-28)
### 📱 Official Ultrasonic release APK is now fully automatically built and published
The automation to build a signed Ultrasonic APK and upload it to apk-hoster already existed in
the code, but had never actually produced a release: the original signing key could no longer be
found anywhere.
- Generated a brand-new signing key and securely configured it, together with the apk-hoster
  credentials, as CI/CD variables (never in the code).
- `ultrasonic:build-release` now runs automatically on every release pipeline and immediately
  publishes the signed APK online at https://apk.example.com.
- Bugfix: the key was passed to the build script in the wrong way (raw bytes instead of text),
  which would have always made the build fail; this is now fixed.
- Bugfix: a reference to a folder on Teun's laptop had accidentally ended up in the source code,
  causing the publish step to always fail in every other environment (including CI); removed.
- All old, manually uploaded APKs have been removed from apk-hoster (clean slate), and the app
  version has been bumped to 6.5.3 (233) as the first official, automatically built release.
- ⚠️ Note: because of the new key, anyone who had installed an earlier, manually signed version
  (e.g. v6.5.2-214) needs to uninstall and reinstall the app once.

## Global Version 0.0.20 (2026-07-28)
### 📦 Importer kept repeating duplicate-folder errors forever
While further digging through production logs, it turned out the import service kept repeating
the same ~15 misleading "disk space/filesystem" error messages on every check, for releases that
had actually already been imported successfully long ago.
- **Cause**: specific handling for "this release was already imported before" already existed,
  but it wasn't invoked for this particular type of conflict, so the folder was never cleaned up
  and kept reappearing as an error in the logs on every pass.
- **Fix**: this type of conflict is now handled the same way as the existing case — the duplicate
  folder is now automatically cleaned up so it doesn't keep coming back as an error. A genuine
  disk space problem is still reported as an error as before — see
  `docs/bug-reports/008-importer-duplicate-folder-stuck-forever.md`.

## Global Version 0.0.19 (2026-07-28)
### 📡 Telegram background service crashed on startup (session-file version mismatch)
While digging through production logs, it turned out the Telegram background service was crashing
while loading its session file, instead of just connecting.
- **Cause**: when building this particular service, alongside the pinned version of the library
  used, a second, unpinned install was accidentally also run. This meant every new build could
  install a different version of that library, and that library stores the session file in a
  format that can differ between versions — so an older build could no longer read the file
  produced by a newer build.
- **Fix**: the pinned library version has been updated to a version compatible with the existing
  session file, and the redundant, unpinned install has been removed so every build now always
  uses exactly the same, tested version — see
  `docs/bug-reports/007-telegram-session-schema-mismatch.md`.
- **Extra discovery**: after a fully successful rollout, this fix turned out to still not be live
  in production. It turned out the automatic deploy so far only refreshed the two main components
  and never automatically rebuilt and published any of the other background services (including
  Telegram). This has now been fixed: all these components are now automatically included in
  every release from now on.

## Global Version 0.0.18 (2026-07-28)
### 🖼️ Artist Images tab was permanently stuck at "0 / 0 artists"
The "Artist Images" admin screen always showed "0 / 0 artists", search never returned results, and
the RESCAN button showed no progress — even though the artist and image data itself was actually
correctly stored in the database.
- **Cause**: a piece of middleware code in the player intercepted every request starting with
  `/api/artists/`, before it could even reach the normal forwarding layer to `music-manager`. That
  middleware only handled two specific cases (an image request, or a bare numeric artist ID for
  the player itself) — all other calls such as statistics, search, and scan progress were
  therefore always rejected with an error before they reached the admin tool.
- **Fix**: the middleware now only intercepts those two specific cases; all other artist-related
  calls are forwarded normally again — see
  `docs/bug-reports/006-artist-images-tab-zero-stats.md`.

## Global Version 0.0.17 (2026-07-28)
### 🚨 Login was broken in production (`no such column: u.password_salt`)
Every login attempt — with username/password and via Google — crashed with a database error.
- **Cause**: a background task in `music-manager` accidentally deleted the player's real,
  permanent user table directly from the live database (based on an incorrect assumption that,
  like session data, that table only existed temporarily in memory). This happened right at the
  moment the player itself was also initializing its own database, causing an incomplete fallback
  in the player to recreate the table without several required columns.
- **Fix**: the destructive cleanup in `music-manager` has been completely removed (it no longer
  served any functional purpose anyway), and the fallback in the player has been updated so it can
  never again create an incomplete table schema.
- **Production**: an immediate manual recovery was applied (missing columns restored, player
  restarted) as soon as the problem was confirmed, well before this release was rolled out — see
  `docs/bug-reports/005-lms-user-table-corruption.md`.

## Global Version 0.0.16 (2026-07-28)
### 🐛 Artist images work again in the admin screen and the player
- **Admin screen (`bug 004`)**: artist image requests were missing authentication and therefore
  always got a `401 Unauthorized`; the API key is now passed as an `apiKey` query parameter.
- **Production sync path (`bug 004`)**: the path `music-manager` uses to access the `lms`/
  `alpha-lms` stacks' own database (for users/playlists and artist images) pointed to a folder
  that never existed in production; this now defaults to the actual data folders of the
  `lms`/`alpha-lms` stacks.

## Global Version 0.0.15 (2026-07-28)
### 🔗 "Show all" buttons on the homepage now link to the correct tabs and views
- **Release Radar**: the "Show all" button now opens the Release Radar tab directly.
- **Songs**: the "Show all" button switches the view mode to songs and opens the songs tab.
- **Sets**: the "Show all" button switches the view mode to sets and opens the sets tab.

## Global Version 0.0.14 (2026-07-28)
### 🎨 "MuMa Admin" button removed from profile menu
- **Profile menu (`ProfileButton.svelte`)**: the "MuMa Admin" button in the profile dropdown menu
  has been removed, since system administration is already fully accessible via the Player/Admin
  switch in the main sidebar.

## Global Version 0.0.13 (2026-07-28)
### 🐛 Fixed popular-genres semicolon delimiter & missing artist images
- **Popular genres (`bug 002`)**: top-genre statistics (`stats.py`) now splits compound genre
  strings separated by semicolons (`;` / `,`), trims whitespace, and counts individual subgenres
  correctly.
- **Artist images (`bug 003`)**: background and manual tasks for missing artist images
  (`run_fetch_missing` in `artist_images.py`) now process all artists where
  `primary_image_id IS NULL`, regardless of their previous `image_status`.

## Global Version 0.0.12 (2026-07-28)
### 🐛 Structured bug reports & fetch-progress fix
- **Structured bug reports**: introduced a 2-step workflow under
  `docs/bug-reports/00#-<title>.md` with fields for status, problem, cause, and solution
  (`AGENTS.md` updated).
- **Artist fetch-progress fix**: prevents polling for fetch progress from incorrectly showing an
  error after completion.

## Global Version 0.0.9 (2026-07-28)
### 🎨 Minor UI cleanup in sidebar and profile menu
- **Legacy UI button removed**: the "Old UI (Legacy)" button in the profile menu has been
  permanently removed.
- **Integrated library**: all library sections (playlists, artists, albums, genres, history,
  favorites) are now directly in the main sidebar with clear icons; the "YOUR LIBRARY" heading has
  been dropped.
- **Redundant System Admin item removed**: the "System Admin" menu item in the sidebar has been
  removed since the Player/Admin switch in the header already covers this.

## Global Version 0.0.8 (2026-07-28)
### 🚪 Logging out after Google Auth left session data behind ("User")
When you were logged in via Google Auth and logged out, the webapp kept holding on to session data
(`mumaSessionActive`, `mumaApiKey`, `mumaRefreshToken`, `userPermissions`, `mumaUser`) and
localStorage values. This left you stuck as 'User' with no music permissions.
- **Fix**: the logout function (`handleLogout` in `ProfileButton.svelte`) now thoroughly clears
  all session stores and associated localStorage items (`muma_api_key`, `muma_refresh_token`,
  `muma_session_active`), so logging out now actually cleans up the entire session.

## Global Version 0.0.7 (2026-07-28)
### 🔐 Dedicated login page instead of a login modal
The login modal has been decoupled from the main view and turned into a dedicated, full-fledged
login page.
- **Dedicated login page**: when you're not logged in, the webapp now always shows a dedicated
  full-screen login page (`LoginPage.svelte`) instead of an overlay on top of the app.
- **Automatic redirect**: if you visit the app without a valid session, you're now automatically
  redirected to `/login`.

## Global Version 0.0.6 (2026-07-27)
### 🎵 Signing in with Google showed you as "User" with no music
Signing in with Google worked, and your permissions/role were correct, but you didn't see your
name and no songs, albums, or genres appeared at all — `getGenres` even returned an error about a
missing parameter.
- **Cause**: after a Google login, your username/password were never stored anywhere in the
  webapp — and the webapp uses exactly those two fields for every call to the music library (and
  to show your name), because a Google login never learns your real password.
- **Fix**: on a successful Google login, the webapp now uses a special, already-existing key from
  your account as a substitute password for these calls. You now see your own username again, and
  your music library (albums, genres, playback) works again — exactly as with username/password
  login.

## Global Version 0.0.5 (2026-07-27)
### 🔐 The Google sign-in button had disappeared again — and the server no longer actually verified who was signing in
After the previous rollout, only username/password showed on the login screen; the Google button
was gone. Cause: the setting containing the Google Client ID wasn't present anywhere in the
configuration automatically used during build and deploy — it only existed (manually) on the
server itself, and was overwritten with an empty value on the first automatic redeploy.
- **Fix**: the Google Client ID is now part of the central configuration used on every automatic
  build and deploy, so the button reappears and keeps appearing on subsequent releases.
- **Extra security**: as long as this setting was missing, the server silently accepted a Google
  login from *any* Google app, not just ours. Signing in with Google now gives a clear error if
  this setting is ever missing again, instead of letting this happen unnoticed.
- Signing in with username/password and signing in with Google already use the same underlying
  account once linked (see 0.0.3) — this fix only ensures both sign-in methods are actually
  available again.
- **Bonus fix**: if the web interface forwarded an error message from the admin server (e.g.
  "wrong password" or "song not found"), that error message was replaced along the way with a
  vague generic failure message. The real error message now comes through correctly.
- **To prevent recurrence**: an extra, mandatory check has been added that automatically verifies,
  on every deploy from a release branch, that this Google setting is actually present, and blocks
  the deploy immediately and clearly if it isn't — instead of the button silently disappearing on
  the next build.

## Global Version 0.0.4 (2026-07-27)
### 🔐 A successful Google login still showed an error message
A valid, linked Google login sometimes came back from the server cleanly with status `200 OK`,
but the webapp still showed "Could not connect to the Google login API" and you stayed on the
login screen.
- **Fix**: `/api/auth/google` (and `/api/auth/login`, `/api/auth/refresh`) now always return user
  data nested under a `user` field, as the webapp already expected everywhere and as
  `/api/auth/verify` already did — instead of placing it loose at the top level of the response.

### 🔐 Google Sign-In popup sometimes blocked itself
Some browsers showed the console message "Cross-Origin-Opener-Policy policy would block the
window.postMessage call." while signing in with Google — this sometimes prevented the ID token
from correctly making it back to the webapp.
- **Fix**: the reverse proxy for the webapp now explicitly sends
  `Cross-Origin-Opener-Policy: same-origin-allow-popups`, so the Google sign-in popup can always
  keep communicating with the page.

## Global Version 0.0.3 (2026-07-26)
### 🔐 Google Sign-In now really works, end-to-end
The "Sign in with Google" flow already existed, but the button didn't appear in production (the
Client ID was never built in), and once that was fixed, signing in still gave `401 Unauthorized`
and admins were missing their admin buttons. On top of that, you could no longer merge two
accounts belonging to the same person.
- **Google button now really appears**: every place that builds the `lms` image (locally, the LMS
  build script, and CI) now passes the Client ID as a build arg, so it actually ends up in the
  built bundle. Documented in a new "Google Sign-In setup" section in `docs/deployment.md`.
- **Google/access-request logins are no longer blocked**: the proxy between the webapp and the
  admin backend now actually lets a new Google login through instead of blocking it before it's
  even checked.
- **Your own login is no longer swapped for a generic one**: every request through that proxy now
  retains your own identity, so the backend correctly shows your real role and permissions.
- **Admin buttons are back**: the Admin tab now correctly recognizes admins again (via Subsonic or
  Google) and shows the user-management buttons that had previously been hidden.
- **Merging accounts**: duplicate accounts (e.g. from a Google access request for someone who
  already had a local account) can now be merged into a single account; an access request can also
  now be linked directly to an existing account instead of always creating a new one.
- **Deleting users is more robust**: failed deletions now show a clear error message, and the last
  remaining admin can no longer be accidentally deleted.

## Global Version 0.0.2 (2026-07-26)
### 🛠 Fix: Production Now Actually Deploys What You Released
Right after `0.0.1`, production kept looking like it was running old code even after a successful
deploy. The cause: the release pipeline never built and published fresh Docker images — it only
told the server to "pull", which just re-fetched whatever image had last been pushed by hand.
- **Automated image build + publish**: every `release/*` branch now automatically builds and
  publishes fresh `music-manager` and `lms` images to Docker Hub as part of the pipeline, before
  production ever gets told to pull. No more manual `docker push` step, and no more risk of
  deploying stale code.
- **Deploy now depends on a successful build**: if the image build/publish step fails or is
  misconfigured, the production deploy step no longer runs at all — it can never silently deploy
  an old image again.

## Global Version 0.0.1 (2026-07-26)
### 🚀 A New Beginning: Single Monorepo & Official Release Process
This release intentionally restarts the overarching version number at `0.0.1` — it is the first
**official** release cut under the new `develop` → `release/*` → `master` branching and deployment
model, and marks the point where this project became one single, unified monorepo.
- **One Repository, One History**: `music-management-server` (LMS) and the `ultrasonic` Android app were
  merged directly into this repository (full commit history preserved via `git subtree`), alongside the
  `frontend`. There are no more submodules or separate remotes for these projects — everything that
  touches the ecosystem (backend, player/manager frontend, mobile client) is now developed and released
  from one place.
- **Ultrasonic Fully Coupled**: the Android client connects to `music-management-server`'s Subsonic API
  through the same `music.example.com` reverse proxy used by the web player/manager, with settings
  backup/sync and star-rating/scrobble feedback already wired end-to-end to Music Manager.
- **Official, Automated Production Deploys**: production is now deployed exclusively from `release/*`
  branches, using dedicated CI-managed SSH credentials — no manual steps or handmade `.env` copying are
  required, and the deploy is idempotent (safe to re-run, and safe to redeploy from scratch without
  losing the database).
- **Release Governance**: a release can no longer reach production without an updated `CHANGELOG.md`,
  these release notes, and a bumped `VERSION` — enforced automatically by a new pipeline check. Every
  release that reaches `master` is now also automatically tagged (`release-vX.Y.Z`), giving a permanent,
  unambiguous record of what has actually shipped.
- **Automated Ultrasonic Distribution**: debug builds are now uploaded to `apk-hoster` automatically on
  every `develop` merge (for day-to-day testing on your own device), with official signed builds
  reserved for `release/*` branches going forward.

See [docs/release-management.md](docs/release-management.md) for the full branching/release model.

## Global Version 2.5.0 (2026-07-11)
### 🚀 Structural Modernization & Path Migration
- **Major Path Migration**: The entire system has been migrated from `/music` to `/mnt/music`. This ensures consistency with host mounts and simplifies path resolution across all services.
- **API Architecture Consolidation**: We've removed the redundant `common/api` layer. All workers now push their status and progress directly to the `music-manager` hub, resulting in a cleaner, more robust architecture.
- **Streamlined Project Layout**: The confusing `music-management/` intermediate folder is gone. By moving `services/` to the root, we've simplified the project structure, `PYTHONPATH` management, and Docker builds.
- **Enhanced Test Reliability**: A new unified testing configuration (`conftest.py`) allows the full test suite to run in isolated environments by automatically mocking heavy system dependencies.
- **Worker Hub Integration**: YouTube and SoundCloud downloaders are now fully integrated with the centralized Job Manager, providing real-time progress bars in the dashboard.
- **Codebase Optimization**: Removed over 80 redundant proxy methods and standardized all internal API routing under the `/api` prefix for better maintainability.

## Global Version 2.3.0 (2026-07-05)
### 🚀 The Cloud Sync & Security Update
- **MuMa Cloud Sync**: Introduced a new server-side backup system for application settings. Clients like Ultrasonic can now securely store and restore their full configuration in the MuMa database.
- **Unified Authentication**: Streamlined the API authentication flow. The API key returned during login is now universally valid for all user-specific actions, including settings management and playlist control.
- **ListenBrainz Reliability**: Overhauled the scrobble import engine with robust pagination support, allowing imports of up to 10,000 tracks per session with improved matching logic.
- **Library Intelligence**: Restored and expanded library statistics, providing deep insights into genre distribution, match rates, and artist coverage across both stable and alpha instances.
- **UI Hardening**: Removed sensitive API keys from the frontend interface in favor of secure session-based tokens, improving overall security for administrators.
- **Multi-Instance Enrichment**: Enhanced the artist image fetcher to automatically synchronize high-quality artwork across all connected LMS databases.

## Global Version 2.2.0 (2026-07-05)
### 🚀 Music Manager Core Consolidation
- **Service Consolidation**: Merged six microservices (`user-service`, `scrobble-service`, `rating-system`, `stats-service`, `management-api`, and `artist-image-fetcher`) into a single, high-performance FastAPI service: **Music Manager**.
- **Performance Optimization**: Implemented database connection pooling and asynchronous thread offloading to eliminate bottlenecks and connection errors.
- **Enhanced Artist Enrichment**: Fixed artist image synchronization to support multiple LMS instances (Stable & Alpha) with proper version tracking.
- **Improved UI/UX**: Updated the Control Center dashboard with better session handling and integrated all management features into a unified interface.
- **Infrastructure Simplification**: Streamlined `docker-compose.yml` and deployment scripts, reducing resource overhead and build complexity.
- **LMS Integration Fixes**: Updated the entire ecosystem to use a unified API port (8000) and optimized internal Docker networking for more reliable communication.
- **Side Scroll Wheel Support**: Added horizontal scroll (deltaX) support for volume control in the LMS music player, optimized for Logitech MX Master 3.

## Global Version 2.1.31 (2026-07-05)
### 🛡️ Health & Activity Dashboard
- **System Monitoring**: The Control Center now has a dedicated "Health & Activity" tab for a complete overview of the system.
- **Container Health**: Real-time status overview of all Docker containers (Running/Stopped).
- **In-App Logs**: View the last 200 lines of logs from each container directly without using SSH.
- **Activity Stream**: Instantly see which tracks have recently been added by the downloaders or processed by the tagger.

## Global Version 2.1.30 (2026-07-05)
### 🔑 LMS Subsonic API Key Integration
- **Configurable Subsonic Key**: LMS now supports the `LMS_SUBSONIC_API_KEY` environment variable. This allows the Subsonic API key to be set directly without manual database changes, ensuring a seamless connection with apps like Ultrasonic.

## Global Version 2.1.29 (2026-07-05)
### 🔐 Centralized Auth & Network Hardening
- **User Service Identity Provider**: Repurposed the User Service to act as a central auth authority. It now exposes an `/auth/verify` endpoint that validates tokens for other services.
- **Enhanced Verification**: Services can now offload API key verification to the User Service, which supports both global and user-specific keys from the database.
- **Port Minimization**: Removed public port exposures for internal microservices (`Rating`, `Scrobble`, `User`). They are now only accessible within the secure Docker network.
- **Internal DNS Integration**: Optimized service communication by utilizing Docker's internal networking, improving both security and performance.

## Global Version 2.1.28 (2026-07-04)
### 🛠 Infrastructure Fix
- **Configuration Persistence**: Ensured that the newly introduced `LMS_SUBSONIC_API_KEY` is correctly propagated through the main Docker Compose configuration, finalizing the fix for LMS user synchronization.

## Global Version 2.1.27 (2026-07-04)
### 🔒 Security & Multi-Service Authentication
- **LMS API Key Separation**: Resolved a key mismatch where LMS required an older UUID token while muma services were updated to a new key. Introduced `LMS_SUBSONIC_API_KEY` to handle this.
- **Improved Diagnostics**: The User Service now provides detailed feedback on Subsonic API responses, helping to identify "Unknown API method" errors on older LMS versions.

## Global Version 2.1.26 (2026-07-04)
### 🐛 Bugfixes & LMS Connectivity
- **Subsonic API Auth**: Fixed an authentication failure when syncing users with LMS. The system now correctly passes the `apiKey` as a query parameter, satisfying LMS security requirements.

## Global Version 2.1.25 (2026-07-04)
### 🔒 Security & LMS Integration
- **API Key Alignment**: Fixed a configuration issue where microservices were receiving inconsistent API keys. Now, `user-service`, `rating-system`, and `scrobble-service` correctly use their dedicated keys.
- **Verified LMS Sync**: Confirmed that the User Service properly includes the `X-API-Key` header when communicating with LMS/Subsonic endpoints.

## Global Version 2.1.24 (2026-07-04)
### 📺 YouTube & Cookie Integration
- **YouTube Control**: A new dedicated "YouTube Accounts" tab in the Control Center allows for easy management of channels to be scanned.
- **Shared Firefox Cookies**: Integrated support for using cookies from a running Firefox container. This enables the downloaders to access restricted content and reduces the likelihood of being flagged as a bot.
- **Improved UI**: Streamlined the downloader management interfaces, adding delete functionality for both SoundCloud and YouTube accounts.

## Global Version 2.1.23 (2026-07-04)
### 🛠 User Service & Sync Fixes
- **LMS Sync Reliability**: Fixed critical bugs in the LMS user synchronization task, including incorrect variable usage and indentation errors.
- **Multi-Host LMS Support**: Introduced the `LMS_HOSTS` environment variable, allowing the User Service to synchronize from multiple LMS instances simultaneously.
- **Environment Cleanup**: Corrected network configuration typos in the `.env` file to ensure stable connectivity.

## Global Version 2.1.22 (2026-07-04)
### 🔐 System-wide API Security
- **Unified API Authentication**: Implemented a mandatory `X-API-Key` validation across all backend services (`Management API`, `User Service`, `Scrobble Service`, and `Rating System`). This ensures that only authorized interactions from the Control Center are accepted.
- **Improved Token Handling**: The Control Center now includes a dedicated "API Security" section, allowing you to securely set and store your API key in the browser.
- **Service Alignment**: Synchronized the `API_KEY` configuration across all modular components to ensure seamless internal communication and proxying.
- **Infrastructure Hardening**: Integrated the `User Service` into the consolidated `full` Docker Compose configuration for better out-of-the-box deployment.

## Global Version 2.1.20 (2026-07-04)
### 🌐 Production Connectivity Fixes
- **LMS Host Alignment**: Updated default SlimServer/LMS host to `lms.example.com` to match the actual production environment.
- **CORS Policy Update**: Expanded trusted origins to include the correct production IP and new LMS domains, ensuring seamless UI interaction across all endpoints.

## Global Version 2.1.19 (2026-07-04)
### 🔐 Unified Password Management
- **LMS Password Sync**: You can now set user passwords directly from the Muma Control Center. These passwords are automatically hashed and synchronized with your Logitech Media Server instance.
- **Enhanced Security**: Switched to industry-standard Bcrypt hashing for all user accounts, ensuring consistent security across the modular ecosystem.
- **Improved User UI**: The Users dashboard now features a dedicated security section for quick account management.

## Global Version 2.1.18 (2026-07-04)
### 🔄 Advanced LMS Integration
- **Direct Database Sync**: Added the ability to sync users directly from the LMS `lms.db` SQLite database, providing more complete account information than the API.
- **ListenBrainz Token Migration**: Automatically migrates ListenBrainz tokens found in LMS accounts to the Muma User Service.
- **Volume Mounting**: Updated infrastructure to support direct access to LMS data files for seamless background synchronization.
- **Enhanced UI**: Added new synchronization triggers to the Users dashboard to easily maintain parity with LMS.

## Global Version 2.1.17 (2026-07-04)
### 👥 Centralized User Management
- **User Service**: Introduced a dedicated service to manage Muma users and their external account credentials.
- **ListenBrainz Integration**: Users can now securely store their ListenBrainz API tokens.
- **LMS Synchronization**: One-click synchronization of players/users from Logitech Media Server.
- **Enhanced Dashboard**: New dedicated Users tab in the Control Center for streamlined administration.

## Global Version 2.1.16 (2026-07-04)
### 🐛 Scrobble Service Fixes
- **Import Stability**: Fixed a critical crash in the ListenBrainz import background task.
- **API Compliance**: Added proper User-Agent headers to external API calls.
- **Data Integrity**: Ensured ListenBrainz raw data is correctly serialized as JSON before storage.

## Global Version 2.1.15 (2026-07-04)
### 📊 Enhanced Scrobble Monitoring
- **Import Dashboard**: Added a new dedicated tab in the Control Center for the Scrobble Service.
- **Progress Tracking**: You can now monitor ListenBrainz imports in real-time with progress bars and status updates.
- **Import History**: View a log of recent imports, including total tracks found and processed.
- **API Improvements**: Enhanced the Scrobble Service with task tracking and background processing status endpoints.

## Global Version 2.1.14 (2026-07-04)
### 🎧 Introducing Scrobble Service
- **Listening History**: You can now track your listens directly in MuMa.
- **ListenBrainz Import**: Sync your existing history from ListenBrainz with a single click.
- **Unmatched Listens**: If a song isn't in your library yet, it's stored separately so you can match it later once it's imported.
- **Smart Matching**: Automated matching using MusicBrainz IDs with a robust artist/title fallback.

## Global Version 2.1.13 (2026-07-04)
### 🍏 UI Polish & Database Consistency
- **Rating System**: Renamed internal table to `rating_tracks` to align with the module's naming convention.
- **Goodbye Blue**: Fixed remaining browser default focus rings that were still showing up as blue. Everything now glows in Spotify Green.
- **Theme Consistency**: Reinforced the dark theme across all interactive components.

## Global Version 2.1.12 (2026-07-04)
### 🎨 UI Refinement & Debugging
- **Spotify Theme Finalized**: The design system is now formalized in `styleguide.md`, ensuring a consistent Spotify-inspired look across the entire Control Center.
- **Enhanced Debugging**: Added a new `--debug` flag to the build and publish scripts for easier troubleshooting of the deployment pipeline.
- **Visual Polish**: Improved color consistency and interactive states (focus/selection) for a smoother user experience.

## Global Version 2.1.11 (2026-07-04)
### 🚀 System-wide Release Notes
- **Unified Documentation**: You can now view release notes for all sub-programs directly from the Control Center home page.
- **Service Integration**: The Rating System now fully supports the versioning and monitoring API.

## Global Version 2.1.10 (2026-07-04)
### 🛠️ Final Infrastructure Hardening
- **ML Analyzer Fully Resolved**: Integrated `pymysql` and other missing core libraries into the ML Analyzer's specialized environment.
- **Cleaner Logs**: Silenced redundant database warnings in worker services, ensuring clearer and more relevant logs.

---

## Global Version 2.1.9 (2026-07-04)
### 🚀 Final Polish & Service Stability
- **ML Analyzer Active**: Fixed the ML Analyzer configuration to ensure it runs as a persistent service, enabling its version tracking and API features.
- **Telegram Reliability**: Implemented advanced asyncio loop handling for the Telegram worker, resolving persistent "Event loop is closed" errors.
- **Optimized Startup**: Removed unnecessary `yt-dlp` update checks from service startup to ensure containers boot faster.

---

## Global Version 2.1.8 (2026-07-04)
### ⚡ Performance & Reliability
- **Telegram Worker Fix**: Resolved a critical "Event loop is closed" error that caused the Telegram worker to crash repeatedly. It now uses a much more stable asynchronous initialization process.

---

## Global Version 2.1.7 (2026-07-04)
### 🛠️ Final Polishing
- **YouTube Fix**: Resolved a configuration mismatch that caused the YouTube worker to crash on startup.
- **Rating System Integration**: Officially included the new Rating System service in the build and deployment pipeline.

---

## Global Version 2.1.6 (2026-07-04)
### 🔄 Massive Dependency Fix
- **Unified Base Image**: To prevent further "ModuleNotFound" errors, all worker service code is now bundled into the base image. This ensures that any cross-service imports (like the Downloader using the Tagger's logic) work seamlessly in all containers.
- **Dependency Consolidation**: All common Python libraries are now pre-installed in the base image, reducing the chance of runtime failures in specialized workers.

---

## Global Version 2.1.5 (2026-07-04)
### 🐛 Bug Fixes
- **API Stability**: Fixed a crash in worker APIs by ensuring all necessary dependencies like `markdown` and `pydantic` are available in the base image.
- **Improved Logging**: Fixed an error masking bug that made it difficult to diagnose startup failures.
- **Service Integration**: Ensured core music management classes are correctly discoverable by all worker services.

---

## Global Version 2.1.4 (2026-07-04)
### 🛠️ Bug Fixes & Stability
- **Dependency Resolution**: Fixed a critical issue where specialized worker containers were missing core music management logic.
- **Base Image Enhancement**: Moved shared `Song` classes and `mutagen` to the base image for better consistency across workers.
- **Management API Fixes**: Resolved a crash in the Control Center caused by missing `requests` library and properly integrated it into the base image ecosystem.

---

## Global Version 2.1.3 (2026-07-04)
### 🚀 Deployment Optimization
- **Consolidated Deployment**: Merged all deployment logic into a single, unified `scripts/deploy.sh` script.
- **Improved Automation**: Streamlined the `install.sh` workflow to ensure all modular applications are processed correctly in one go.

---

## Global Version 2.1.2 (2026-07-04)
### 🏗️ Modular Architecture
- **Specialized Containers**: Each service now runs in its own lightweight, optimized Docker container.
- **Improved Performance**: Reduced image sizes by excluding unnecessary dependencies and frontend builds from background workers.
- **Module-Specific Documentation**: Introduced separate release notes and changelogs for each module to improve clarity.

---

## Version 2.1.1 (2026-07-04)
### 🏗️ Infrastructure Update
- Unified Docker deployment configuration with the new `scanner_service` name.
- Added a consolidated `docker-compose.full.yml` for easier Portainer integration.

## Version 2.1.0 (2026-07-04)

### 🎨 Artist-Genre Editor
We've introduced a powerful new editor in the Control Center! You can now easily map your favorite artists and labels to specific genres using a modern, Spotify-inspired interface. Search through your library, find the right genre, and set the rules for future imports.

### 🔍 Library Scanner
The new Library Scanner automatically indexes your music collection into the database. It finds your tracks, extracts metadata, and organizes your artists and labels without ever touching your original files.

### 🛠️ Backend Enhancements
- Expanded the Management API with dedicated endpoints for library and rule management.
- Improved database indexing for faster library lookups.

---

## Version 2.0.0 (2026-07-04)

This major release introduces a redesigned database core and significantly enhanced machine learning analysis capabilities.

### Features
- **Advanced Audio Analysis**: The ML analyzer now extracts deeper audio features including MFCC, Zero Crossing Rate, Spectral Rolloff, and Chroma features. This enables more accurate similarity matching and automated tagging.
- **Database Schema v2**: A fully refactored database engine providing significantly improved performance and data consistency for large music collections.

### Improvements
- **Analysis Stability**: Enhanced robustness for high-load analysis jobs, ensuring reliable background processing of large libraries.
- **Metadata Handling**: Improved accuracy in path mapping and configuration storage across the system.
