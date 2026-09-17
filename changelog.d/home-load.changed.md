- **De startpagina laadde seconden en de onderdelen hielden elkaar op.** Release radar, de
  vijf daily mixes en de presets kwamen pas tegelijk in beeld, en elk van de feeds kostte de
  server seconden. Twee oorzaken (`docs/designs/feeds/home-load.md`). Aan de serverkant rekende
  elke feed-aanroep alles opnieuw uit: `GET /api/feeds` loste het luisterprofiel zeven keer op
  (één keer per policy, telkens dezelfde 90 dagen `scrobble_listens`), en de drie
  band-mixes bouwden voor een kaartkleur een volledige feed, tot en met de hele bibliotheek als
  kandidaat wanneer het venster verruimd werd. Eén startpagina was elf profiel-berekeningen.
  Aan de clientkant wachtten songs en sets op de radar (`Promise.all`), de mix-kaarten op alle
  drie de band-feeds én de artiestfoto, en zaten sessiecheck, instellingen en presets in
  dezelfde wachtrij van drie achter een feed-build — de wachtrij was gemaakt voor de LMS-proxy,
  waar deze aanroepen sinds 0.65.1 niet meer langs komen. Nu: het profiel wordt per aanroep één
  keer opgelost; elke feed en de feedlijst worden per luisteraar per dag opgeslagen in
  `feeds_snapshot` (de daily mixes zijn per ontwerp dag-stabiel, de radar wordt elk uur ververst,
  een gewijzigde instelling maakt alles direct oud) en een achtergrondlus `feeds-refresh` houdt
  ze voor iedereen met een luisterbeurt in de laatste dertig dagen alvast warm; een uitsluiting
  wist de snapshots van die luisteraar. `?limit=10` is voortaan de kop van dezelfde ranking als
  de pagina waar de rij naartoe linkt, niet een tweede verdeling over tien plaatsen. De client
  toont elke rij zodra die er is, tekent de mix-kaarten meteen uit de feedlijst met de vaste
  kleuren en vult genretint en artiestfoto later los in, en houdt twee wachtrijen: drie plekken
  voor wat nog via de LMS-proxy loopt, acht voor wat rechtstreeks naar MuMa gaat.
  `X-MuMa-Feed-Source` op een feed-antwoord zegt of het uit de snapshot kwam of live gebouwd is.
- **`verify_api_key` in `routers/users.py` blokkeerde de event loop.** De dependency was
  `async def` en riep de synchrone `verify_token` (een databaseronde) rechtstreeks aan, dus elke
  presets- of instellingen-aanroep hield alle andere verzoeken op tot de sleutelcheck klaar was.
  Nu een gewone `def`, zoals `feeds.verify_api_key` al was; de rbac-, scanner- en
  tagger-wrappers gaan mee.
