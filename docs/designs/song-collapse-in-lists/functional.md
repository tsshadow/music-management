# One entry per song in feeds and lists — Functional Design

## Overview

The library holds several files of one song: the official release, a radio edit, a SoundCloud or
YouTube rip. MuMa groups them into one song and names the best version, the canonical (see
[the song-versions design](../song-versions/technical.md)).
Until now the feeds and most lists ignored that grouping, so a song could appear twice, and a feed
could play the rip while the official version sat in the library (bug report 096). This makes every
surface outside the song's own page show one entry per song, and that entry is the canonical.

## User Stories

- As a listener, I want the Release Radar and the daily mixes to list a song once, so that two
  files of one song do not take two places.
- As a listener, I want a feed to play the official version of a song rather than a low-bitrate rip.
- As a listener, I want a song I heard in any version to count as heard, so a rip of it is not
  presented as new.
- As a listener, I want search, favourites, shuffle, genre lists, radio channels and the home
  shelves to show each song once.
- As a listener, I want the rating I gave any version of a song to show on the song, and a rating I
  change from a list to take effect.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| Two versions of one new song were released this week | The radar lists the song once, playing the canonical |
| Only the rip falls inside the radar's window | The radar lists the song, playing the canonical |
| I heard the official version, a rip of it is new | The rip does not rank as unheard |
| I starred the SoundCloud rip | Favourites shows the song once, as the canonical, starred |
| I rated the canonical 3 and the rip 5 | The song shows 3 |
| I unstar a song in favourites | It leaves the list, whichever version held the star |
| I open the song page | Every version is listed, each with its own rating |
| I open an album or a playlist | Unchanged: every file the album or I put there |

## Acceptance Criteria

1. The Release Radar and every daily mix (classic, artist, label, soft/mid/hard) contain at most
   one entry per song, and that entry plays the song's canonical.
2. A song counts as heard when any of its versions was played.
3. A feed dates a song by the newest release date among its versions that fell in the window.
4. Search results, favourites, shuffle (random songs), genre lists, radio channels and the phone
   home shelves "Recent uitgebracht" and "Recent toegevoegd" list each song once.
5. A song that MuMa has not grouped yet is still shown.
6. The rating a list shows for a song is the canonical's own, or the highest of the other versions
   when the canonical has none; changing or clearing it from a list takes effect.
7. Albums, playlists and the song page are unchanged.

## Open Questions / Not Yet Decided

- The song-versions design says a song shows "the highest rating in the group". Taken literally,
  lowering a song's rating from a list could never show, because the new rating lands on the
  canonical and a higher one elsewhere still wins. This design uses "the canonical's own, else the
  highest" instead. To be confirmed by Teun.
