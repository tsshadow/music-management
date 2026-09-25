# Track form and performance date — Functional Design

## Overview

MuMa's reason to exist is the filter: "hardstyle from 2012", and live sets as first-class material
(see [product-goal.md](../../product-goal.md)). Two things stood in the way.

- **Form was not a field.** Whether a file is a track, a set, a live set or a podcast episode could
  only be guessed from the folder it sits in or from its length. The songs/sets switch in the app
  splits on ten minutes, so "only live sets" or "sets, but not podcasts" could not be asked at all.
- **A live set had only its release date.** The product goal says a live set is filtered on the day
  it was played. The library held a single date, so a Defqon.1 2012 recording uploaded in 2016 filed
  under 2016.

This feature gives every track a **form**, and every live set whose festival edition is known a
**performance date**, and makes both usable as filters — in the web UI and on the phone, which run
the same interface.

## The forms

| Form | Meaning | How MuMa decides |
|---|---|---|
| `track` | A single song | Shorter than ten minutes, wherever it sits |
| `set` | A released DJ set or mix (Warm Up Mixes, a long SoundCloud upload, a label's mix album) | Ten minutes or longer and none of the below applies |
| `liveset` | A recording of a performance at an event | Ten minutes or longer, and in `Livesets/` or `Telegram/`, or naming a known festival in its title (or in its path together with a year) |
| `podcast` | An episode of a radio show or podcast series | Ten minutes or longer, and in `Podcasts/` or naming an approved show |

Decided against a separate `mix` form. The product goal treats released sets and mixes identically
(both filter on their release date), and no rule can tell a "mix" from a "set" in a long SoundCloud
upload — a distinction no filter asks for and nothing can fill is a value that stays empty. `Top 100`
is not a form either: on production all but one of its ~900 files are the individual tracks of the
countdown, and the short files under `Podcasts/` are the same (unmixed Top 40 tracks), which is why
length is decided first.

The rules are the ones the tagger already applies: the same ten-minute threshold, the same festival
and podcast lists (`rules_festivals`, `rules_podcasts`), matched the same way. A curator adding a
festival alias, an edition date or approving a show changes the form and performance date of the
matching files within the hour, without touching a single file.

A track whose length is unknown gets no form. It still shows up in every list that does not filter
on form.

## The performance date

A live set that names a festival and a year, where the festival has an edition date for that year
(Beheer > Festivals), gets that date as its performance date. Every other track has none.

The year filter then reads, per the product goal:

| Material | Date the year filter uses |
|---|---|
| Tracks, released sets and mixes, podcasts | Release date |
| Live sets | Performance date, falling back to the release date |

## User Stories

- As a listener, I want to pick "Live sets" in the sets view, so that I hear festival recordings and
  not the weekly radio show.
- As a listener, I want "2012" to give me the sets played in 2012, so that a recording uploaded years
  later is not missing from its year.
- As the curator, I want to see a festival edition date I enter take effect on the library without a
  retag or a rescan.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| Sets view, open the new **Soort** chip | Options: All, Sets & mixes, Live sets, Podcasts |
| Pick "Live sets" | Only live sets are listed; the chip reads "Live sets" and can be cleared |
| Songs view | No Soort chip — every song is a track; the chip would only offer one real choice |
| Year 2012 with "Live sets" | Live sets played at a 2012 edition, plus live sets without a known edition released in 2012 |
| Year filter on songs | Unchanged: release year |
| A track MuMa has not classified yet (just downloaded) | Not in a Soort-filtered list until the next hourly pass; in every unfiltered list as before |
| Curator adds the 2013 date for Defqon.1 | Within an hour the 2013 Defqon.1 live sets carry that performance date |

## Acceptance Criteria

1. The sets view offers a Soort filter with All / Sets & mixes / Live sets / Podcasts, on the phone
   and in the browser.
2. Picking a form lists only tracks of that form; clearing it lists all sets again.
3. A live set tagged with a festival and year whose edition date exists is found under the year of
   that date, even when its release date is a different year.
4. A track (under ten minutes) is never classified as a set, live set or podcast.
5. Adding an edition date or festival alias updates the affected tracks without retagging files.
6. Deploying this does not block on a library-wide migration.

## Open Questions / Not Yet Decided

- **Android Auto and voice** still browse by the ten-minute LENGTH switch. The server accepts
  `form` on `getSongs` from this change on, so they can follow without another server release;
  wiring them is recorded in [open-work.md](../../open-work.md).
- **Saved presets** do not store the form yet; a preset saved from the sets view restores the sets
  view without it. Same entry in open-work.
- The year picker lists the years the files carry. A year that exists only as a performance date
  is not in that list (rare: the tagger already writes the edition date into the file's date when
  it knows it).
