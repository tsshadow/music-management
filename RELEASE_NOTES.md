# Release Notes - Music Management Suite

This project is now modularized. Detailed release notes for each module can be found in their respective directories:

- [Scanner Module](services/scanner/RELEASE_NOTES.md)
- [Tagger Module](services/tagger/RELEASE_NOTES.md)
- [Downloader Module](services/downloader/RELEASE_NOTES.md)
- [Importer Module](services/importer/RELEASE_NOTES.md)
- [Music Manager](services/music_manager/RELEASE_NOTES.md)
- [ML Analyzer](services/ml-analyzer/RELEASE_NOTES.md)

## Unreleased

## Global Version 0.0.21 (2026-07-28)
### 📱 Officiële Ultrasonic release-APK wordt nu volledig automatisch gebouwd en gepubliceerd
De automatisering om een ondertekende Ultrasonic-APK te bouwen en naar apk-hoster te uploaden
bestond al in de code, maar heeft nog nooit echt een release opgeleverd: de originele
ondertekeningssleutel was nergens meer terug te vinden.
- Een gloednieuwe ondertekeningssleutel gegenereerd en samen met de apk-hoster inloggegevens
  veilig ingesteld als CI/CD-variabelen (nooit in de code).
- `ultrasonic:build-release` draait nu automatisch bij elke release-pipeline en zet de
  ondertekende APK meteen online op https://apk.example.com.
- Bugfix: de sleutel werd op de verkeerde manier doorgegeven aan het bouwscript (rauwe bytes in
  plaats van tekst), waardoor de build altijd zou zijn mislukt; dit is opgelost.
- Bugfix: een verwijzing naar een map op de laptop van Teun stond per ongeluk in de broncode,
  waardoor de publicatiestap in elke andere omgeving (waaronder CI) altijd faalde; verwijderd.
- Alle oude, handmatig geüploade APK's zijn van apk-hoster verwijderd (schone lei), en de
  app-versie is opgehoogd naar 6.5.3 (233) als eerste officiële, automatisch gebouwde release.
- ⚠️ Let op: door de nieuwe sleutel moet iedereen die een eerdere, handmatig ondertekende versie
  (bv. v6.5.2-214) had geïnstalleerd, de app eenmalig verwijderen en opnieuw installeren.

## Global Version 0.0.20 (2026-07-28)
### 📦 Importer bleef dubbele mappen voor altijd als foutmelding herhalen
Bij het verder doorspitten van de productielogs bleek de import-dienst dezelfde ~15 misleidende
"schijfruimte/bestandssysteem"-foutmeldingen te blijven herhalen bij elke controle, voor releases
die eigenlijk allang succesvol waren geïmporteerd.
- **Oorzaak**: er bestond al een specifieke afhandeling voor "deze release is al eerder
  geïmporteerd", maar die werd voor dit specifieke type conflict niet aangeroepen, waardoor de map
  nooit werd opgeruimd en bij elke ronde opnieuw als fout in de logs verscheen.
- **Fix**: dit type conflict wordt nu op dezelfde manier afgehandeld als het al bestaande geval —
  de dubbele map wordt automatisch opgeruimd zodat deze niet steeds opnieuw als fout terugkomt. Een
  echt schijfruimteprobleem blijft gewoon als fout gemeld — zie
  `docs/bug-reports/008-importer-duplicate-folder-stuck-forever.md`.

## Global Version 0.0.19 (2026-07-28)
### 📡 Telegram-achtergronddienst crashte bij het opstarten (versieconflict in inlogbestand)
Tijdens het doorspitten van de productielogs bleek de Telegram-achtergronddienst te crashen bij het
laden van zijn inlogbestand, in plaats van gewoon te verbinden.
- **Oorzaak**: bij het bouwen van deze specifieke dienst werd, naast de vastgelegde versie van de
  gebruikte bibliotheek, per ongeluk ook nog een tweede, niet-vastgelegde installatie uitgevoerd.
  Daardoor kon elke nieuwe bouw een andere versie van die bibliotheek installeren, en die bibliotheek
  slaat het inlogbestand op in een formaat dat per versie kan verschillen — waardoor een oudere bouw
  het bestand van een nieuwere bouw niet meer kon lezen.
- **Fix**: de vastgelegde bibliotheekversie is bijgewerkt naar een versie die past bij het bestaande
  inlogbestand, en de overbodige, niet-vastgelegde installatie is verwijderd zodat elke bouw voortaan
  altijd exact dezelfde, geteste versie gebruikt — zie
  `docs/bug-reports/007-telegram-session-schema-mismatch.md`.
