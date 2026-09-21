- **De artiestfoto-fetcher draaide een maand zonder sleutels en zette 45.000 artiesten op
  "niet gevonden".** De Spotify client id en secret kwamen alleen ooit mee in de `.env` die het
  image kopieerde; toen die COPY op 2026-07-24 terecht verdween, kreeg de container ze van niets
  meer -- `docker-compose.yml` noemde ze niet. Een provider zonder sleutel antwoordde met een lege
  lijst, precies wat een zoekopdracht zonder treffers ook geeft, en de fetcher schreef
  `image_status = 'failed'`: Sefa, Partyraiser, Dr. Peacock, Warface, alles vanaf 22 augustus
  (11.759 actief, allemaal van juli; 44.972 failed, geen enkele foto sinds). De velden op
  Beheer > Config bestonden al en werden door niemand gelezen, en `data/config.json` stond niet op
  een volume, dus wat je daar invulde overleefde geen deploy. Nu: `credential()` in
  `config_store` (configpagina eerst, omgeving daarna) voor fetcher én tagger-lookup;
  `ProviderUnavailable` voor een ontbrekende of afgewezen sleutel, 429, 5xx of netwerkfout, zodat
  alleen een 200 zonder treffers "niet gevonden" is; een run zonder geconfigureerde provider
  kijkt niets op en schrijft niets; `migrate_v30` zet de blinde verdicten terug naar "nooit
  gevraagd" totdat de eerste providerfoto na 22 augustus binnen is; compose geeft
  `SPOTIFY_*`/`LASTFM_API_KEY`/`DISCOGS_TOKEN` door en mount `/app/data`. De 404 op
  `/api/artists/{naam}/image` doet niet meer alsof hij een lookup start -- Starlette liet die
  background task altijd al vallen. Zie docs/bug-reports/034.
