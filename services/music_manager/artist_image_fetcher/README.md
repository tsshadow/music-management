# 🎨 Artist Image Fetcher

The Artist Image Fetcher is a service designed to enrich the music library with high-quality artist images from multiple sources. It prioritizes official images (Spotify) while supporting underground artists (SoundCloud, Last.fm) and provides a local cache for the LMS player.

## 🚀 Features

- **Multi-source fetching**: Spotify, SoundCloud, Last.fm, MusicBrainz.
- **Confidence Scoring**: Intelligent matching based on name similarity, MBID, and popularity.
- **Local Caching**: Local storage of images and thumbnails (64, 160, 300, 640px).
- **LMS Integration**: Stable path convention (`/media/artist-images/{id}/primary.jpg`).
- **Fallbacks**: Generated fallback images with artist initials if no source is found.

## 🛠 Configuration

Configure the following environment variables in your `.env` file:

```env
# API Keys
SPOTIFY_CLIENT_ID=your_id
SPOTIFY_CLIENT_SECRET=your_secret
LASTFM_API_KEY=your_key

# Storage Paths
ARTIST_IMAGE_STORAGE_PATH=/var/lib/music-management/artist-images
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
2. **JSON Manifest**: A `manifest.json` is generated in the storage directory for batch processing.
