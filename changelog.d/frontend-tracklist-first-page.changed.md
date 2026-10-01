- **Track lists show their first rows in the time a 50-row answer takes, whatever the page size.**
  The songs and sets lists, genres, labels, podcasts, festivals, years, lineups and search asked
  the whole page (up to 500 rows) in one `getSpotifyTracks` call; on production a 200-row page
  took 1.3 s idle and 12-17 s while LMS scanned. The first request now asks 50 rows and the rest of
  the page follows behind them, with versions folded across both; a revisit shows the whole page
  from the cache. Leaving a list for a page that is not a track list now aborts its request too,
  so it no longer holds an LMS connection the next page needs.
<!-- release notes -->
- Track lists show their first rows much sooner, also while the library is being scanned.
