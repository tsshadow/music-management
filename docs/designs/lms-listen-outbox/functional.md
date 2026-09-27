# LMS Listen Outbox — Functional Design

## Overview

Every play LMS records (web player, app, car) is relayed to music-manager, which keeps the shared
listening history, statistics and mixes. Until now that relay was best-effort: while music-manager
was down (every deploy, every restart) or answered with an error for more than about fifteen
seconds, the listens made in that time were lost, and so was anything still waiting when LMS itself
restarted (bug report 075).

Bug report 075 added a safety net in music-manager: a loop that pulls recent LMS-only listens every
15 minutes. Issue #67 asked for the second half: make LMS's relay itself durable. Teun chose it on
2026-09-26 ("Yes add it"). LMS now writes every listen for music-manager to an outbox in its own
database first. It delivers from there, in order, and removes a listen only once music-manager has
it. The pull loop stays, as the net under the net.

## User Stories

- As a listener, I want a play made during a deploy or a music-manager restart to show up in my
  history afterwards, without anyone running a repair.
- As a listener, I want my history in the order I played things, even when several listens arrive
  late at once.
- As the administrator, I want to see how many listens LMS is still holding and since when, so I can
  tell "music-manager is catching up" apart from "something is stuck".
- As the administrator, I want LMS to warn me when it gives a listen up, rather than lose it
  silently.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| music-manager is up | A listen shows up in the history within a second or two, as before. |
| music-manager is down for a minute (deploy) | Listens made in that minute show up once it is back, usually within a minute, with their original play time and in play order. |
| music-manager is down for hours | LMS keeps retrying, at most once a minute. Everything played shows up once it is back. |
| LMS restarts while listens are still waiting | They are delivered after LMS comes back. |
| The same listen reaches music-manager twice (the answer to the first try got lost) | It is counted once. |
| music-manager refuses a listen as malformed | That listen is dropped with a WARNING in LMS's log. The listens behind it still go. |
| music-manager answers "not allowed" (for example during an API key rotation) | The listens wait until the key is fixed. None is dropped for this. |
| More than 10,000 listens wait, or one has waited 14 days | The oldest are dropped with a WARNING. music-manager's pull loop can still recover them from LMS's own listen table. |
| Administrator opens music-manager's `/health` | `lms_listen_outbox` shows, per LMS, how many listens wait and when the oldest was queued. A waiting listen never turns the health check red. |

## Acceptance Criteria

1. A listen played while music-manager is stopped appears in music-manager's history after it
   starts again, without manual action.
2. Listens delivered after an outage keep their original play time and arrive in the order they were
   played.
3. A listen still waiting when LMS restarts is delivered after the restart.
4. Delivering the same listen twice creates one listen in the history.
5. LMS never keeps more than 10,000 waiting listens and never keeps one longer than 14 days. Each
   drop is logged as a WARNING.
6. Recording a play never waits on music-manager. The web player and the app stay as responsive
   during an outage as they are without one.
7. `/health` on music-manager reports the outbox's size and oldest entry per LMS.

## Open Questions / Not Yet Decided

- None. The limits (10,000 listens, 14 days, a retry at most once a minute) are fixed in code. If
  one ever needs changing, it can become a setting then.
