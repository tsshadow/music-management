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
| `liveset` | A recording of a performance at an event | Ten minutes or longer, and in `Livesets/` or `Telegram/`, or naming a known festival in its title (or in its path together with a year); under `EPs/` the festival counts only when the title or folder also says "live" or "DVD" |
| `podcast` | An episode of a radio show or podcast series | Ten minutes or longer, and in `Podcasts/` or naming an approved show |
| `interview`, `preview` | Not music: an interview, the preview of an event DVD | The title, at any length. See [non-music-forms](../non-music-forms/functional.md) |

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

**The label tree is the exception** (bug report 109). Under `EPs/<label>/` titles name festivals
all the time without being recordings of one: "Radium - Decibel Dictature" is a track, and
"Defqon.1 2015 Mix 1 (Mixed by Ran-D)" is the label's mix album for that edition -- a `set`, as the
table says. What the real recordings among the label releases have in common is that they say so:
"Live at Reverze 2009", "The Live Registration", a DVD rip, a `..._Live-STREAM` rip. So under
`EPs/` a festival name makes a live set only together with the word "live" (or "liveset") or
"DVD" in the title or the folder; otherwise the file is a `set`. On production this moved about
310 files from live set to set and kept 32 as live sets.

A track whose length is unknown gets no form. It still shows up in every list that does not filter
on form.

## The performance date

A live set that names a festival and a year, where the festival has an edition date for that year
(Management > Festivals), gets that date as its performance date. Every other track has none.

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
| Android Auto, Sets tab, **Soort** | Sets & mixes / Live sets / Podcasts, each a folder like a genre's: play all, shuffle, recently added, by year, then the tracks |
| Android Auto, Soort > Live sets > By year > 2012 | Live sets played in 2012 (performance year), as on the web |
| "Speel livesets van Defqon 2019 af" (car, microphone or text) | Defqon.1 live sets played in 2019. "Dj sets" asks for sets & mixes, "podcasts" for podcasts; a bare "set" still means any long track |
| "Speel de podcast van KTRA af" / "speel de laatste aflevering van Monstercat af" | The episodes of that show (Keeping The Rave Alive, Monstercat Podcast), newest first; a name that is no show plays all podcasts |
| Preset builder in sets mode | A **Soort** select (All / Sets & mixes / Live sets / Podcasts); the preset keeps it, on the web and in the car |
| "Save as preset" from the sets view with Soort set | The preset keeps the Soort |

### On the phone: Android Auto, voice and presets

Issue #47. The native paths
now ask the same question the web sets view asks.

- **Android Auto**: the Sets tab gets a **Soort** row next to Podcasts and Festivals. The three forms
  are a fixed list -- never read from the server -- so the car can only ever send a form LMS knows.
- **Voice**: "livesets" / "live sets" ask for live sets, "djsets" / "dj sets" for sets & mixes,
  "podcasts" for podcasts. A bare "set" names no form: people say it of a festival recording as
  often as of a released mix, so it keeps meaning every long track. "Van Defqon" after a set word
  is read as the festival when no artist of that name exists.
- **A podcast show by name** (issue #88):
  "speel de podcast van KTRA af", "play the Monstercat podcast", "speel de laatste aflevering van
  Monstercat af" play that show's episodes, newest first. "Aflevering" / "episode" ask for the
  podcast form just as "podcast" does. The name is matched against the shows the library has
  episodes tagged under (`PODCAST`) and, through the podcast curation, their aliases ("KTRA" for
  Keeping The Rave Alive); a longer name that contains the spoken one is also found ("Darkside" for
  Twisted's Darkside Podcast), and a tie goes to the show with the most episodes. A named show
  replaces the podcast form rather than adding to it, so an episode downloaded in the last hour --
  not yet classified -- still plays. A name that matches no show changes nothing: the request plays
  podcasts, as before. A genre named without a keyword stays a genre ("speel hardstyle podcasts af"
  is the podcasts within Hardstyle), and only a show name the library lists is ever sent.
- **Presets** store the form (`form` in the preset JSON, sets presets only) and play it everywhere.

**The year next to a form** is the filing year -- a live set's performance year -- because that is
what "live sets from 2012" means. It is only used together with a form, and only for one year;
everywhere else (songs, a bare "sets", several years) the year keeps its tag-year meaning, so no
existing list, preset or spoken request changes its answer.

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

- ~~Android Auto, voice and saved presets did not know the form~~ -- wired in issue
  #47, see "On the phone" above.
- ~~A spoken **podcast name** was not matched against the `PODCAST` tag~~ -- done in issue
  #88, see "On the phone" above.
- A show named without any podcast word ("speel KTRA af") is not tried as a show: that would cost
  every ordinary request an extra lookup, and a bare name keeps finding the track of that name.
- The year picker lists the years the files carry. A year that exists only as a performance date
  is not in that list (rare: the tagger already writes the edition date into the file's date when
  it knows it).
