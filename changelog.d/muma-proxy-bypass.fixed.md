- **Gewone MuMa-aanroepen gaan niet meer door LMS heen.** De reverse proxy stuurt `/muma/api/…`
  nu rechtstreeks naar MuMa; alleen wat LMS zelf implementeert (login, bibliotheekbeheer,
  artiestafbeelding en artiest-id voor de speler, track-refresh, `/muma/users/`) blijft bij LMS.
  De LMS-proxy hield per aanroep een Wt-thread vast, stuurde ze één voor één door en weigerde
  boven de helft van zijn pool — de oorzaak van de 503's bij het openen van de startpagina, en
  een grens die bij elke nieuwe aanroep op een scherm opnieuw in beeld kwam. MuMa controleert de
  `X-API-Key` zelf; LMS voegde daar niets aan toe behalve de flessenhals. Een nieuwe CI-job
  (`muma:proxy-routing`) draait de echte nginx-config tegen stubs en bewijst per route waar die
  heen gaat. Wat wél via LMS blijft lopen krijgt bij een weigering nu een `Retry-After`, en de
  web-UI wacht precies zo lang. De job-endpoints van MuMa (`/api/jobs/register`, `/active`,
  `/history`) vragen voortaan zelf een sleutel; ze leunden op de check die LMS ervoor deed.
