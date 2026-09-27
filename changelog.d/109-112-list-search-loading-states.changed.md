- **A genre, label, festival, podcast, year or lineup no longer shows the previous list under its
  name, and search no longer says "No results" before it has asked** (issues #109 and #112,
  `docs/designs/perceived-performance/`). Opening a second genre left the first genre's tracks on
  screen under the new heading until `getSpotifyTracks` answered, and one loading flag shared with
  the collection grids could mark the list done while it was still loading. The list now clears on
  every new place and shows skeleton rows; a filter change on the same list keeps the old rows
  dimmed until the new ones arrive; a failure is a section error with a retry instead of an empty
  "Geen nummers" state. The first page of every list is cached per query for five minutes
  (`trackListCache.js`, stale-while-revalidate, refreshed after one minute), so going back is
  instant, and pressing a genre/label/podcast/festival/year/lineup card starts that list's
  request on pointerdown, one request per press and shared with the page. The search results page
  gives tracks, artists and albums their own skeletons, errors and retries, shows "Zoeken…" while
  any is out, and says "No results" only once all three answered empty. The search dropdown
  says it is searching from the first keystroke (the 300 ms debounce included), keeps the previous
  results dimmed instead of flashing "No results", and offers a retry when `search3` fails. History,
  Starred, Memories and the search "more" modal swap their whole-page "Laden…"/spinner for
  skeleton sections, and Starred, History and the modal show an error with a retry where they
  used to claim there was nothing. The style guide's Loading States section gains the stale-results
  and search-as-you-type rules.

<!-- release notes -->

- Opening a genre, label, festival, podcast, year or lineup no longer briefly shows the previous
  list; going back to one you just saw is instant.
- Search shows that it is searching instead of "No results" while it waits, in the search box and
  on the results page.
- History, Favourites and Memories show placeholders while they load, and a retry button when
  loading fails.
