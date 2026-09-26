# Song versions: best-version ranking and the Versions page — Functional Design

Date: 2026-09-26. Decision by Teun (owner). Replaces the ranking order in
[the original song-versions design](../../superpowers/specs/2026-08-23-song-versions-and-canonical-design.md#ranking);
grouping, the pin, the split and the LMS sync from that design are unchanged.

## Overview

A song often exists several times in the library: a SoundCloud rip, a YouTube rip, the label
release as radio edit and as extended mix, sometimes as both FLAC and MP3. MuMa plays one of them
(the *best* version) and keeps the others reachable. The old ranking put "official release" first,
and "official" meant "has a label and is not in a download archive". A release still waiting in
`EPs/__TODO` has no label yet, so it counted as unofficial and lost to a rip. Measured on
production before this change: 1,428 songs picked a version while a better-format sibling existed,
and 549 picked a SoundCloud/YouTube/podcast rip over a sibling in the label folder
(e.g. Hysta & RDØ – TOGETHER).

Teun's decision, in his words: "FLAC (a setting if you want lossless) or MP3; preference pro edit >
radio edit > extended mix > music video (pro or radio edit are usually best for listening). Usually
you want FLAC radio edit, or MP3 radio edit if storage is an issue."

## User Stories

- As a listener, I want the lossless release of a song to play rather than a rip, so that what I
  hear is the best copy I own.
- As the owner, I want one setting to prefer MP3 over FLAC, so that I can trade fidelity for storage
  and bandwidth without curating song by song.
- As a listener, I want a pro edit or radio edit to win over an extended mix or a music-video rip,
  so that the version I hear is the one made for listening.
- As a curator, I want a page listing every song with several versions and which one plays, so that
  I can check the choice and override it where it is wrong.
- As a curator, I want to see which songs the new ranking changed, so that I can review exactly
  those instead of the whole library.

## Functional Flows

### The ranking

Decided in this order; each step only matters when all earlier steps tie:

1. **Format**, driven by the setting `prefer_lossless` (Beheer → Configuratie, group "Song
   versions", default on):
   - on: lossless (FLAC/ALAC/WAV/AIFF) > MP3 320 > AAC/M4A/Opus > MP3 192 > lower;
   - off: MP3 320 > AAC/M4A/Opus > lossless > MP3 192 > lower.
   Rips from SoundCloud/YouTube are lossy, so they naturally lose to a proper release file.
2. **Version kind**: pro edit/pro mix > radio edit > edit > original mix > no marker > extended mix >
   instrumental/acapella/dub > music video/official video/visualizer/"official audio".
3. **Bitrate**, in 32 kbps steps (so a large embedded cover does not count as quality).
4. **Official release**: a file under the label tree (`EPs/`, including the import queue
   `EPs/__TODO`), or a file with a label that did not come from a download archive.
5. **Oldest** first, then lowest id, so the choice does not wander.

A manual pin always wins.

| Situation | Observable outcome |
|---|---|
| A FLAC radio edit in `EPs/` and a 320 MP3 SoundCloud rip, setting on | The FLAC plays |
| Same, setting off | The MP3 plays (format decides first) |
| A release in `EPs/__TODO` (no label yet) and an equally good rip | The release plays (official breaks the tie) |
| A pro edit and a radio edit, same format | The pro edit plays |
| An "(Official Video)" rip and a plain upload, same format | The plain upload plays |
| A song pinned on the Versions page | The pinned version plays, whatever the ranking says |
| The ranking changes (deploy, or the setting flipped) | Within the hour every song is re-ranked; songs whose choice changed are flagged |

### The Versions page (Beheer → Curatie → Versies)

| Situation | Observable outcome |
|---|---|
| Open the page | Songs with more than one version, 50 per page, most versions first; the ranking in force and how many songs a rescore changed are shown under the title |
| Type in the search box and press Enter | Songs whose title or artist matches, from page 1 |
| Sort by "Recently changed" / tick "Only changed by the rescore" | Flagged songs first / only flagged songs |
| Open a song | Each version with title, path, source (label release, SoundCloud, YouTube, other), format and bitrate, kind, rating and plays; the playing one marked "Best", the one before a rescore marked "Was best" |
| "Pick as best" on a version | That version is pinned and plays from now on; the flag clears |
| "Reset to automatic" (pinned songs) | The pin is removed and the ranking decides again |
| "Accept new choice" (flagged songs) | The flag clears; the new choice stays |
| A user without `rules.manage` presses a button | The server's refusal is shown; nothing changes |

## Acceptance Criteria

1. With the setting on, a FLAC release beats every lossy version of the same song regardless of
   kind; with it off, an MP3 320 beats the FLAC.
2. Within one format, pro edit > radio edit > edit > original > no marker > extended >
   instrumental > video.
3. A release in `EPs/__TODO` beats an otherwise equal rip.
4. A pinned version plays after any rescore and after flipping the setting.
5. After deploy the worker logs, before changing anything, how many songs the new ranking will
   change, then applies it and logs the result. A second run changes nothing.
6. The Versions page lists, searches, sorts and pages as described; pin, reset and accept work and
   are refused without `rules.manage`.
7. What LMS plays follows within one sync pass (hourly); the file LMS shows for a track follows the
   same format order.

## Open Questions / Not Yet Decided

- Grouping "(Pro Edit)" and "(Official Music Video)" with the other versions of the song is a
  separate change: this one only teaches the *kind* detector those words, so a pro edit currently
  still forms a song of its own until that change lands.
- Mobile shows no version UI of its own for this; it follows LMS's canonical.
