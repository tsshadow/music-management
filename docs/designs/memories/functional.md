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
| User taps a card in the home preview | The full Memories screen opens, scrolled to that year |
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
8. Both the web UI and the Android app show the same groups for the same date.
9. The home preview shows one card per year group, at most ten cards, so it stays a short strip; opening a
   card opens the full screen at that year.
10. Switching the home preview off in settings hides it, and the setting survives restarting the app or
    reloading the page.
11. With the home preview switched off, Memories is still reachable in both clients without changing any
    setting back.
12. When there is nothing to show, the home preview is absent rather than present-and-empty.
13. A device in a different time zone than the server sees memories for the device's own local date.

## Open Questions / Not Yet Decided

- How many of the library's tracks actually carry day-precision release tags is unknown: the development
  databases are empty, so it could not be measured during design. If the number turns out to be small, the
  feature is thin until the MusicBrainz/Discogs enrichment lands. This affects how useful the feature is on
  day one, not how it is built.
- A second kind of memory ("first listened to on this day") is agreed as a follow-up and deliberately not
  designed here, beyond keeping the screen and the response shape able to carry more than one kind of group.
- Enriching missing release dates from MusicBrainz/Discogs is a separate design.
