# Phone UI polish — Functional Design

Follow-up to [`universal-ui/`](../universal-ui/functional.md). The universal UI ships on the phone
since muma-mobile 7.0.0; a side-by-side with Spotify (2026-09-17) showed the skeleton is right and the
screens are empty. This design covers the visual and behavioural fixes, in the order they will be
built. Missing production data (empty feeds, absent cover art) is explicitly out of scope: every
change here must look right *with* and *without* data.

## Overview

Three phone screens are touched: Home, Browse (Bladeren) and the full-screen player (Now Playing).
The player gets the most work — it is the screen a listener looks at longest and it was the barest.
The work is split into eight increments (A–H) that each ship as their own merge request; later
increments may refine earlier ones, but nothing in an earlier increment depends on a later one.

## User Stories

- As a listener, I want the player to look like something when a track has no cover, so that a
  library that is mostly uncovered does not read as broken.
- As a listener, I want to see where I am playing from and reach the artist, genre and label from the
  player in one tap, so that the player is a place to continue from, not a dead end.
- As a listener, I want Home to show me something to play below the shortcuts, so that the screen is
  not half empty.
- As a listener, I want Browse to remember the artists, labels and festivals I opened recently, so
  that the fixed category grid is not the only way in.
- As a listener, I want to see which speaker or headset is playing and switch it, so that I do not
  have to leave the app for the system settings.

## Functional Flows

### A — Player artwork and background

| Situation | Observable outcome |
|---|---|
| Track has a cover | The cover fills the artwork square, at a resolution suited to the screen (not the mini-player thumbnail). |
| Track has no cover, artist has an image | The artist image fills the square instead. |
| Neither exists | A flat panel in the track's genre tint shows the title in large text. The MuMa mark is not shown at that size. |
| Any track | The screen background is a vertical gradient from the genre tint (top) into the standard dark background (below the artwork), so the screen is never flat black. |
| Track has several genres | The first genre that the server has a tint for decides the colour; no tint at all gives the neutral surface colour. |
| Mini player | One square image slot with the same cover → artist → tint fallback; the separate round artist avatar next to the artist name disappears. |

### B — Player header, metadata and controls

| Situation | Observable outcome |
|---|---|
| Header | Two lines: a small "Playing from" caption and the source name in bold sentence case. No capitals. |
| Header, right side | A ⋮ button opens a sheet with: go to artist, go to album, play next, add to queue, lyrics (when present), details. Lyrics access is not lost. |
| Genres and label | Rendered as tappable chips (the same chips the details sheet already uses), never clipped to one row; the release date moves to the details sheet. |
| Artist line | Looks tappable (chevron, hit area the full row height); with several artists each name stays its own tap target. |
| Rating | Stars are larger with a 44px tap target; tap-again-to-clear keeps working. |
| Transport icons | Shuffle, repeat, previous, next and the bottom-row icons share one visual weight. |

### C — Home and Browse layout

| Situation | Observable outcome |
|---|---|
| Shortcut tile with no tracks | The subtitle is a designed line for that destination ("Ontdek nieuwe releases", …), never the generic "no tracks in this section". A failed load reads as failed; a loading tile shows a skeleton. |
| Odd number of shortcut tiles | The last tile spans the full width; there is no orphan half-row. |
| "Show all" | Sentence case, normal tracking. |
| Recent-tracks shelf | Compact rows (thumbnail, title, artist) instead of large square cards with a placeholder. |
| Browse | The advanced-search card leaves the top of the screen; a filter icon beside the search bar opens it. Category tiles are shorter (≈64–72 CSS px). |

### D — Useful Home rows

| Situation | Observable outcome |
|---|---|
| Memories loaded | A "Memories" year row appears with one tile per year, tapping one opens that year. |
| Songs mode | A "Recently added" shelf of recent tracks. Sets mode: a "Recent sets" shelf. |
| Rows without data | Hidden, not shown empty. |

### E — Recent places and accurate source

| Situation | Observable outcome |
|---|---|
| Listener opens an artist, album, genre, label, festival, playlist or year | That place is remembered on this device for this server and account, most recent first, capped at 12. |
| Browse | A "Recent" row above the category grid lists those places; tapping one opens it. Hidden when empty. |
| Player header | "Playing from" names the place the queue was started from (genre, playlist, artist, …), not the current track's album. |

### F — Player continuation

| Situation | Observable outcome |
|---|---|
| Scroll below the controls | Sections: "Next up" (the next three tracks in actual play order), "More from <artist>", "Other versions" when the track has versions. |
| Swipe down on the artwork | Closes only when the view is scrolled to the top. |
| Play next / add to queue from the player | Inserts after the current *position*, even when the same track appears twice in the queue. |

### G — Personalised Home rankings

| Situation | Observable outcome |
|---|---|
| Listening data exists | Rows "Your artists this month" and "Your labels" from the listening statistics; tapping opens the artist or label. Hidden without data. |

### H — Audio output

| Situation | Observable outcome |
|---|---|
| Native app | The bottom row of the player shows the current output ("Bose QC35 II", "Phone speaker") in the accent colour; tapping opens the system output picker, or Bluetooth settings where no picker exists. |
| Browser | Nothing is shown. |

## Acceptance Criteria

1. With a track that has neither cover nor artist image, the player shows a tinted panel with the title; the MuMa mark is not visible.
2. The player background is tinted for a Hardstyle track and neutral for a track without genre.
3. The mini player renders exactly one image.
4. The player header is not uppercase and offers a ⋮ menu with artist, album, play next, add to queue, details, and lyrics when present.
5. Every genre on the playing track is a chip; the release date is not on the player screen.
6. Home tiles with no tracks show destination-specific copy; five tiles render without an orphan.
7. Browse opens with the category grid visible; the advanced-search entry is beside the search bar.
8. After opening an artist and a label, Browse shows both in a "Recent" row, most recent first.
9. Starting playback from a genre shows that genre's name in the player header.
10. The player scrolls to show the next tracks and more from the artist.
11. On the phone with a Bluetooth headset connected, the player names it and tapping it opens a picker.

## Open Questions / Not Yet Decided

- Whether "Recent" in Browse should also record playback starts (not only opened pages). Decided:
  opened pages only; playback provenance is a separate store used by the header.
- Song-to-set containment ("sets this track appears in") needs backend modelling and is deferred.
- Share and sleep timer are separate features and are not part of the ⋮ menu here.
