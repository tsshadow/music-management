# Library Browser — Functional Design

## Overview

The management UI currently has three overlapping views onto the same collection. **Library** lists tracks
with a search box and pagination. **Stats** shows collection-wide totals and top-10 lists. **Advanced
Library** was meant to be the powerful one — facet filters, an inspector panel, distribution charts — but it
has never worked against real data.

Two independent defects explain that. The track query selects five columns (`musical_key`, `energy`,
`danceability`, `valence`, `popularity`) that do not exist in the production database, so the endpoint
returns HTTP 500; the frontend does not check the response status and renders the failure as "No tracks
found". Separately, the genre facet reads `library_track_genres`, a table that has zero rows because nothing
in the codebase has ever written to it. Beyond those two, large parts of the page are placeholder content
that was never wired up: the key/Camelot grid, the mood buttons, the vocals checkboxes, the audio-feature
bars, the lyrics panel, the tag chips, three dead metadata checkboxes, and both distribution charts, which
render hardcoded arrays.

This design replaces the three views with one Library Browser built only on data the library actually holds,
and adds the missing write path that gives genre real coverage. The aggregation behind the charts is exposed
as a reusable analytics API so a later player page can ask the same questions about a single artist without
reimplementing anything.

## User Stories

- As a library owner, I want to filter my collection by genre, label, artist, BPM range and release year at
  the same time, so that I can find cross-sections such as "Frenchcore on Footworxx above 190 BPM".
- As a library owner, I want the distribution charts to reflect my current filter, so that selecting a genre
  immediately tells me how its BPM and release years are spread.
- As a library owner, I want to see how much of my collection actually has BPM, genre and artist data, so
  that I know how much to trust a distribution before drawing conclusions from it.
- As a library owner, I want genres in the browser to match what my files and LMS show, so that the browser
  and my player do not disagree about what a track is.
- As a library owner, I want to see which genres are still awaiting curation, so that the browser doubles as
  a signal of how much curation work is outstanding.
- As a library owner, I want to re-run parsing or re-download a track from the browser, so that fixing a
  track does not require switching to another view.
- As a library owner, I want one place to browse the library, so that I stop guessing which of three views
  answers a given question.

## Functional Flows

### Browsing and filtering

| Situation | Observable outcome |
|---|---|
| Opening the Library Browser | Full collection, newest first, with a header showing the number of tracks, artists, labels and genres in view plus the data-coverage percentages |
| Ticking a genre in the sidebar | Track list and every chart narrow to that genre; header counts and coverage update |
| Combining genre, label and a BPM range | Filters intersect — a track must satisfy all of them to appear |
| Typing in the artist field | Matching artist names appear as suggestions; picking one adds it as a removable chip |
| Selecting several artists | Tracks by any of the selected artists appear |
| Typing in the search box and pressing Enter | Free-text match against title, artist and label, combined with any active facets |
| Entering a number between 50 and 300 in the search box | Treated as a BPM search, matching tracks within 2 BPM |
| Clicking a bar in the top-artists or top-labels chart | That artist or label is added to the filter |
| A filter combination matching nothing | "No tracks match these filters" with a control to clear them, and empty charts — not an error |
| The server failing to answer | An explicit error message naming the failure, never an empty result presented as success |
| Clearing all filters | Returns to the full collection |

### Genre

| Situation | Observable outcome |
|---|---|
| A track whose file tag holds an approved genre | Appears under that genre's curated name, so `uptempo` is listed as `Uptempo Hardcore` |
| A track whose file tag holds a genre still awaiting curation | Appears under the genre's raw name, grouped in the sidebar under "Awaiting curation" |
| A track whose file tag holds a rejected genre | That genre is not shown and not filterable; the track still appears under its other genres, or as having none |
| A track with several genres in its tag | Appears under each of them |
| A genre approved or rejected in the curation page after the fact | Reflected in the browser after the next scan of the affected files |

### Analysis

