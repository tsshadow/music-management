# Big Changes in MuMa LMS Fork

This fork of `epoupon/lms` introduces **extended custom OpenSubsonic implementations, deeply coupled with a custom Ultrasonic client**. These enhancements transform the traditional Subsonic server into a modern, Spotify-like music ecosystem.

## Key Enhancements

### 1. Smart Deduplication Engine
The backend features a sophisticated deduplication logic (see `Spotify.cpp`) that:
*   **Normalizes metadata**: Intelligently handles artist separators (`,`, `&`, `feat.`, `ft.`) and strips title suffixes like `(radio edit)`, `(extended mix)`, etc.
*   **Quality Scoring**: Automatically selects the best version of a track based on:
    *   File Format: FLAC > MP3 > others.
    *   Bitrate: Higher bitrates receive higher scores.
    *   Metadata Completeness: Presence of MBID, release date, and rating.
*   **Hides Duplicates**: The UI and custom clients can request a deduplicated view, showing only the highest quality version of any song.

### 2. Extended Subsonic API (`spotify/` endpoints)
A set of custom REST endpoints provides advanced functionality beyond the standard Subsonic API:
*   `getSpotifyTracks`: Advanced filtering and sorting (by rating, duration, clusters) with built-in deduplication support.
*   `getSpotifyHistory`: Access to detailed user listening history.
*   `getSpotifyCuratedPlaylists`: Access to curated genre and radar playlists.
*   `spotifyImportFromListenBrainz`: Synchronizes listening history from external scrobbling services.


### 3. Festival Lineups & Cluster Filtering
*   **Festival Lineup Repository**: Ability to browse music based on specific festival lineups (e.g., Intents Festival) by matching artists against curated list files.
*   **Cluster Filtering**: Support for complex multi-criteria filtering using "Clusters" (Tags like Year, Genre, Label, etc.), allowing queries like "Hardcore from 2023 with rating > 4".

### 4. Deep Ultrasonic Integration
The **custom Ultrasonic client** is specifically modified to leverage these backend extensions. It utilizes the new `spotify/` endpoints to provide:
*   A "Spotify-style" browsing experience.
*   Better handling of high-resolution audio (FLAC).
*   Integrated curated genre and festival sections.
*   Synchronized ratings and play counts across the MuMa ecosystem.

### 5. Modern Spotify-like UI (Svelte)
A complete replacement of the default web interface, built with Svelte, focusing on speed, responsiveness, and a modern aesthetic inspired by Spotify.
