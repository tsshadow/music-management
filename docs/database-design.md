# Databaseontwerp

Dit document beschrijft het relationele datamodel dat gedeeld wordt door de `scrobbler`- en `analyzer`-modules. Het is bedoeld als referentie om snel te zien waar informatie zich bevindt en hoe tabellen met elkaar samenhangen.

## Hoogover overzicht

- **Gebruikersactiviteit** wordt vastgelegd in `listens`, met optionele relaties naar `tracks`, `artists` en `genres` om luistergedrag te verrijken.
- **Mediabibliotheek**-gegevens komen binnen via de analyzer. Deze module verrijkt artiesten, albums, tracks en bestanden en vult tevens associatietabellen (`track_artists`, `track_genres`, `track_labels`, `track_tag_attributes`).
- **Analyzer ↔ Scrobbler**: beide modules gebruiken dezelfde tabellen. De analyzer schrijft (en verrijkt) metadata, de scrobbler leest deze voor API-responses en gebruikersinterfaces en slaat nieuwe `listens` op.

### Relatiemodel (tekstuele weergave)

```
users ──< listens >── tracks ──< track_artists >── artists
                      │                       └── artist_aliases
                      │
                      ├──< track_genres >── genres ──< listen_genres >── listens
                      ├──< track_labels >── labels
                      ├──< track_tag_attributes >── tag_sources
                      ├──< title_aliases
                      └── media_files (1:N)

tracks ──< listen_match_candidates >── listens
tracks ──< listen_artists >── artists
albums ──< tracks
artists ──< albums
```

## Tabellen per domein

### Gebruikers

| Tabel | Doel | Belangrijkste kolommen | Opmerkingen |
|-------|------|------------------------|-------------|
| `users` | Beheer van applicatiegebruikers. | `username` (uniek), `created_at`. | `id` wordt gebruikt als foreign key in `listens`. |

### Muziekmetadata (door analyzer gevuld)

| Tabel | Doel | Belangrijkste kolommen | Relaties |
|-------|------|------------------------|----------|
| `artists` | Canonieke artiestenrecords. | `name`, `name_normalized` (uniek), `sort_name`, `mbid`. | Wordt gebruikt door `albums`, `tracks.primary_artist_id`, `track_artists`, `listen_artists`. |
| `artist_aliases` | Alternatieve schrijfwijzen voor artiesten. | `alias_normalized` (uniek). | Verwijst naar `artists.id`. Analyzer gebruikt dit bij normalisatie. |
| `albums` | Albums per artiest. | `title`, `title_normalized`, `year`, `mbid`. | `artist_id` → `artists.id`; unieke combinatie `artist_id` + `title_normalized`. |
| `tracks` | Kern van het datamodel. | `title`, `title_normalized`, `album_id`, `primary_artist_id`, `duration_secs`, `track_uid` (uniek), `mbid`, `isrc`, `acoustid`. | Verwijst naar `albums.id` en `artists.id`. Analyzer gebruikt `track_uid` voor deduplicatie. |
| `track_artists` | Rollen van artiesten per track. | `artist_id`, `role`. | Verbindt meerdere artiesten aan één track. |
| `title_aliases` | Alternatieve titels. | `alias_normalized`. | Verwijst naar `tracks.id`; gebruikt voor matching van listens. |
| `genres` | Canonieke genres. | `name`, `name_normalized`. | Verwijst vanuit `track_genres` en `listen_genres`. |
| `track_genres` | Koppelt tracks aan genres met een gewicht. | `weight` (standaard 100). | Combineert `track_id` en `genre_id`. |
| `labels` | Muzieklabels. | `name`, `name_normalized`. | Koppeling via `track_labels`. |
| `track_labels` | Verbindt tracks met labels. | - | Composiet primary key (`track_id`, `label_id`). |
| `tag_sources` | Herkomst van tag-attributen. | `name`, `priority`. | Referentie voor `track_tag_attributes`. |
| `track_tag_attributes` | Losse tag-waarde paren per track. | `key`, `value`, `source_id`. | Houdt attributen als stemming, BPM, etc. Bron wordt naar prioriteit gebruikt door analyzer. |
| `media_files` | Lokale mediabestanden gescand door analyzer. | `file_path`, `file_path_hash` (uniek), `file_size`, `file_mtime`, `audio_hash`, `duration_secs`, `parsed_metadata_json`, `last_scan_at`. | Verbindt één-op-veel naar `tracks` via matching (geen FK). Analyzer bewaart hier scanresultaten. |

