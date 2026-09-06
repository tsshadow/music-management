# Listening Statistics — Functional Design

## Overview

MuMa has recorded listens since 2024-03-28 and has never shown them back. `/history` lists them one
by one; nothing counts them. This design covers the page that does: what was played, when, how
often, and where from — the thing stats.fm is for a Spotify account, on a collection MuMa already
owns.

The reason this is a design and not a one-liner is that the recorded history is not what a reader
will assume it is, in two separate ways, and a page that hides either one is worse than no page.

**Most listens are not linked to a track.** A listen arrives as an artist name and a title; if
neither matches the library it lands in a second table and never becomes a track. On production on
2026-09-06 that is 33.461 listens against 20.299 linked ones — 62% of the history. A background
worker keeps retrying and recovers roughly 17% of what it tries, so the gap narrows slowly and never
closes: much of the imported ListenBrainz history is music that was never downloaded.

**Almost nothing recorded how long it played.** Only 876 of the 20.299 linked listens carry a played
duration, and all of them arrived after that was built in August 2026. Every older listen, and every
imported one, knows only that it happened.

So this page counts two populations at once and has to say which is which on every number it shows.

## User Stories

- As the listener, I want to see how much I played over a period, so that the history MuMa has been
  collecting since 2024 becomes something I can read.
- As the listener, I want to know which of those numbers are complete and which are a fraction, so
  that I do not read a top-ten built from a third of my history as my top ten.
- As the listener, I want my top artists and labels, so that I can see what a year of listening
  actually consisted of.
- As the listener, I want to see when I listen — hour of the day, day of the week — in *my* clock,
  not the server's.
- As the listener, I want to see where I listened, so that the phone, the web player and an imported
  history are distinguishable.
- As the listener, I want my history to be mine, so that another account on the same server cannot
  read it.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| The page is opened | Totals, a timeline, an hour-of-day chart and three rankings for the last 12 months |
| A different period is chosen | Everything reloads for that period; the timeline changes its bucket with it |
| The history contains unmatched listens | A prominent notice names the percentage and the count, above the charts |
| Few listens recorded a duration | The same notice says so, and the listening time is labelled an estimate |
| A ranking is shown | It says it covers linked listens only |
| A track carries two labels | It counts for both labels, and the labels panel says so |
| A listen was never linked to a track | It counts in the totals, the timeline, the clock and the sources; it appears in no ranking |
| A listen has no duration anywhere | It contributes no seconds at all, rather than zero seconds |
| The listener is in Amsterdam and played something at 00:30 | It is counted on that day, at that hour — not two hours earlier, in UTC |
| A listen from January and one from July are both at 23:00 UTC | They land in different local hours, because the offset differs by season |
| Nothing was played in the period | The page says so instead of drawing empty charts |
| One panel's request fails | The other panels still render; only that panel is missing |
| The API is unreachable | The page says statistics are unavailable |
| Another user's name is requested | Refused, unless the caller holds the system key |

## Out of Scope

- **Ranking the unmatched listens on their raw text.** They carry an artist and a title, so a
  ranking could be built from them — and would sit next to the real one with different spellings of
  the same artists. Partial inclusion means counting them, not guessing at them.
- **Featured artists.** A ranking counts the primary artist, so one listen counts once. Crediting
  every featured artist is a different metric and needs its own name.
- **A Wrapped page.** The year-in-review in `docs/designs/wrapped/` is a presentation of this data,
  not a second source of it; it can be cut from these endpoints once they exist.
- **Comparing users.** Five accounts is not a social graph.
- **Importing a Spotify export.** Only ListenBrainz can be imported today. Adding Spotify is a
  separate piece of work with its own parser.

## Acceptance Criteria

1. The page shows total listens over both populations, and separately the number that is linked to a
   library track.
2. The unmatched percentage and count are visible without scrolling past a chart.
3. The listening time is labelled as an estimate, alongside the share of listens that measured their
   duration.
4. Every ranking states that it covers linked listens only.
5. Choosing a period reloads every panel, and the timeline's bucket follows the period.
6. Hour-of-day and day-of-week counts are in the reader's timezone, correct on both sides of a
   daylight-saving change.
7. A period boundary is a local midnight, so the last day of a range is whole.
8. An empty history produces an explicit message, not a zero-filled chart.
9. A failing panel does not blank the page.
10. A user's API key can read only that user's history.
