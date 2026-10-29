# Cover art for playlists in the app and the car: Functional Design

## Overview

The web UI shows a collection as images. Every playlist, album and artist has a cover, and the user
recognizes a row by its picture before reading the text. The Android app and Android Auto show the same
collection as text rows with a generic icon. In the car this costs the most. A list of fifteen text lines
takes more glances than a grid of four tiles.

This feature gives every browsable entry a cover. Where no existing image exists (a genre, a festival, a
stage), the app generates one from the name. That way one image system serves the web, the phone and the
car. The color of Hardstyle is the same everywhere.

The feature is split into five steps that are released separately. Steps 1, 2 and 3 are delivered. Step 4
(the phone strips) and step 5 (real festival images) are still open.

## User Stories

- As a listener, I want to see my genres as tiles with images in the car, so that I can choose with one
  glance instead of reading a list.
- As a listener, I want to recognize a festival by its own color and name, so that Defqon.1 Red and
  Defqon.1 Blue are not two nearly identical text lines.
- As a listener, I want to recognize a DJ by their portrait, so that I find the right one faster in a long
  artist list.
- As a listener, I want a playlist without its own cover to still look like something, instead of the
  empty music-staff icon.
- As a driver, I want tracks to stay a list, so that I do not have to search forty titles in a grid.

## Functional Flows

| Situation | Observable result |
|---|---|
| The user opens a level in the car whose entries have cover art (albums, artists) | Android Auto draws a grid with images instead of a text list |
| The user opens a level in the car whose entries have no cover art (the A to Z index of artists) | The level stays a list. No empty tiles appear |
| The user opens the main menu in the car | Stays a list. Those entries carry a menu icon, not cover art |
| The user opens a track list or a set | Stays a list, even if every track has a cover |
| An album page contains a "More" entry without its own image | The page stays a grid. That one entry does not pull it back to a list |
| The user opens a genre level in the car | Each genre carries a cover that the app draws itself from the name and color. The level becomes a grid as a result |
| An artist has no portrait | The cover falls back to initials on the color of the artist's genre. The artist list therefore stays a grid |
| An artist has a portrait | The portrait wins. Nothing is drawn over it |
| MuMa is unreachable while the car browses | The covers keep the colors fetched last. If nothing was fetched yet, they use the neutral color |
| A genre that MuMa does not know (new in a tag) | Neutral color. No empty tile |

## Acceptance Criteria

1. In Android Auto, the album list appears as a grid with cover art, not as a text list.
2. In Android Auto, the artist list appears as a grid once the artists have an image.
3. The A to Z index, which the artist list falls back to above 100 artists, stays a list.
4. The main menu in the car stays a list.
5. Tracks and sets stay a list, regardless of their cover.
6. No level in the car leaves the layout to the car's default. Each level says for itself what it wants to
   be.
7. The same genre name gives the same color on the web and in the app.
8. A genre in the web UI carries the color that MuMa sends. A genre that MuMa does not know keeps the brand
   color the card always had.

## Open Questions / Not Yet Decided

- Which festivals have image material that is really usable, and may it be used? Until that is settled,
  the generated cover is the end product, not an intermediate step.
- Do playlists and tiles get a drawn cover too? Not at the moment. There is no cover family for "a
  playlist". Inventing one would fill the grid with tiles that say nothing. Their level stays a list.
- Should the main menu in the car become a category grid with its own icons? That needs icons that read as
  a tile. The current monochrome vectors do not.

## Related Docs

- [`mockup.html`](mockup.html): the three cover families and the screens, as a page you can open in a
  browser
- [`technical.md`](technical.md)
