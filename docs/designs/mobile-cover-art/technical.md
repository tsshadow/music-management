# Cover art for playlists in the app and the car: Technical Design

Implements [`functional.md`](functional.md).

## Data Model

No schema change. The tint is derived from the genre name and is not stored. Storing it would create a
second source of truth that can drift from the derivation.

## API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/library/genres` | none | rows `{genre, state, count, tint}` | 401 without an API key; 500 if the database is unreachable |

`tint` is new and additive: a `#rrggbb` string next to the existing fields. Existing consumers ignore the
field. This is not a breaking change.

The color comes from `services/music_manager/genre_tint.py`. The genres this collection carries are in a
short table. Hardstyle deserves the orange of the festivals it comes from, and that is not a hash result.
Everything outside the table is derived from the name with blake2b. Do not use `hash()`: CPython salts
string hashing per process, so the same genre would get a different color after every restart.
Saturation and brightness are fixed. So the genre name in near-black stays readable over the tint, whatever
tint comes out.

### Who reads it

- **Web UI**: `src/lib/genreTints.js` fetches the list once and attaches the tint to the genre items that
  come from Subsonic's `getGenres`. `getGenres` has no color. This join is why the web UI does not need to
  know the colors itself.
- **App**: `MumaAPIDefinition.getLibraryGenres()`, cached by `GenreTintCache` for one hour. The media
  browser must answer within the caller's deadline. One network call per browse level would make a list
  wait while someone is looking at it. A failed fetch keeps what was already there. The car is exactly
  where MuMa is least reachable, and an empty grid is worse than an old one.

Neither client has its own table. That is the whole point. Hardstyle orange in one client and magenta in
the other is invisible until both are open side by side, and it cannot be tested from either side.

## How Android Auto draws a level

The car decides the layout **per level, not per item**. So the hints travel on the `LibraryParams` of the
level, not on the items:

| Extra | Value | Meaning |
|---|---|---|
| `android.media.browse.CONTENT_STYLE_BROWSABLE_HINT` | `1` = list, `2` = grid | layout of the browsable children |
| `android.media.browse.CONTENT_STYLE_PLAYABLE_HINT` | `1` = list, `2` = grid | layout of the playable children |

The keys come from `androidx.media.utils.MediaConstants`. That library is not on the classpath. The values
are fixed, so they were copied in as literal constants, the same way `BROWSER_SEARCH_SUPPORTED` already was.

**Without these hints, the car mostly ignores the artwork URI of browsable items.** So rendering cover art
without setting the hint makes no visible difference. That is why step 2 comes before step 3.

## The rule

`contentStyleParams(items)` in
`services/muma-mobile/app/src/main/kotlin/nl/teunschriks/mumamobile/service/androidauto/ContentStyle.kt`
decides over the whole list:

- **A browsable level becomes a grid** as soon as at least one browsable child carries cover art.
- **Cover art is not the same as an icon.** A URI with the scheme `android.resource` is a vector from the
  APK. The main menu carries those, and they do not count. As a tile, such a vector is a small glyph on an
  empty surface. The name that tells the entries apart then gets less room than it does in a list.
- **One cover is enough.** An album page past the first one adds a browsable "More" entry with no image of
  its own. That one entry must not pull the page back to a list. That is exactly where the collection is
  largest.
- **Playable always stays a list.** A grid of forty tracks costs the driver more glances than forty rows.

The rule reads the items itself. So levels that get cover art in step 3 (genres, festivals) become a grid
automatically. No list of media ids has to be maintained.

## Where it is connected

Step 4 sits in `HomeCardAdapter`. `HomeCardArt.kindFor(card)` decides whether a card gets a drawn cover, and
the same three families apply as in the car. A card for which the server does have an image keeps that
image. A kind without a cover family (label, year, playlist) keeps its icon. The color comes from
`AppGenreTints.cache`, one cache for the whole app. Two caches would open a window in which the car and the
phone disagree about Hardstyle.

- `MediaLibraryBase.itemListResult(items)` builds the answer with its params. All 27 places in
  `MediaLibraryBrowser` that returned `LibraryResult.ofItemList(..., null)` now pass through it, and so does
  `emptyResult`. A level can therefore no longer forget them.
- `searchableRootParams` sets list/list as the global fallback, next to the existing search claim. The car
  uses that for everything that does not go through `itemListResult`.

## Cross-App Impact

Step 2: none. Only `services/muma-mobile`.

Steps 1 and 3 touch `music-management-server` (the tint next to the genre name) and `frontend` (which uses
the same tint instead of its own table). They ship at the same time as the app.

## Technical Acceptance Criteria

1. `contentStyleParams` returns `CONTENT_STYLE_GRID_ITEM` when a browsable item has a `content://` URI as its
   artwork.
2. `contentStyleParams` returns `CONTENT_STYLE_LIST_ITEM` when no browsable item has artwork.
3. `contentStyleParams` returns `CONTENT_STYLE_LIST_ITEM` when the only artwork is an `android.resource://`
   URI.
4. One item with artwork among browsable items without artwork returns `CONTENT_STYLE_GRID_ITEM`.
5. The hint for playable items is always `CONTENT_STYLE_LIST_ITEM`, even when those items carry artwork.
6. Artwork on a playable item does not change the browsable hint.
7. An empty level returns `CONTENT_STYLE_LIST_ITEM`.
8. `browser.getChildren(...)` for the main menu returns a result with non-empty `params`, with
   `CONTENT_STYLE_LIST_ITEM` as the browsable hint.
9. `searchableRootParams` sets both hints to `CONTENT_STYLE_LIST_ITEM` and keeps `BROWSER_SEARCH_SUPPORTED`.

Covered by `ContentStyleTest` and `SearchableRootParamsTest` in
`services/muma-mobile/app/src/test/kotlin/nl/teunschriks/mumamobile/service/androidauto/`.

## Still to build

| Step | What | Status |
|---|---|---|
| 1 | Tint per genre from the server, and a renderer that draws a cover from name, kind and tint | **Delivered** |
| 2 | Content-style hints | **Delivered** |
| 3 | Artwork URI on browsable items in `MediaLibraryBrowser` | **Delivered** for genres and artists |
| 4 | Home strips on the phone made cover-first, like the web UI | **Delivered** for genres, festivals and artists |
| 5 | Link the festival family (B) to real festival images where they exist and may be used | Open |

Step 3 deliberately does not touch **playlists and tiles**. They are browsable and have no image, so their
level stays a list. A fourth cover family for "a playlist" does not exist in the design. Inventing one to
fill the grid would replace the list with tiles that mean nothing. The festival family is built and tested,
but no browse level in the car shows festivals yet. That comes with step 5.

## Related Docs

- [`functional.md`](functional.md)
- [`mockup.html`](mockup.html)