### Luistergeschiedenis (hoofdzakelijk door scrobbler gevuld)

| Tabel | Doel | Belangrijkste kolommen | Relaties |
|-------|------|------------------------|----------|
| `listens` | Luisterevents per gebruiker. | `user_id`, `track_id`, `listened_at`, `source`, `source_track_id`, `artist_name_raw`, `track_title_raw`, `album_title_raw`, `enrich_status`, `match_confidence`. | FK naar `users` en optioneel `tracks`. Analyzer verrijkt listens en vult `enrich_status`, `match_confidence`, `last_enriched_at`. |
| `listen_match_candidates` | Bewaart alternatieve matches die analyzer vindt. | `track_id`, `confidence`. | Verbindt `listens` met mogelijke `tracks`. |
| `listen_artists` | Flattened artiesten per luisterevent. | - | Koppelt `listens` aan `artists`. |
| `listen_genres` | Genres per luisterevent. | - | Koppelt `listens` aan `genres`. |

### Configuratie

| Tabel | Doel | Belangrijkste kolommen |
|-------|------|------------------------|
| `config` | Slaat sleutel/waarde configuratie op, bijvoorbeeld ingestelde analyzers of API-keys. | `key`, `value`, `updated_at`. |

## Gebruikspatronen

- **Analyzer ingest**: leest bestanden (`media_files`), maakt of actualiseert `artists`, `albums`, `tracks` en relaties (`track_artists`, `track_genres`, `track_labels`, `track_tag_attributes`, `title_aliases`). Bij matching van listens vult de analyzer `listen_match_candidates` en past `listens.track_id`, `enrich_status` en `match_confidence` aan.
- **Scrobbler API/UI**: schrijft nieuwe `listens` (met ruwe velden `artist_name_raw`, `track_title_raw`, `album_title_raw`) en raadpleegt verrijkte data via de relaties. Het gebruikt de canonicale metadata om zoek- en browsefuncties te ondersteunen.

## Kolomreferentie

Onderstaande tabel biedt een snelle mapping van veelgebruikte eigenschappen:

| Eigenschap | Tabel.kolom | Beschrijving |
|------------|-------------|--------------|
| Titel (canoniek) | `tracks.title` | De uiteindelijke titel gebruikt in UI en matching. |
| Titel (genormaliseerd) | `tracks.title_normalized` | Analyzer gebruikt dit voor deduplicatie. |
| Artiestnaam (canoniek) | `artists.name` | Gebruikt voor weergave. |
| Artiestnaam (genormaliseerd) | `artists.name_normalized` | Unieke sleutel voor artiestmatching. |
| Albumtitel | `albums.title` | Bijhorende album van een track. |
| Ruwe artiestinput | `listens.artist_name_raw` | Originele string uit bron, vóór matching. |
| Ruwe tracktitel | `listens.track_title_raw` | Originele titel uit bron. |
| Speelduur (track) | `tracks.duration_secs` | Duur in seconden volgens analyzer. |
| Speelduur (listen) | `listens.duration_secs` | Waargenomen duur van het luisterevent. |
| Genre | `genres.name` / via `track_genres`, `listen_genres` | Canoniek genre. |
| Label | `labels.name` | Muzieklabel gekoppeld aan track. |
| Audiohash | `media_files.audio_hash` | Analyzer gebruikt dit om duplicaten te herkennen. |

## Indexering en constraints

- Uniciteit op `artists.name_normalized`, `albums.artist_id + title_normalized`, `tracks.track_uid`, `track_artists` (track/artist/role) en `track_labels`, om duplicaten te voorkomen.
- `listens` heeft een `uq_listen_dedupe` constraint op (`user_id`, `track_id`, `listened_at`) om dubbel scrobblen te beperken.
- Indexen op normaliseerde namen en statusvelden versnellen analyzer queries voor matching en enrichment.

## Uitbreiding

Nieuwe tabellen kunnen het beste aansluiten op de bestaande normalisatieaanpak:

1. Introduceer een canonicale tabel met normaliseerde kolommen (`*_normalized`).
2. Gebruik join-tabellen met composiet primary keys voor N:N-relaties.
3. Voeg ruwe bronkolommen toe in `listens` of een analoge event-tabel om gegevensverlies te vermijden.

Deze richtlijnen houden analyzer en scrobbler in sync en maken het eenvoudig om eigenschappen te lokaliseren en te verrijken.
