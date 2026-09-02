# Ratings & Scrobbling — Functional Design

> See [docs/designs/README.md](../README.md) for the overall process. This document describes the user-observable behavior for track ratings and listening history across the MuMa ecosystem.

## Overview

The Ratings & Scrobbling feature ensures that a user's track preferences and listening history are consistently managed and available across all clients (Web UI, Android app) and the core music library. It provides the data needed for personalized statistics, smart playlists, and cross-device library consistency.

## User Stories

- As a listener, I want to rate a track on my Android phone (MuMa Mobile) and see that rating reflected in the Web UI, so that my library remains consistent.
- As a listener, I want my plays to be recorded automatically, so that I can view my listening statistics later.
- As a listener, I want to see my most-played tracks in a "Recently Played" or "Top Rated" dynamic playlist.
- As a listener, I want to import my existing listening history from ListenBrainz, so that I don't lose my past data.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| User rates a track in MuMa Mobile (Android app) | The rating is sent to the Music Management Server (LMS). LMS notifies the Music Manager. The rating appears in the Web UI and is stored permanently in the main library database. |
| User rates a track in the LMS Web UI | LMS notifies the Music Manager. The rating is stored permanently in the main library database. |
| User plays a track until the end | The client reports the play to the scrobbler service. The listen is recorded in the history. If the track is recognized in the library, it's linked to the specific track record; otherwise, it's stored as an "unmatched" listen for future reconciliation. |
| User triggers a ListenBrainz import | Music Manager fetches the user's history from ListenBrainz in the background and populates the scrobble database. The user can monitor the progress of the import in the dashboard. |

## Acceptance Criteria

1. Track ratings are stored on a consistent 0-100 scale across the ecosystem (e.g., mapping 1-5 stars to 20-100 units).
2. Changing a rating multiple times for the same track updates the existing record rather than creating a new one.
3. Listen history includes the exact timestamp of the listen, the username, and the source (e.g., 'manual', 'listenbrainz').
4. Dynamic playlists can correctly filter and sort tracks based on the user's personal ratings.
5. Ratings are preserved even if the playback server's local database is wiped and rebuilt, as they are stored centrally in the Music Manager.

## Open Questions / Not Yet Decided

- ~~**Bidirectional Sync**~~: decided. Sync is one-way: LMS reports rating changes to the Music Manager, and the Music Manager never pushes back. The Music Manager is the archive, LMS the working copy; a rebuilt LMS database loses the stars in the player and keeps them centrally. See [Product Goal](../../product-goal.md), "Ownership of ratings and history".
- **Track Deletion**: If a track is deleted from the library, do its ratings and listens remain in the database for historical statistics?
- **Unmatched Reconciliation**: Is there an automated process to re-scan unmatched scrobbles when new tracks are added to the library?
- **Rating Scale Mapping**: Are 1-5 star ratings from all Subsonic clients consistently mapped to the 0-100 internal scale?