- **Extra ontdekking**: deze fix bleek na een volledig geslaagde uitrol tóch nog niet op productie
  te staan. Het bleek dat de automatische uitrol tot nu toe alleen de twee hoofdonderdelen ververste
  en alle overige achtergronddiensten (waaronder Telegram) nooit automatisch opnieuw bouwde en
  publiceerde. Dit is nu gerepareerd: voortaan worden al deze onderdelen bij elke release automatisch
  meegenomen.

## Global Version 0.0.18 (2026-07-28)
### 🖼️ Artiestenafbeeldingen-tab stond permanent vast op "0 / 0 artiesten"
Het beheerscherm "Artist Images" toonde altijd "0 / 0 artiesten", zoeken gaf nooit resultaten en de
RESCAN-knop liet geen voortgang zien — terwijl de artiesten- en afbeeldingsgegevens zelf wél gewoon
correct in de database stonden.
- **Oorzaak**: een stuk tussenlaag-code in de player onderschepte élk verzoek dat begint met
  `/api/artists/`, nog vóórdat het bij de normale doorstuurlaag naar `music-manager` kon komen. Die
  tussenlaag kende maar twee specifieke gevallen (een afbeeldingsverzoek, of een los numeriek
  artiest-ID voor de speler zelf) — alle andere aanroepen zoals de statistieken, zoekfunctie en
  scanvoortgang werden daardoor altijd afgewezen met een foutmelding, nog vóór ze de beheertool
  bereikten.
- **Fix**: de tussenlaag onderschept nu alleen nog die twee specifieke gevallen; alle andere
  artiest-gerelateerde aanroepen worden weer gewoon normaal doorgestuurd — zie
  `docs/bug-reports/006-artist-images-tab-zero-stats.md`.

## Global Version 0.0.17 (2026-07-28)
### 🚨 Inloggen deed het niet meer op productie (`no such column: u.password_salt`)
Elke inlogpoging — met gebruikersnaam/wachtwoord én via Google — crashte met een databasefout.
- **Oorzaak**: een achtergrondtaak in `music-manager` verwijderde per ongeluk de echte, permanente
  gebruikerstabel van de player rechtstreeks uit de live database (op basis van een verkeerde aanname
  dat die tabel net als sessie-gegevens alleen tijdelijk in het geheugen zou bestaan). Dit gebeurde
  precies op het moment dat de player zelf ook zijn database aan het initialiseren was, waardoor een
  onvolledige noodgreep in de player de tabel herstelde zonder een aantal verplichte kolommen.
- **Fix**: de destructieve opschoning in `music-manager` is volledig verwijderd (die diende sowieso
  geen functioneel doel meer), en de noodgreep in de player is bijgewerkt zodat die nooit meer een
  onvolledig tabelontwerp kan aanmaken.
- **Productie**: direct handmatig herstel toegepast (ontbrekende kolommen teruggezet, player herstart)
  zodra het probleem bevestigd was, ruim vóór deze release werd uitgerold — zie
  `docs/bug-reports/005-lms-user-table-corruption.md`.

## Global Version 0.0.16 (2026-07-28)
### 🐛 Artiestenafbeeldingen werken weer in het beheerscherm en de player
- **Beheerscherm (`bug 004`)**: afbeeldingsverzoeken voor artiesten misten authenticatie en kregen daardoor altijd een `401 Unauthorized`; de API-key wordt nu meegegeven als `apiKey` queryparameter.
- **Synchronisatiepad productie (`bug 004`)**: het pad waarmee `music-manager` de eigen database van de `lms`/`alpha-lms` stacks benadert (voor gebruikers/afspeellijsten en artiestenafbeeldingen) wees naar een map die op productie nooit heeft bestaan; dit wijst nu standaard naar de daadwerkelijke datamappen van de `lms`/`alpha-lms` stacks.

## Global Version 0.0.15 (2026-07-28)
### 🔗 "Alles tonen" knoppen op de homepagina doorverwijzen naar juiste tabs en views
- **Release Radar**: knop "Alles tonen" opent direct de Release Radar tab.
- **Songs**: knop "Alles tonen" schakelt de view mode naar nummers en opent de songstip.
- **Sets**: knop "Alles tonen" schakelt de view mode naar sets en opent de setstab.

## Global Version 0.0.14 (2026-07-28)
### 🎨 "MuMa Beheer" knop in profielmenu verwijderd
- **Profielmenu (`ProfileButton.svelte`)**: de "MuMa Beheer" knop in het dropdownmenu van het profiel is verwijderd, aangezien het beheren van het systeem al volledig bereikbaar is via de Player/Beheer schakelaar in de hoofd-zijbalk.

## Global Version 0.0.13 (2026-07-28)
### 🐛 Populair genres semicolon-delimiter & ontbrekende artiestenafbeeldingen gefixed
- **Populair genres (`bug 002`)**: statistieken top-genres (`stats.py`) splitst samengestelde genre-strings gescheiden door puntkommas (`;` / `,`), trimt spaties en telt individuele subgenres correct.
- **Artiestenafbeeldingen (`bug 003`)**: achtergrond- en handmatige taken voor ontbrekende artiestenafbeeldingen (`run_fetch_missing` in `artist_images.py`) verwerken nu alle artiesten waarbij `primary_image_id IS NULL`, ongeacht hun eerdere `image_status`.

