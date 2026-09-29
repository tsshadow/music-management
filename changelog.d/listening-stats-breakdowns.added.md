- **Listening statistics by genre and release year, with filters.** The statistics page now shows
  your most played genres and a release-year chart (per year or per decade, tracks without a usable
  date in their own "Onbekend jaar" bar), and every panel -- totals, timeline, clock, sources, top
  tracks/artists/labels and the two new ones -- can be narrowed to one or more genres and/or years:
  pick genres in the filter bar (your own genres, most played first), type a from-to year range, or
  tap a bar in either chart to toggle it. Several genres mean any of them; a genre and a year must
  both hold. The filter is in the URL, so a view can be bookmarked or shared. A track with several
  genres counts for each, and the genre panel says the bars overlap. Genre and year are only known
  for a linked track, so a filter excludes every listen that was never matched to the library; the
  page says how many right under the filter instead of silently shrinking the totals. API:
  `GET /api/listening/top-genres`, `GET /api/listening/years`, and the parameters `genre`, `year`
  (a year or `unknown`), `year_from`, `year_to` on every `/api/listening/*` endpoint, which also
  report `excluded_unmatched` (docs/designs/listening-stats/). No schema change.

<!-- release notes -->

- **Listening statistics by genre and year.** New charts for your most played genres and the
  release years of what you played, and filters for genre and year that apply to the whole page --
  tap a bar to filter on it. Listens that were never linked to a track cannot have a genre or year,
  so the page tells you how many fall outside a filter.
