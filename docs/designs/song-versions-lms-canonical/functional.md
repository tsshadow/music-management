# One canonical version per song in the player — Functional Design

## Overview

MuMa groups every recording of a song (radio edit, extended mix, SoundCloud rip, the FLAC and the
MP3 of one release) under one *work* and picks one version to show. The app and Android Auto hide
the other versions by default ("canonical only"). This change makes the player's copy of that
choice exact: every song shows up exactly once, never twice and never not at all. Bug report
[097](../../bug-reports/097-lms-canonical-one-per-work.md) has the measurements that prompted it.

## User Stories

- As a listener with "canonical only" on, I want each song once in a list, so that I do not skip
  over the same track in two formats.
- As a listener, I want a song I own to show up even when the player lacks the version MuMa
  prefers, so that nothing I have silently disappears from my lists or the car.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| The preferred version exists as a FLAC and an MP3 | Only the FLAC is shown; the MP3 appears under "versions" |
| Two files of equal format | The higher-bitrate one is shown; on a full tie, the most recently scanned |
| The player does not have the preferred version's file | The best version the player does have is shown instead |
| A song MuMa has not grouped yet | Every file of it stays visible, as before |
| Nothing changed since the last hourly sync | The sync changes nothing in the player |

## Acceptance Criteria

1. With "canonical only" on, no song appears twice because it exists in two files.
2. No song the player has a file for is missing from a canonical-only list.
3. Turning "canonical only" off still shows every version.

## Open Questions / Not Yet Decided

- None. Which version wins inside MuMa is unchanged (see the song-versions design); this only
  changes how that choice reaches the player.
