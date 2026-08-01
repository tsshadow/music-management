# Library Search and Sort (Android) — Functional Design

## Overview

The Library tab in the Android app lists artists, albums, genres, years, festivals, lineups and
ratings. None of those lists can be searched, and only the album list that belongs to a single
artist offers a sort order. With roughly 50.000 artists in the library, finding one means scrolling
through pages that load 100 at a time, so an artist whose name starts with a late letter is in
practice unreachable.

This feature puts one header on top of those lists: a search field and a sort selector. Searching
an artist by name works over the whole library, not only over the part that happens to be loaded.
Sorting offers the orders that are actually useful per list — by name, but also by how much music
there is behind an entry.

## User Stories

- As a listener, I want to type "angerfist" above the artist list and see that artist immediately,
  so that I do not have to scroll through 50.000 names.
- As a listener, I want to sort artists by number of tracks, so that the artists I have most music
  from are on top instead of the ones starting with an "A".
- As a listener, I want to see how many albums and tracks an artist has in the list, so that the
  sort order is verifiable rather than mysterious.
- As a listener, I want to search and sort the album list the same way, so that the Library tabs
  behave alike.
- As a listener, I want to filter the genre, year, festival, lineup and rating tabs by name, so
  that picking one does not mean scanning a grid.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| Opens Library → Artists | Header with a search field ("Zoeken") and a sort selector. The list is sorted by name, as today. |
| Types "angerfist" in the artist search | After a short pause the list shows the matching artists from the whole library, not only the loaded pages. Scrolling loads more matches. |
| Clears the artist search | The full list returns, in the sort order that was selected. |
| Picks "Aantal nummers" as artist sort order | The list reloads from the top, artists with the most tracks first. The search term, if any, stays applied. |
| Reads an artist row | Shows the artist name plus how many albums and tracks that artist has. |
| Opens Library → Albums | Same header. Sort orders: name, artist, year, recently added, most played, highest rated, number of tracks. |
| Types in the album search | The list shows matching albums from the whole library; scrolling loads more. |
| Opens Library → Genres / Years / Festivals / Lineups / Ratings | Same header. Search filters the cards by name as you type; sorting offers name and count. |
| Switches from Artists to Albums and back | Each tab keeps its own search term and sort order for as long as the screen is open. |
| Searches while offline | The search field reports that search needs a connection; the list keeps showing what is cached. |
| A search matches nothing | The list shows an empty state naming the term that was searched for, with the search field still filled so it can be corrected. |

## Acceptance Criteria

1. The Artists, Albums, Genres, Years, Festivals, Lineups and Ratings tabs each show a header with
   a search field and a sort selector.
2. Searching for "angerfist" on the Artists tab returns that artist even when the list has only
   loaded the first 100 names.
3. The artist sort selector offers: name (A-Z), number of tracks, number of albums, recently added,
   and random. Choosing one reloads the list from the top and keeps any active search term.
4. Each artist row shows the number of albums and the number of tracks for that artist.
5. The album sort selector offers: name, artist, year, recently added, most played, highest rated,
   and number of tracks.
6. Searching on the Albums tab returns albums that are not in the currently loaded page.
7. On the Genres, Years, Festivals, Lineups and Ratings tabs, typing filters the visible cards by
   name without a network call, and the sort selector offers name and count.
8. Search terms and sort orders are per tab; switching tabs does not carry one tab's term into
   another.
9. A search that returns nothing shows an empty state, not a blank list.
10. With no connection, searching reports that it is unavailable rather than silently returning
    nothing.

## Open Questions / Not Yet Decided

- Whether the search term should survive leaving and re-entering the Library screen. Decided for
  now: it does not — the term lives as long as the screen does.
- Whether the sort order should be remembered per user across app restarts. Deferred; the current
  behaviour (default order on each start) is kept.
- Showing the track count per artist costs one count query per artist in the response. If that
  turns out to be too slow on the real library, criterion 4 narrows to "the track count is shown
  when the list is sorted by number of tracks". This is decided by measurement during
  implementation, not up front.