| Situation | Observable outcome |
|---|---|
| Switching to the analysis view | Genre distribution, BPM histogram, release-year histogram, top artists and top labels, all for the current filter |
| Reading the BPM histogram | Raw detected values, with a visible note that tempo detection misreports half and double time, so peaks around 150-160 and 190-200 are partly artefacts |
| Filtering to a set with little analysed audio | Coverage indicator shows the low percentage, so a thin histogram is not mistaken for a thin collection |

### Inspecting and acting on a track

| Situation | Observable outcome |
|---|---|
| Selecting a track | Inspector shows title, artist, label, genres, BPM, release year, duration, date added, file path and, when known, the source URL |
| A field the library does not hold | Omitted, not shown as a zero or a placeholder |
| Re-running the parse for a track | Confirmation, then a message that the scan has started |
| Re-downloading a track | Confirmation, then a message that the download has started; if no source URL is on file, an explanation instead |

### Navigation changes

| Situation | Observable outcome |
|---|---|
| Looking for the old Library or Stats tabs | Gone; the Library Browser replaces both |
| Looking for scrobble totals, match rate, unmatched listens, recently added tracks, or the artist-images action | Moved to the Overview tab, where the other system-health figures already live |
| Reading the popular-genres list on Overview | Counts come from the genres tracks actually carry, so they change from today's figures, which are derived from machine-learning predictions |

## Acceptance Criteria

1. Opening the Library Browser lists tracks from the real collection, with no view or filter driven by
   placeholder data.
2. Genre, label, artist, BPM range and release year can each be used as a filter, and combining them narrows
   the result to tracks satisfying all of them.
3. The genre sidebar lists genres that tracks actually carry, each with its track count, and separates
   approved genres from those awaiting curation.
4. Selecting several artists shows tracks by any of them; selecting several genres shows tracks in any of
   them.
5. Every chart in the analysis view reflects the active filter, and changing a filter updates all of them.
6. The header shows what share of the tracks in view has BPM, genre and artist data.
7. The BPM histogram shows detected values without correction, alongside a note explaining half and
   double-time misdetection.
8. A failed server request produces a visible error naming the failure; an empty result is only shown when
   the server genuinely returned no tracks.
9. A track whose file tag carries an approved genre is listed under that genre's curated name.
10. A track whose file tag carries a rejected genre is not listed under it, and that genre cannot be
    selected as a filter.
11. The inspector shows only fields the library holds for that track, and omits the rest.
12. Re-run parse and re-download work from the inspector and report their outcome.
13. The Library and Stats tabs are gone, and every figure they showed is either in the Library Browser or on
    the Overview tab.
14. After a full forced scan, the share of tracks with at least one genre matches the share whose files carry
    a genre tag.

## Open Questions / Not Yet Decided

- BPM half and double-time misdetection is a data-quality problem in the analyzer. This design shows the raw
  values and names the problem in the UI; correcting it at the source is separate work.
- Musical key, mood, vocal type, energy, danceability, valence, popularity and lyrics have no data behind
  them and are removed rather than faked. Key in particular cannot be derived from what is stored:
  `mean_chroma` is a single scalar averaged over all twelve pitch classes, so recovering key would require
  re-analysing the audio. Out of scope here.
- Machine-learning genre predictions in `library_track_ml_labels` are excluded, from the browser and from the
  popular-genres figures on Overview. The model is early, too heavy for the server, and not yet accurate
  enough to present alongside curated genres. The predictions stay in the database for later ML work.
- The dynamic-playlist preview in the web UI will match more tracks once genres are indexed, because it
  currently falls back to those same ML predictions. Accepted: the preview sees little use, and the seeded
  default playlists it was built around are being retired separately.
- The collection has no album concept — there is no album table, and the old Stats tab reported a hardcoded
  zero. Album browsing is not part of this design.
- Ratings exist for 21 tracks, too few to be worth a facet. Revisit once ratings see real use.
