# Android Auto Browse Parity — Functional Design

> Status: decided with Teun on 2026-09-19 after a walk through the car tree against the phone's
> Browse grid. Part 1 (the tree) shipped with this document; part 2 (a tapped track plays the
> list from there) followed in its own merge request.

## What was wrong

The car showed four tabs — Bibliotheek, Nummers, Livesets, Meer — because Android Auto draws at
most four root entries as tabs and folds the rest behind "Meer". The root had nine: Sets, the
daily mixes, the release radar, radio, news and Favorites were all hidden, which is the opposite of
what putting them at the root was for.

Under Nummers the only way into the library by tag was the genre chain: genre, then a year (or
"All"), then one of four sort orders, and only then a list. Three taps before anything played, and
no way to see the tracks without first committing to an order. Labels, podcasts, festivals, years
and lineups — every other tile on the phone's Browse grid — did not exist in the car at all.
"Recent afgespeelde genres" was there instead, and it did not work well.

A preset (a MuMa dynamic playlist) reached the car through a media id that had room for genre and
year only, so a preset built around a label or a festival played everything of its length.

## The tree

Exactly four tabs, never a fifth:

| Tab | Rows (grouped) |
|-----|----------------|
| **Start** | Voor jou: Dagelijkse mixen, Release radar · Favorieten: Favoriete nummers, Favoriete genres (once one is favourited), Presets · Live: Radio, Nieuws |
| **Nummers** | Bladeren: Genres, Labels, Jaren, Lineups, BPM (since issue #140, `../android-auto-bpm/`) · Afspelen: Willekeurig (plays), Recent toegevoegd, Recent uitgebracht |
| **Sets** | Bladeren: Genres, Soort (Sets & mixes / Livesets / Podcasts, see `track-form/`), Podcasts, Festivals, Jaren · Afspelen: the same three · Favorieten: Favoriete genres, Presets (sets) |
| **Bibliotheek** | Playlists, Artiesten, Albums |

Labels and lineups only exist under Nummers, podcasts and festivals only under Sets: the same split
`collections.js` applies on the web and the phone, for the same reason — the tagger writes neither
`PODCAST` nor `FESTIVAL` below ten minutes, and a label describes a release.

Every tag list (a genre, a label, a podcast, a festival, a year, a lineup) opens the **same folder**:

1. Alles afspelen — the whole list, newest release first (plays)
2. Willekeurig — the whole list, shuffled by the server (plays)
3. Recent toegevoegd — the whole list, newest addition first (plays)
4. Per jaar — a folder of years, each leading back into this folder narrowed to that year
5. the tracks, newest release first

A preset opens the same way: Alles afspelen, Willekeurig, then its tracks in its saved order; and
every filter the preset carries — label, festival, artists, rating, duration — now reaches the
server.

Removed: the Livesets tab (it was Sets without the favourites), "Recent afgespeelde genres", the
"Recente nummers"/"Recente sets" rows under Bibliotheek, and the Subsonic podcast-channel code that
was never in the tree.

## Decisions

- **Podcasts and festivals live under Sets**, not under Bibliotheek: parity with the phone's
  mode split. Bibliotheek stays mode-independent.
- **Default order in a tag folder is release date, newest first.** Willekeurig and Recent
  toegevoegd are the two other orders worth a row; the fourth of the old chain ("Recent
  aangepast") is gone.
- **Favorites are a section of Start**, not a tab: the four tabs are Start | Nummers | Sets |
  Bibliotheek. The old `MEDIA_FAVORITES_ID` folder still answers for a car that cached it.
- **Start is static.** The presets row is always there (empty on a fresh account) rather than
  hidden behind a server round trip before the first tab can draw.
- Tag lists sort by how much there is to hear, most first; years newest first. A car list is
  scrolled with one finger at a red light.

## A tapped track plays the list from there

Every song-level media id used to hand the car a queue of one, so a track tapped in any browsed
list played and then stopped. `onSetMediaItems` now resolves a tap to the list it was tapped in
plus a start index (`MediaLibraryPlaybackController.queueForTap`), off the main thread. A list
that no longer holds the track — a car that remembered an id from before the service restarted —
falls back to the old one-track path rather than playing nothing.

## Not in this change

- Downloads/offline, Geschiedenis, Memories and Luisterstatistieken in the car: other data sources
  (Room, the muma API), a separate design.
- Group headings on the tracks themselves. The play rows and the year folder carry a group; the
  tracks below them do not. Whether Android Auto draws that mix cleanly is a car test, not a unit
  test.
- `PODCAST` has to be in the LMS scanner's extra tags to scan, or the Podcasts list is empty —
  the same requirement the web page has.
