# Library Search and Sort (Android) — Technical Design

Implements [`functional.md`](functional.md).

Two apps change together: the Subsonic API in `services/music-management-server` (the LMS fork) and
the Android client in `services/ultrasonic`. Per AGENTS.md rule 7 they ship in the same change.

## Data Model

No schema change. Everything needed already exists in the database:

- `Artist::FindParameters` carries `keywords` (name *and* sort name are matched) and an
  `ArtistSortMethod`, of which `SortName`, `TrackCountDesc`, `AddedDesc` and `Random` are
  implemented in `src/libs/database/impl/objects/Artist.cpp`.
- `ReleaseSortMethod` implements `Name`, `ArtistNameThenName`, `DateDesc`, `AddedDesc`,
  `StarredDateDesc` and more.

Two sort methods are added to the enums in
`src/libs/database/include/database/objects/Types.hpp`:

| Enum | New value | Ordering |
|---|---|---|
| `ArtistSortMethod` | `ReleaseCountDesc` | `COUNT(DISTINCT r_a_l.release_id) DESC, a.sort_name`, joining `release_artist_link` |
| `ReleaseSortMethod` | `TrackCountDesc` | `COUNT(t.id) DESC, r.sort_name`, joining `track` |

Both follow the shape of the existing `ArtistSortMethod::TrackCountDesc` case: the join is added in
`createQuery` under the same condition list, and the `orderBy` in the sort switch. A `GROUP BY` is
already present for the aggregate cases.

One helper is added: `Track::getCount(Session&, const Track::FindParameters&)`, mirroring the
existing `Release::getCount` overload. It backs the per-artist track count in the response.

## API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /rest/getArtists.view` | existing `musicFolderId`, `offset`, `count`; **new** `query` (string, optional), **new** `sortBy` (enum, optional) | `artists` node as today, with a new `songCount` attribute per `artist` | Unknown `sortBy` → falls back to `name` and is logged; it is not an error response. Empty `query` is treated as absent. |
| `GET /rest/getAlbumList2.view` | existing `type`, `size`, `offset` | unchanged | **New accepted `type` value** `byTrackCount`. `alphabeticalByArtist` already works today. |
| `GET /rest/search3.view` | existing `query`, `albumCount`, `albumOffset`, `artistCount`, `artistOffset`, `songCount` | unchanged | unchanged |

`sortBy` values and their mapping:

| `sortBy` | `ArtistSortMethod` |
|---|---|
| `name` (default) | `SortName` |
| `trackCount` | `TrackCountDesc` |
| `albumCount` | `ReleaseCountDesc` (new) |
| `added` | `AddedDesc` |
| `random` | `Random` |

`query` is split on whitespace and passed to `FindParameters::setKeywords`, which is what
`search3` already does for artists — so "angerfist" and "anger fist" behave the same way in both
endpoints.

### Grouping by first letter

`handleGetArtistsRequest` groups artists into index nodes by the first character of their sort
name. That grouping is meaningful only for `name`. For every other `sortBy`, and whenever `query`
is set, the handler emits a single index node with `name="#"` holding the artists in server order.
The client flattens index nodes into one list (`toArtistList`), so the order survives; no client
change is needed for this.

### `songCount` on the artist node

`createArtistNode` (`src/libs/subsonic/impl/responses/Artist.cpp`) already computes `albumCount`
per artist with a note that it is "not very efficient". `songCount` is computed the same way, via
the new `Track::getCount` overload with `setArtist(artist->getId())`.

This adds one count query per artist in the response, so it is measured before merging: the target
is that `getArtists.view?count=100` stays under 300 ms on production data. If it does not, the
attribute is computed only when `sortBy=trackCount` is requested, and the client shows the track
count only in that order. The fallback is a response-shape difference, not an API change.

`songCount` is an addition to a response, so older clients are unaffected.

## Client Design (services/ultrasonic)

### The header

`FilterButtonBar` is extended rather than replaced: it already owns the sort dropdown and the
grid/list toggle, is already styled, and is already wired to fragments through
`FilterableFragment`. A second row is added to `filter_button_bar.xml`: a `TextInputLayout` with a
search icon and a clear button, hidden unless the fragment asks for it.

- `ViewCapabilities` gains `supportsSearch: Boolean = false`.
- `FilterableFragment` gains `fun setQuery(query: String?) {}`.
- The 300 ms debounce lives in `FilterButtonBar`, so no fragment repeats it. The bar emits the
  trimmed term, or `null` when it is empty.

`ArtistListFragment` and `FilterBrowseFragment` switch from their current layouts to
`list_layout_filterable`, which already includes the bar. `AlbumListFragment` already inflates that
layout when `byArtist` is set; the condition becomes "always" (`AlbumListFragment.kt:183`).

