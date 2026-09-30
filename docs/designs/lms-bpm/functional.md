# LMS BPM — Functional Design

## Overview

Since 0.86.0 MuMa writes the measured tempo into every file's own BPM tag (ID3 `TBPM`, MP4 `tmpo`,
Vorbis `BPM`; see [bpm-tag-writeback](../bpm-tag-writeback/functional.md)). The playback server
(LMS) did read that tag through TagLib, but threw it away: it stored no tempo per track and its
Subsonic song objects had no tempo field. A third-party Subsonic client (Symfonium, Feishin, DSub
...) therefore still showed no BPM, although the file carries one.

This change makes LMS keep the file's BPM and hand it out as OpenSubsonic's `bpm` field on every
song it returns (issue #150).

MuMa's own pages do not change: the web UI and the app keep showing MuMa's effective BPM
(measurement first), which is richer than a whole number from a tag (source, confidence, folded).
The LMS value is for other Subsonic clients and for later use.

## User Stories

- As a listener using a third-party Subsonic client, I want to see each song's tempo, so that I can
  pick music by BPM there too.
- As the operator, I want the existing library to pick the tempo up without re-tagging anything by
  hand.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| A file has a BPM tag of `150` (or `150.0`, or `150,4`) | Its song object carries `"bpm": 150` |
| A file has `150,5` | `"bpm": 151` (half up, as the writeback rounds) |
| A file has no BPM tag, or `0`, `abc`, `1500`, anything outside 40–500 | `"bpm": 0` (OpenSubsonic's "unknown") |
| MuMa's writeback rewrites a file's tag | LMS rescans the announced folder and the new value shows up |
| A file whose tag was already right (the writeback left it alone) | Filled by the one full re-read that follows the upgrade |
| A client that has OpenSubsonic disabled (legacy Subsonic) | No `bpm` field, as with every other OpenSubsonic field |

## Acceptance Criteria

1. `getSong`, `getAlbum`, `search3`, `getRandomSongs`, playlists and every other response that
   contains songs carry an integer `bpm` for OpenSubsonic clients.
2. A song whose file has no usable tempo reports `0`.
3. After the upgrade, one library scan re-reads every file once; after it every tagged file has its
   tempo, without anyone touching the files.
4. MuMa's web UI and the app look and behave exactly as before.

## Open Questions / Not Yet Decided

- None. Whether MuMa's UI should ever prefer LMS's value was decided: no, MuMa's measurement stays
  the source for MuMa's own pages.
