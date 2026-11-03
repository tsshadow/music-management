# 🎨 Artist Image Fetcher

The Artist Image Fetcher is a service designed to enrich the music library with high-quality artist images from multiple sources. It prioritizes official images (Spotify) while supporting underground artists (SoundCloud, Last.fm) and provides a local cache for the LMS player.

## 🚀 Features

- **Multi-source fetching**: Spotify, SoundCloud, Last.fm, MusicBrainz.
- **Confidence Scoring**: Intelligent matching based on name similarity, MBID, and popularity.
- **Local Caching**: Local storage of images and thumbnails (64, 160, 300, 640px).
- **LMS Integration**: Stable path convention (`/media/artist-images/{id}/primary.jpg`).
- **Fallbacks**: Generated fallback images with artist initials if no source is found.

## 🛠 Configuration

The API keys are read through `services.common.config_store.credential()`: a value set on
**Management > Configuration** ("3rd Party APIs") wins, the environment is the fallback. On production
the environment is the Portainer stack env, passed through by `docker/docker-compose.yml`.
A run with no configured provider looks nothing up and marks nothing as failed -- see
`docs/bug-reports/034-artist-image-fetcher-ran-blind.md` for the month it did.

Environment variables:

```env
# API Keys
SPOTIFY_CLIENT_ID=your_id
SPOTIFY_CLIENT_SECRET=your_secret
LASTFM_API_KEY=your_key

# Storage Paths
ARTIST_IMAGE_STORAGE_PATH=/mnt/music/artists
ARTIST_IMAGE_PUBLIC_BASE_URL=/media/artist-images
ARTIST_IMAGE_REFRESH_DAYS=90
```

## ⌨️ CLI Usage

The service can be controlled via the CLI:

```bash
# Add project root to PYTHONPATH
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Fetch images for a specific artist by ID
python3 services/artist_image_fetcher/cli.py fetch --artist-id 123

# Fetch images for a specific artist by name
python3 services/artist_image_fetcher/cli.py fetch --name "A-Lusion"

# Fetch missing images for 100 artists
python3 services/artist_image_fetcher/cli.py fetch-missing --limit 100

# Refresh images older than 90 days
python3 services/artist_image_fetcher/cli.py refresh --older-than-days 90
```

## 📊 Database Schema

The service uses two main tables:
1. `library_artist_images`: Stores metadata for cached images.
2. `artist_external_ids`: Caches external IDs (Spotify ID, MBID, etc.) to speed up future lookups.

It also adds fields to `library_artists` to track image status.

## 🔗 LMS Integration

LMS can consume these images via:
1. **Stable Path**: Images are always available at `ARTIST_IMAGE_PUBLIC_BASE_URL/{artist_id}/primary.jpg`.

The storage directory used to carry a `manifest.json`, rewritten whole after every artist. Nothing
read it, so it is no longer maintained; an existing file is left on disk untouched.

## Image status

`library_artists.image_status` is `active` (has a portrait), `failed` (every configured provider
answered and none had a confident match; retried after `ARTIST_IMAGE_RETRY_AFTER_DAYS`), `cleared`
(removed by hand in the manager; the bulk run and a plain `/fetch-image` leave it alone, only
`/fetch-image?force=true` looks it up again) or empty (never decided). A provider that could not
answer, and a download or save that failed, write no status at all: the artist is asked again next
run.

## Downloading provider images

A portrait URL comes from a provider's API answer, so it is downloaded through `safe_fetch.py`, the
same path as the manual "image from URL" route: the host is resolved once, every address must be
public (no loopback, RFC 1918, Docker bridge, CGNAT/tailnet, link-local/metadata or IPv6 forms of
those), the connection goes to that checked address with the original name as `Host`, TLS SNI and
certificate name, redirects are re-checked per hop (at most three), and the body is capped at 10 MB.
A refused or oversized URL is not retried. See bug report 114.

## Logging and alerts

Every `WARNING` and `ERROR` becomes an event and a push on the `music-management-alerts` ntfy
topic, so a bulk run keeps per-artist trouble at `INFO` and counts it instead: a provider that could
not answer (MusicBrainz included -- timeouts, 5xx, transport errors), and a portrait that was found
but could not be downloaded or saved. A run logs at most two `WARNING`s -- the first rate limit it
hits, and the closing summary from `log_run_summary()` (artists deferred, rate-limit pauses and total
pause time, failed downloads, non-answers per provider) -- plus at most one `ERROR`, when the image
directory cannot be written. A `429` from Spotify or MusicBrainz, or a MusicBrainz `503` carrying
`Retry-After`, pauses the whole run for the requested time (default 30 s, capped at 10 minutes).
See bug reports 058 and 060.

Missing configuration is reported once per process, not once per fetcher: the manager builds a new
fetcher for every single-artist fetch. The Spotify credentials and Last.fm key (`WARNING`) and "no
configured image provider" (`ERROR`) go through `providers.base.log_once`, which logs at full level
the first time and at `DEBUG` after. Once a fetcher finds the setting present again the complaint is
re-armed, so removing it later is reported again. See bug report 065.
