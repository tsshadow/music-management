- **The Release Radar and the daily mixes list a song once, and play its best version.** A feed
  treated every file as its own candidate, so two files of one song took two places (Deadly Guns -
  KOPPEN ROLLEN twice on the radar of 2026-09-26, one YouTube and one SoundCloud file of the same
  song), and "heard" was per file: a song heard in its official version made its 140 kbps rip rank
  as unheard, above it (ERABREAK - Elevate and four more). Every feed now collapses to one entry per
  song before ranking, plays the song's canonical even when only a rip fell inside the window,
  dates the song by its newest version, and counts a listen or a rating of any version as the
  song's. Bug report 096.
- **Search, favourites, shuffle, genre lists, radio channels and the phone home shelves show each
  song once.** The server's `search3` (with a query), `getStarred2`, `getRandomSongs`,
  `getSongsByGenre` and `getSongsByFilter` return only the canonical of a song (a song not grouped
  yet stays), a favourite version is listed as its song, and "Recent uitgebracht" / "Recent
  toegevoegd" ask for one row per song. Albums, playlists and the song page are unchanged. The row
  of a song shows the song's rating: the canonical's own, else the highest given to any version;
  clearing it clears every version, so unstarring from favourites works. Bug report 096.

<!-- release notes -->

- **The Release Radar and daily mixes no longer list a song twice, and play the official version
  instead of a SoundCloud or YouTube rip.** A song heard in any version now counts as heard.
- **Search, favourites, shuffle, genre lists, radio and the home shelves show each song once**, with
  the rating you gave any of its versions.
