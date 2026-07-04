# Scrobble Service

De Scrobble Service is verantwoordelijk voor het bijhouden van de luistergeschiedenis binnen het MuMa systeem.

## Functionaliteiten
- **Scrobble Tracking**: Ontvangt events van muziekspelers (bijv. LMS via een plugin).
- **Matchingsalgoritme**: Koppelt scrobbles automatisch aan de lokale `library_tracks` op basis van:
    1. MusicBrainz ID (MBID)
    2. Artiest en Titel match (fallback)
- **ListenBrainz Import**: Haal je luistergeschiedenis op van ListenBrainz om je lokale statistieken aan te vullen.
- **Unmatched Listens**: Slaat scrobbles op die nog niet in de bibliotheek zijn gevonden, zodat ze later alsnog gematcht kunnen worden.

## API Endpoints
- `POST /api/scrobble`: Verzend een nieuwe scrobble.
- `POST /api/import/listenbrainz`: Start een import van ListenBrainz.
- `GET /version`: Huidige versie van de service.
- `GET /release-notes`: Laatste wijzigingen.

## Database
De service gebruikt twee tabellen:
- `scrobble_listens`: Bevestigde en gematchte scrobbles.
- `scrobble_unmatched_listens`: Scrobbles die (nog) niet gematcht konden worden.
