# Memories — Functional Design

## Overview

Memories surfaces music from the library by the calendar: "today, X years ago". It is the same idea Google
Photos and Immich use for pictures, applied to release dates — on 2 August you see what was released on (or
around) 2 August in earlier years, grouped per year.

The feature is for the everyday listener using either client. It gives the library a reason to resurface
tracks that are neither new nor favourited, which no existing view does: Release Radar only looks forward at
what is recent, and Songs/Albums are browsing tools that require you to already know what you want.

This first iteration is driven entirely by **release date**, read from the `DATE`/`ORIGINALDATE` tags that
the library already carries. Two follow-ups are explicitly out of scope here and will be designed
separately: enriching missing release dates from MusicBrainz/Discogs, and a second kind of memory based on
when a track was first listened to. The screen is laid out so that a second kind of memory becomes an extra
group alongside the release groups, without redesigning it.

## User Stories

- As a listener, I want to see which tracks in my library were released on today's date in earlier years, so
  that I rediscover music I would not have searched for.
- As a listener, I want to play a whole year's worth of those tracks in one tap, so that a memory turns into
  listening instead of browsing.
- As a listener opening the home screen, I want a short preview of today's memories, so that I notice them
  without navigating anywhere.
- As a listener who finds the preview distracting, I want to switch it off, so that my home screen stays the
  way I like it.
- As a listener on a day with no exact matches, I want to see near-miss releases from the same week instead
  of an empty screen, so that the feature stays worth opening.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| Tracks exist whose release date is exactly today in earlier years | Memories shows one group per year, newest year first, headed "Today, X years ago" with the year and the number of tracks |
| No exact match today, but releases fall within three days either side | The same groups appear, headed "This week, X years ago", so the wording never claims a precision the data does not have |
| A year has both exact and near-miss tracks | The group is headed "Today, X years ago"; the exact matches are listed first |
| Neither exact nor near-miss matches exist | Memories shows a short explanatory empty state; the home preview is hidden entirely rather than shown empty |
| User taps a year group | The tracks of that year play, in the order shown |
| User opens Memories on web | One tile per year, newest first: a mosaic of that year's covers, the year, its heading, the three best-loved tracks and a play action |
| User opens a tile on web | That year gets its own page at `/memories/<year>`, listing the first fifty tracks with a "load more" that reveals fifty at a time |
| User opens `/memories/<year>` on a later day | The page shows whatever that year holds on that day, or an empty state saying the year has no memories today |
| User taps a card in the home preview | On web, that year's page opens; on Android, the full Memories screen opens scrolled to that year |
| User turns the home preview off in settings | The preview disappears from home; Memories itself stays reachable from its permanent place — the sidebar on web, the Library tab on Android |
| Tracks only carry a year, or a year and month, in their tags | They never appear in Memories, because "today X years ago" cannot be established from them |
| A track was released earlier this same year on today's date | It does not appear; a memory is always at least one year old |
| The server does not provide memories (older or non-LMS server) | Both clients behave as if there are no memories: no preview, no error message |

## Acceptance Criteria

1. On a date where the library contains a track whose release date is exactly that day-and-month in an
   earlier year, Memories lists that track under a group headed with the correct number of years ago.
2. Groups are ordered from the most recent year to the oldest.
3. On a date with no exact matches but with releases up to three days before or after, those tracks are
   shown and the group heading says "this week", not "today".
4. A group's heading says "today" whenever at least one track in it matches the date exactly.
5. Playing a group starts playback of every track in that group, in the displayed order.
6. Tracks whose tags carry only a year, or only a year and month, never appear.
7. Releases from the current calendar year never appear.
8. Both the web UI and the Android app show the same groups for the same date. The layout differs: web
   shows a tile per year that opens its own page, Android lists the years as sections on one screen.
9. The home preview shows one card per year group, at most ten cards, so it stays a short strip; opening a
   card opens that year.
10. Switching the home preview off in settings hides it, and the setting survives restarting the app or
    reloading the page.
11. With the home preview switched off, Memories is still reachable in both clients without changing any
    setting back.
12. When there is nothing to show, the home preview is absent rather than present-and-empty.
13. A device in a different time zone than the server sees memories for the device's own local date.
14. A web tile names the three tracks of its year that the listener values most: favourites first, and
    listen count deciding both within the favourites and among the rest. That ordering is the server's, so
    the three are the best of the whole year rather than the best of the page the client happens to hold.
15. A web year page shows fifty tracks at a time; the whole year plays from its play action, not just the
    part on screen.
16. A count shown next to a year is the size of that year, not the size of the page the client was sent.
17. In a year where nothing is rated or played -- which is most of them -- the tracks shown first are the
    ones from an actual label release, ahead of the ones ripped from a platform.

## Open Questions / Not Yet Decided

- Measured on the production library on 2026-08-23: day-precision release dates are common enough that a
  single day yields around 3.600 tracks across nineteen years, but they sit almost entirely on the platform
  rips. Of 1.091 rated tracks only 305 carry one, and none of those fell inside that day's window; the
  listen table knows 356 tracks, likewise none. So the rating and listen keys rarely decide anything today,
  and the release key carries the ordering. Both the MusicBrainz/Discogs enrichment and the scrobble
  matching would change that, and neither is designed here.
- A second kind of memory ("first listened to on this day") is agreed as a follow-up and deliberately not
  designed here, beyond keeping the screen and the response shape able to carry more than one kind of group.
- Enriching missing release dates from MusicBrainz/Discogs is a separate design.
