## [Unreleased]

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
