# Tapping an Artist in the Android App Opens a Blank Page

# status: fixed

# reported problem
In the Android app (Ultrasonic), artists do not show an artist page: tapping an artist in the
artist list leaves you on an empty screen.

# Possible reason
Not a server problem. The Subsonic side was never involved: `getArtists` clearly works, since the
list the user taps on is populated by it, and `getAlbumsOfArtist` is exercised by the search
results and the player's "show artist" menu item, both of which do open a working artist screen.

The failure is in the app's navigation. Three things pointed at the same destination:

1. `ArtistListFragment.onItemClick` navigated an `Artist` (not an `Index`) to
   `NavigationGraphDirections.toArtistDetail(...)`.
2. `HomeCardNavigator.directionsFor` did the same for `HomeCardType.ARTIST`, so the home screen's
   artist cards and recently-played artists went to the same place.
3. That destination, `artistDetailFragment` in `navigation_graph.xml`, resolved to
   `org.moire.ultrasonic.fragment.ArtistDetailFragment`, which was a stub: a bare
   `Fragment()` with no layout, no `onCreateView`, and no data loading — only a `splitDiscography`
   helper. A fragment with no view renders nothing, which is exactly the reported blank page.

The stub and the navigation to it were both present from the initial import of the app into this
repository, so no artist page was ever shown from the artist list; the working paths (search,
player) simply took a different route.

# solution
Point every entry into an artist at the screen that already works — `AlbumListFragment` with
`byArtist = true` — and delete the stub so the dead destination cannot be wired up again by
accident.

- New `org.moire.ultrasonic.fragment.ArtistNavigation` holds the destination in one place:
  `directionsFor(ArtistOrIndex)` for the artist list (an `Index` still opens its folder contents)
  and `directionsForArtist(id, name)` for callers that only have the id and title. It passes the
  same arguments `SearchFragment` and `PlayerFragment` already pass
  (`AlbumListType.SORTED_BY_NAME`, `size = 1000`, `byArtist = true`).
- `ArtistListFragment.onItemClick` and `HomeCardNavigator` now call it. Recording the artist in
  `RecentActivityStore` is unchanged.
- `ArtistDetailFragment.kt`, the `artistDetailFragment` destination, the global `toArtistDetail`
  action and the unused `artistListToArtistDetail` action are removed. `AlbumExtensions`
  (`isEP`/`isSingle`) is kept — it is unit tested and is what a real discography page would build
  on.

A dedicated artist page that splits the discography into albums, EPs and singles (what the stub was
presumably meant to become) remains open work; this change only makes tapping an artist show that
artist's albums.

# tests
- `services/ultrasonic/ultrasonic/src/test/kotlin/org/moire/ultrasonic/fragment/ArtistNavigationTest.kt`
  — asserts an artist navigates to `R.id.toAlbumList` with `byArtist = true` and the artist's id
  and name, that an artist card on the home screen reaches the same destination, and that an
  `Index` still navigates to `R.id.toTrackCollection`. The first two fail against the old code,
  which produced the blank `artistDetailFragment` destination.
- Full module suite: `./gradlew :ultrasonic:testDebugUnitTest` — 136 tests, 0 failures.
- `./gradlew :ultrasonic:assembleDebug` builds, confirming the removed navigation destination left
  no dangling Safe Args references.
