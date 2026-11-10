# LMS Rating Outbox: Functional Design

## Overview

A rating set in LMS (web player, app, car) is copied to music-manager, which keeps its own copy of
every rating for the dynamic playlists, the mixes and the statistics. LMS sends that copy once. If
music-manager is down at that moment (every deploy, every restart) or answers with an error, the
rating never arrives, and LMS writes one WARNING to its log. Nothing sends it again later: the copy
only ever goes from LMS to music-manager, so a missed rating stays wrong in music-manager until
someone runs `scripts/restore_lms_ratings.py` by hand (issue #222).

Listens had the same problem and got a durable outbox (issue #67,
[lms-listen-outbox](../lms-listen-outbox/functional.md)). Ratings get the same treatment. LMS writes
every rating change for music-manager to a second outbox in its own database first, and the relay
that delivers the listens delivers the ratings too. A rating leaves the outbox only once
music-manager has it.

A rating differs from a listen in one way: only its last state matters. Ten listens of a track are
ten facts, but a track rated 3, then 4, then cleared has one fact left: "no rating". The outbox
keeps one entry per user and rated item, and a new change replaces the waiting one. Teun decided
this on 2026-11-10, together with the separate table and the shared relay.

## User Stories

- As a listener, I want a rating I set during a deploy or a music-manager restart to reach my
  playlists and mixes afterwards, without anyone running a repair.
- As a listener, I want the rating I see in the player to be the one music-manager has, also when I
  changed it a few times while music-manager was down.
- As a listener, I want a rating I cleared to stay cleared in music-manager, also when I cleared it
  during an outage.
- As the administrator, I want to see how many rating changes LMS still holds and since when.
- As the administrator, I want LMS to warn me when it gives up a rating change, and to tell me which
  one, because nothing else will bring it back.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| music-manager is up | A rating change reaches music-manager within a second or two, as now. |
| music-manager is down for a minute (deploy) | Rating changes made in that minute reach music-manager once it is back, usually within a minute. |
| music-manager is down for hours | LMS keeps trying, at most once a minute. Every waiting rating change arrives once it is back. |
| LMS restarts while rating changes wait | They are delivered after LMS comes back. |
| A track is rated 3, then 5, during an outage | music-manager gets 5. It never gets 3. |
| A track is rated 4, then the rating is cleared, during an outage | music-manager gets "cleared". A 4 it had from before the outage is removed. |
| A rating is cleared, then set to 2, during an outage | music-manager gets 2. |
| A track is rated while an earlier change for it is on its way | Both arrive in the order they were made, so music-manager ends with the newer one. |
| The same rating change reaches music-manager twice (the answer to the first try got lost) | Nothing changes the second time. |
| Listens and ratings both wait after an outage | They are delivered together, oldest change first, one at a time. |
| music-manager refuses a rating change as malformed | That change is dropped with a WARNING. The changes behind it still go. |
| music-manager answers "not allowed" (for example during an API key rotation) | The changes wait until the key is fixed. None is dropped for this. |
| More than 10,000 rating changes wait, or one has waited 14 days | The oldest are dropped. Each drop is a WARNING that names the user and the rated item. |
| Administrator opens music-manager's `/health` | `lms_rating_outbox` shows, per LMS, how many rating changes wait and when the oldest was made. A waiting change never turns the health check red. |

## Acceptance Criteria

1. A rating set while music-manager is stopped appears in music-manager after it starts again,
   without manual action.
2. A rating cleared while music-manager is stopped is gone from music-manager after it starts again.
3. After several changes to one rating during an outage, music-manager ends with the last one and
   never shows an earlier one in between.
4. A rating change still waiting when LMS restarts is delivered after the restart.
5. Delivering the same rating change twice leaves music-manager as one delivery does.
6. LMS never keeps more than 10,000 waiting rating changes and never keeps one longer than 14 days.
   Each drop is logged as a WARNING with the user and the item.
7. Setting a rating never waits on music-manager. The player stays as responsive during an outage
   as without one.
8. `/health` on music-manager reports the rating outbox's size and oldest entry per LMS, next to the
   listen outbox.

## Open Questions / Not Yet Decided

- The limits. This design uses the listen outbox's numbers: 10,000 changes, 14 days, a retry at
  most once a minute. A listen has a second way back (music-manager's backfill reads LMS's listen
  table), and a rating does not. A dropped rating stays wrong until
  `scripts/restore_lms_ratings.py export-lms` and `import-muma` run. One row per user and item
  keeps the table small, so a longer age limit (or none) costs little. The age limit is there so
  that one change music-manager keeps answering with a server error cannot block every listen and
  rating behind it for good. Proposed: keep 14 days. Teun to confirm.