## Global Version 0.0.12 (2026-07-28)
### 🐛 Gestructureerde bugreports & fetch-progress fix
- **Gestructureerde bugreports**: Geïntroduceerd volgens een 2-staps workflow onder `docs/bug-reports/00#-<title>.md` met velden voor status, probleem, oorzaak en oplossing (`AGENTS.md` bijgewerkt).
- **Artist fetch-progress fix**: Voorkomt dat het pollen van fetch-progress onterecht een foutmelding geeft na afronding.

## Global Version 0.0.9 (2026-07-28)
### 🎨 Kleine UI-opschoning in zijbalk en profielmenu
- **Legacy UI knop verwijderd**: de knop "Oude UI (Legacy)" in het profielmenu is definitief weggehaald.
- **Geïntegreerde bibliotheek**: alle bibliotheek-onderdelen (afspeellijsten, artiesten, albums, genres, geschiedenis, favorieten) staan nu direct in de hoofd-zijbalk met duidelijke iconen; de kop "JOUW BIBLIOTHEEK" is vervallen.
- **Overbodig Systeembeheer-item weg**: het menu-item "Systeembeheer" in de zijbalk is verwijderd aangezien de schakelaar (Player/Beheer) in de header dit al regelt.

## Global Version 0.0.8 (2026-07-28)
### 🚪 Uitloggen na Google Auth liet sessiedata achter ("Gebruiker")
Wanneer je ingelogd was via Google Auth en uitlogde, bleef de webapp sessiegegevens (`mumaSessionActive`, `mumaApiKey`, `mumaRefreshToken`, `userPermissions`, `mumaUser`) en localStorage-waarden vasthouden. Hierdoor bleef je hangen als 'Gebruiker' zonder muziekrechten.
- **Fix**: de uitlogfunctie (`handleLogout` in `ProfileButton.svelte`) wist nu grondig alle sessiestores en bijbehorende localStorage-items (`muma_api_key`, `muma_refresh_token`, `muma_session_active`), zodat uitloggen ook echt de volledige sessie opschoonde.

## Global Version 0.0.7 (2026-07-28)
### 🔐 Vaste inlogpagina in plaats van inlogmodal
De inlogmodal is losgekoppeld van de hoofdweergave en omgevormd tot een vaste, volwaardige inlogpagina.
- **Vaste inlogpagina**: wanneer je niet bent ingelogd, toont de webapp altijd een dedicated full-screen inlogpagina (`LoginPage.svelte`) in plaats van een overlay bovenop de app.
- **Automatische doorverwijzing**: bezoek je de app zonder geldige sessie, dan word je automatisch doorgestuurd naar `/login`.

## Global Version 0.0.6 (2026-07-27)
### 🎵 Inloggen met Google liet je zien als "Gebruiker" zonder muziek
Inloggen met Google werkte, en je rechten/rol klopten, maar je zag jouw naam niet en er kwam geen
enkel nummer, album of genre in beeld — `getGenres` gaf zelfs een foutmelding over een ontbrekende
parameter.
- **Oorzaak**: na een Google-login werd je gebruikersnaam/wachtwoord nergens in de webapp
  opgeslagen — en precies die twee velden gebruikt de webapp voor élke aanroep naar de muziekbibliotheek
  (en om je naam te tonen), omdat een Google-login nooit je echte wachtwoord te weten komt.
- **Fix**: bij een geslaagde Google-login gebruikt de webapp nu een speciale, al bestaande sleutel van
  je account als vervangend wachtwoord voor deze aanroepen. Je ziet nu weer gewoon je eigen
  gebruikersnaam, en je muziekbibliotheek (albums, genres, afspelen) werkt weer — precies zoals bij
  inloggen met gebruikersnaam/wachtwoord.

## Global Version 0.0.5 (2026-07-27)
### 🔐 De Google-inlogknop was weer verdwenen — en de server controleerde niet meer echt wie er inlogde
Na de vorige uitrol stond alleen nog gebruikersnaam/wachtwoord op het inlogscherm; de Google-knop was weg.
Oorzaak: de instelling met de Google Client ID stond nergens in de configuratie die automatisch gebruikt
wordt bij het bouwen en uitrollen — die stond alleen (handmatig) op de server zelf, en werd bij de eerste
automatische heruitrol overschreven met een lege waarde.
- **Fix**: de Google Client ID staat nu in de centrale configuratie die bij elke automatische build en
  uitrol wordt gebruikt, zodat de knop weer verschijnt en blijft verschijnen bij volgende releases.