### Query state

A plain class `LibraryQuery` (in `fragment/`, next to the fragments, testable without Robolectric)
holds `query: String?`, `sortOrder: SortOrder` and `offset: Int`, and answers one question: given a
change (new term, new order, scrolled to the end), what should be loaded next and does the list
reset to the top? Changing the term or the order resets `offset` to 0 and clears the list;
scrolling appends. Both list models own an instance; nothing is written to `Settings`, so the tabs
cannot leak state into each other.

### Artists

`SortOrder` gains `BY_TRACK_COUNT("trackCount")`, `BY_ALBUM_COUNT("albumCount")` and
`BY_ADDED("added")`; `BY_NAME` and `RANDOM` already exist. `MusicService.getArtists` grows
`query: String?` and `sortBy: String?` parameters, threaded through `RESTMusicService`,
`CachedMusicService` and `OfflineMusicService`:

- `RESTMusicService` passes them to `API.getArtists`, which gains the two `@Query` parameters.
- `CachedMusicService` only caches the unfiltered, name-sorted first page — a cache keyed on every
  term is worthless and would grow without bound. Any call with a `query` or a non-default `sortBy`
  goes straight to the network.
- `OfflineMusicService` filters and sorts its cached artists in memory for `query`, `name` and
  `trackCount`; for the orders it cannot answer offline it throws `OfflineException`, which the
  existing handler turns into the "not available offline" message.

`ArtistRowBinder` shows `albumCount` and the new `songCount` under the name.

### Albums

Browsing keeps using `getAlbumList2` through `AlbumListModel.getAlbums`. Searching switches the
model to `search3` with `albumCount`/`albumOffset` for paging, so browse and search are two sources
feeding one list, chosen by whether a term is set. `SortOrder.BY_TRACK_COUNT` maps to the new
`byTrackCount` type; `BY_ARTIST` maps to `alphabeticalByArtist`, which the server already accepts.

### Browse tabs

`FilterBrowseFragment` loads its whole list in a single call, so search and sort are in-memory.
A pure function `filterAndSortCards(cards, query, order)` does both: name match on a normalized key
(lowercased, diacritics stripped — the same normalization the web UI uses for genre search), and
sorting by name or by the count already on the card. No network call, no server change.

## Cross-App Impact

- `services/music-management-server`: new `query`/`sortBy` parameters and `songCount` attribute on
  `getArtists.view`, new `byTrackCount` album list type, two new sort methods, one new
  `Track::getCount` overload.
- `services/ultrasonic`: header, query state, service-layer parameters, row layout.
- `services/frontend` and `services/music_manager`: no change. The web UI has its own search and
  does not call `getArtists.view`.

Both server and client changes are additive, so a new client against an old server degrades to
"search returns everything, sort falls back to name" rather than failing — but they still ship
together, per AGENTS.md rule 7.

## Technical Acceptance Criteria

1. `getArtists.view?query=angerfist` returns only artists matching the keyword, and the same query
   with two keywords ("anger fist") returns the same artist.
2. `getArtists.view?sortBy=trackCount` returns artists in descending track count, `sortBy=albumCount`
   in descending album count, `sortBy=added` newest first, and an unknown value falls back to name
   order with a log line rather than an error.
3. When `query` is set or `sortBy` is not `name`, the response contains exactly one index node and
   the artists in it are in server order.
4. Every `artist` node in `getArtists.view` carries a `songCount` attribute equal to the number of
   tracks linked to that artist.
5. `getAlbumList2.view?type=byTrackCount` returns albums in descending track count.
6. Database tests cover `ArtistSortMethod::ReleaseCountDesc` and `ReleaseSortMethod::TrackCountDesc`
   against a fixture with known counts, including ties, which are broken by sort name.
7. `LibraryQuery` unit tests: a new term resets the offset and clears the list; a new sort order
   does the same; scrolling appends without clearing; the same term set twice does not trigger a
   reload.
8. `filterAndSortCards` unit tests: matches ignore case and diacritics, sorting by count is
   descending with name as tie-breaker, and an empty query returns the input order.
9. A `FilterButtonBar` test asserts the search row is hidden when `supportsSearch` is false and
   visible when it is true.
10. `./gradlew :ultrasonic:testDebugUnitTest` and the server's existing test target both pass.
11. `getArtists.view?count=100` against production-sized data stays under 300 ms; if not, the
    `songCount` fallback described above applies.

## Related Docs

- [docs/designs/library-browser/](../library-browser/) — the Library tabs this header is added to
- [docs/bug-reports/023-android-artist-page-blank.md](../../bug-reports/023-android-artist-page-blank.md)
  — the artist destination these lists navigate to
