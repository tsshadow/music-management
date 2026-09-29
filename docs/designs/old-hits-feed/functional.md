# Oude hitjes — Functional Design

## Overview

A new personal feed, **"Oude hitjes"** ("Oude favorieten die je minder draait"), for old songs the
listener used to love or play a lot and has not heard in a while. It sits next to the daily mixes:
on the web and phone Home shelf, on the phone's "Daily mixes" page, and in the car's "Daily mixes"
folder. Like the daily mixes it holds 100 tracks, stays the same all day, changes the next day, and
continues with "Meer laden".

Teun asked for it after the daily mixes turned out to favour recent releases: an old anthem he
rated five stars in 2024 never comes back unless he searches for it. Measured on production
(2026-09-29): 1,607 rated tracks, 702 old ones with 4-5 stars, and 929 old tracks played three or
more times of which 584 not in the last six months. Many old tracks have neither a rating nor a
listen (the listen history only starts in 2024), so a third source of "this was a hit" comes from
outside: the artist's top tracks on Deezer (and on Last.fm when a key is configured).

## User Stories

- As a listener, I want a list of my old favourites I have not heard in a while, so that I
  rediscover them without searching.
- As a listener, I want the old tracks I used to play a lot to come back after a long silence, even
  when I never rated them.
- As a listener, I want the well-known old hits of artists I like to show up, even when I never
  rated or played that particular track.
- As a listener, I never want a track I rated 1 or 2 stars, a track I played last month, or a
  new release in this list.
- As the owner, I want every threshold adjustable on the config page without a release, and the
  external lookups to send nothing but artist names.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| Open Home (web or phone) | An "Oude hitjes" card appears after the five daily mixes, with its subtitle. |
| Tap the card | A feed page with up to 100 tracks, favourites, much-played tracks and known hits taking turns. |
| Open it again later the same day | The same list in the same order. |
| Open it the next day | A different selection and order; the stalest favourites are most likely near the top. |
| A track in the list was played (any version) in the last 90 days | It is not in the list. |
| A track is rated 1 or 2 stars | It is never in the list. |
| A song exists in several versions (remix, edit, compilation rip) | It appears once, as its canonical version. |
| One artist has many old favourites | At most three of their songs are in the list. |
| The listener has no ratings and no listens at all | The feed says there is not enough data yet. |
| The listener excluded an artist, label or genre from their profile | Tracks of it are left out, as in the other feeds. |
| "Meer laden" at the bottom | More tracks follow, no song repeated. |
| In the car, open "Daily mixes" | "Oude hitjes" is listed last, directly playable. |
| No Last.fm key configured | The feed still works, with Deezer alone as the external source. |

## Acceptance Criteria

1. "Oude hitjes" is listed by `GET /api/feeds` and shown on Home, the phone's "Daily mixes" page
   and the car's "Daily mixes" folder, titled "Oude hitjes" with subtitle "Oude favorieten die je
   minder draait".
2. Every track in it was released more than three years ago (by the earliest known date of any
   version of the song; see the technical design for undated songs).
3. No track in it is rated 1-2 stars, and no song in it was played in the last 90 days.
4. About 40% of the places go to own 4-5 star songs, about 30% to songs played at least three
   times but not in the last six months, and about 30% to known hits by artists the listener rates
   or plays. A group that runs short hands its places to the next.
5. One version per song, at most three songs per artist.
6. The list is the same all day and differs from day to day.
7. The thresholds (age, rest days, six-month silence, play count, shares, per-artist cap, version
   count) are settings in the "Feeds" group of the config page; the external lookup can be
   switched off there.
8. Only artist names are ever sent to Deezer or Last.fm.

## Open Questions / Not Yet Decided

- Whether the card should get a colour and icon of its own rather than the name-derived colour of
  the rotating mixes. Deferred: it uses the existing palette until the style guide says otherwise.
- The tier shares and thresholds are the requested defaults, not measured ones; revisit after a
  few weeks of use.
