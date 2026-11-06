# Feed length — Functional Design

GitLab issue #83.

## Overview

Every generated feed (Release Radar, the classic daily mix, the three spectrum mixes Zachter /
Middenin / Harder, the artist mix and the label mix) held 30 tracks. That is two hours at best and
often under one: Teun asked (2026-09-26) for "standaard 100 tracks of een search more knop". This
change does both. A feed is 100 tracks by default, the length is a Management setting, and a listener
who reaches the end of a feed can ask for more of the same day's feed — on the feed page with a
"Meer laden" button, and in the player without doing anything: a queue started from a feed tops
itself up before it runs out.

Measured on production for user `user` on 2026-09-26, live builds at 30 and at 100:

| Feed | Candidates | At 100 | Build time at 100 |
|---|---|---|---|
| Release Radar | 131 | 100 | 4.1 s (4.1 s at 30) |
| Klassiek (`daily-mix`) | 1835–2180 | 100 | 4.7 s |
| Zachter | 546–685 | 100 | 4.7 s |
| Middenin | 502–624 | 100 (3 filled from unknown hardness) | 22.1 s |
| Harder | 247–321 | 100 (1 filled from unknown hardness) | 22.6 s |
| Artiestmix | 0–2 | 0–2 | 0.4 s |
| Labelmix | 3 | 3 | 0.2 s |

Five of the seven reach 100 on their own. The artist and label mixes were short for a reason that
has nothing to do with the length (they picked an entity with too few playable tracks — issue #77,
bug report 110, fixed in develop just before this change: only a name with at least 15 playable
songs is drawn, the window widens to find them, and the artist mix is not capped per artist). An
artist mix therefore holds as many of that artist's songs as qualify, up to the feed length; its
per-artist cap follows the length. One default for every feed is enough; there is no per-feed
length. (The artist and label numbers above were measured on production before #77 deployed.)

## User Stories

- As a listener, I want a daily mix to last an afternoon, so that I do not have to pick the next
  thing after half an hour.
- As a listener at the end of a feed, I want "more of this", so that a good mix does not just stop.
- As the admin, I want to change the length without a release, so that I can shorten it again if
  the nightly refresh gets too slow or lengthen it if 100 is still too few.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| A listener opens a feed page (web or app) | Up to 100 tracks (the configured length), in the feed's own order. |
| The listener scrolls to the end of the list | A "Meer laden" button under the list. Tapping it appends the next tracks of the same feed; none of them is a song already in the list. |
| The feed has nothing more to give | The button is gone. |
| The listener presses play on a feed (page or Home card) and listens to the end | Shortly before the last track the queue grows by the next page of the same feed, without a tap. When the feed is exhausted the queue simply ends, as before. |
| The listener starts something else (an album, a search) | That queue never grows with feed tracks. |
| The admin changes "Feed length" in Management > Configuration → Feeds | The next time a feed is opened it is rebuilt at the new length; today's stored feeds are not served any more. |
| Android Auto | The feed folders list the configured length (100) instead of 30, never more than 100. |
| The driver plays a feed in the car ("Alles afspelen" or a tapped track) and listens on | Shortly before the last track the car's queue grows by the next page of the same feed, as on the web (issue #84). |

## Acceptance Criteria

1. With no setting changed, every feed that has enough candidates holds 100 tracks.
2. The "Feed length" setting exists in Management under Feeds, accepts 10–200, and anything else falls
   back to 100.
3. "Meer laden" appends tracks that are not already in the list; repeated taps never show a song
   twice on the same day.
4. A queue started from a feed is extended before it runs out; a queue started anywhere else never is.
5. The same page asked for twice on the same day holds the same tracks.

## Open Questions / Not Yet Decided

- ~~Android Auto's own "play all" plays the (now 100-track) list but does not continue past it.~~
  Resolved by issue #84: the car's feed queue tops itself up too (technical.md, "Continuation in
  Android Auto").
