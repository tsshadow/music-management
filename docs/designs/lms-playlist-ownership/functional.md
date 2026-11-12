# LMS Playlist Ownership — Functional Design

## Overview

The music server (LMS) keeps the smart playlists that people make in the player. Each hour,
music-manager copies them into its own `dynamic_playlists` table. Until now that copy only added
playlists and changed their name and rules. A playlist that was deleted in LMS stayed in
music-manager, a playlist that got a new owner stayed with the old owner, and a failed copy wrote
one line to the container output and nothing else.

Teun decided on 2026-11-12 that LMS owns a synced playlist (issue #223). music-manager follows it.

## User Stories

- As a listener, I want a playlist that I delete in the player to go away everywhere, so that it
  does not come back in another app.
- As a listener who gets a playlist from someone else, I want it in my own list, so that the
  previous owner does not keep it.
- As an admin, I want a failed playlist copy in the event log, so that I see it without reading
  container output.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| A playlist is deleted in LMS | At the next hourly sync, music-manager deletes its copy. |
| A playlist gets a new owner in LMS | At the next hourly sync, the copy moves to the new owner. |
| The new owner has no music-manager account | The copy stays as it is. |
| The copy fails | A `WARNING` event "Playlist sync failed for <server>", and nothing of that pass is saved. |
| A playlist made in music-manager itself (no LMS id) | Not touched by the sync. |

## Acceptance Criteria

1. One hour after a delete in LMS, the playlist is gone from music-manager.
2. One hour after an owner change in LMS, the playlist shows for the new owner only.
3. A failed sync shows as a `WARNING` in Beheer > Events.

## Open Questions / Not Yet Decided

- None.