- **Extra beveiliging**: zolang deze instelling ontbreekt, accepteerde de server stilzwijgend een
  Google-login van *elke* Google-app, niet alleen de onze. Inloggen met Google geeft nu een duidelijke
  foutmelding als deze instelling ooit weer zou ontbreken, in plaats van dit onopgemerkt te laten gebeuren.
- Inloggen met gebruikersnaam/wachtwoord én inloggen met Google gebruiken al hetzelfde onderliggende
  account zodra ze gekoppeld zijn (zie 0.0.3) — deze fix zorgt er alleen voor dat beide manieren van
  inloggen weer daadwerkelijk beschikbaar zijn.
- **Bonus-fix**: als de webinterface een foutmelding van de beheerserver doorstuurde (bijvoorbeeld
  "verkeerd wachtwoord" of "nummer niet gevonden"), werd die foutmelding onderweg vervangen door een
  onduidelijke generieke storingsmelding. De echte foutmelding komt nu correct door.
- **Om herhaling te voorkomen**: er is een extra, verplichte controle toegevoegd die bij elke uitrol
  vanaf een release-tak automatisch checkt of deze Google-instelling daadwerkelijk aanwezig is, en die
  de uitrol direct en duidelijk blokkeert als dat niet zo is — in plaats van dat de knop stilletjes
  verdwijnt bij de volgende build.

## Global Version 0.0.4 (2026-07-27)
### 🔐 Succesvolle Google-login toonde toch een foutmelding
Een geldige, gekoppelde Google-login kwam soms met status `200 OK` netjes terug van de server, maar de
webapp toonde alsnog "Kon geen verbinding maken met de Google login API" en je bleef op het inlogscherm
staan.
- **Fix**: `/api/auth/google` (en `/api/auth/login`, `/api/auth/refresh`) geven de gebruikersgegevens nu
  altijd genest onder een `user`-veld terug, zoals de webapp al overal verwacht en zoals ook
  `/api/auth/verify` al deed — in plaats van deze los boven het antwoord te plaatsen.

### 🔐 Google Sign-In popup blokkeerde soms zichzelf
Sommige browsers lieten in de console de melding "Cross-Origin-Opener-Policy policy would block the
window.postMessage call." zien tijdens het inloggen met Google — hierdoor kwam het ID-token soms niet
correct terug bij de webapp.
- **Fix**: de reverse proxy voor de webapp stuurt nu expliciet `Cross-Origin-Opener-Policy:
  same-origin-allow-popups` mee, zodat de Google-inlogpopup altijd met de pagina kan blijven
  communiceren.

## Global Version 0.0.3 (2026-07-26)
### 🔐 Google Sign-In werkt nu écht, end-to-end
De "Sign in with Google"-flow bestond al, maar de knop verscheen niet in productie (de Client ID werd
nooit meegebouwd), en zodra dat gefixt was, gaf inloggen alsnog `401 Unauthorized` en misten admins hun
beheerknoppen. Daarnaast kon je twee accounts van dezelfde persoon niet meer samenvoegen.
- **Google-knop verschijnt nu écht**: elke plek die het `lms`-image bouwt (lokaal, LMS build-script en
  CI) geeft de Client ID nu mee als build-arg, zodat deze daadwerkelijk in de gebouwde bundel terechtkomt.
  Gedocumenteerd in een nieuwe "Google Sign-In setup"-sectie in `docs/deployment.md`.
- **Google/access-request logins zijn niet langer geblokkeerd**: de proxy tussen de webapp en de
  beheerbackend laat een nieuwe Google-login nu daadwerkelijk door in plaats van deze te blokkeren
  voordat hij zelfs gecontroleerd wordt.
- **Je eigen login wordt niet meer omgewisseld voor een generieke**: elk verzoek via die proxy behoudt nu
  je eigen identiteit, zodat de backend je echte rol en rechten correct laat zien.
- **Beheerknoppen zijn terug**: de Beheer-tab herkent admins (via Subsonic of Google) nu weer correct en
  toont de gebruikersbeheer-knoppen die voorheen verborgen waren.
- **Accounts samenvoegen**: dubbele accounts (bijv. door een Google-toegangsaanvraag voor iemand die al
  een lokaal account had) kunnen nu samengevoegd worden tot één account; een toegangsaanvraag kan ook
  direct aan een bestaand account gekoppeld worden in plaats van er altijd een nieuw account van te maken.
- **Verwijderen van gebruikers is robuuster**: mislukte verwijderingen geven nu een duidelijke
  foutmelding, en de laatste beheerder kan niet meer per ongeluk verwijderd worden.

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
- **Streamlined Project Layout**: The verwarrende `music-management/` intermediate folder is gone. By moving `services/` to the root, we've simplified the project structure, `PYTHONPATH` management, and Docker builds.
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
