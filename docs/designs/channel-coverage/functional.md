# Channel Coverage — Functional Design

See [docs/designs/README.md](../README.md) for the design-doc process this document follows. This is the
functional (user-observable) half; the implementation contract is in [technical.md](technical.md). The
sibling feature for record labels is [label-catalog-coverage](../label-catalog-coverage/functional.md).

## Overview

The downloader follows about 1.100 SoundCloud accounts and 280 YouTube channels. Every account has a
backlog of older tracks that the ordinary sweep never reaches, and since the deep sweep
(see [downloader/functional.md](../downloader/functional.md), "The deep sweep") that backlog is being
worked off — but nothing shows how far along it is. The deep sweep already counts, per account, how
many tracks the platform lists, how many we hold, how many were deliberately written off and how many
are still to fetch; those numbers are only written to the log.

This feature stores that count as a per-account **snapshot** and shows it in the management UI, so
the owner can see for every channel how complete it is, when the last track came in, and whether the
downloader is still making progress on it.

## User Stories

- As the collector, I want to see per channel how many of its tracks I hold (`309 van 1030`), so
  that I know how complete each channel is.
- As the collector, I want to see how many tracks per channel are still to be fetched, and when the
  last one arrived, so that I can tell whether the backlog is actually being worked off.
- As the collector, I want a source-wide summary — how many channels are complete, how many still
  have a backlog, how many were never counted, how many tracks came in recently — so that I can judge
  whether the downloader is doing its job without reading logs.
- As the collector, I want to see how many tracks were written off, and why, so that a channel that
  looks "complete" because everything failed does not pass unnoticed.

## Functional Flows

### Where the numbers come from

| Situation | Observable outcome |
|---|---|
| A deep sweep pass finishes for an account, in full or cut short (cap or rate limit) | The account's snapshot is updated: listed, held, excluded, remaining, when, and whether the pass finished. |
| An ordinary (probe-only) check runs | The snapshot is not touched; only "last checked" moves. |
| The platform listing itself fails | The previous snapshot stays as it was. "Last checked" shows the attempt. |
| An account has never been deep-swept | It shows as "nog niet geteld" (not counted yet), with no percentage. |

### What the management page shows

Under **Beheer → Downloaders** a new sub-tab **Volledigheid** with a source switch (SoundCloud /
YouTube).

| Element | Content |
|---|---|
| Summary tiles | Channels counted / configured, complete, with a backlog, tracks remaining in total, tracks fetched in the last 7 and 30 days, current backoff state. |
| Write-offs | A breakdown per reason (too short, too long, unavailable, failing, failed) for the source. |
| Channel table | One row per channel (YouTube: per channel *and* download type): a bar showing held / excluded / remaining over listed, the numbers as text, percentage held, last download, last check, snapshot age and whether that pass finished. |
| Filter and sort | Search by name; filter "onvolledig" (remaining > 0), "nog niet geteld", "compleet"; sort on remaining (default), percentage, name, last download. |

### Wording

- "Held" is what the download archive records, which is not the same as a playable file still being
  in the library. The page says *gearchiveerd*, not *in bibliotheek*.
- "Excluded" is what the downloader decided not to fetch under the current settings (duration bounds,
  retry window). A widened duration filter brings tracks back, so the number is a snapshot, not a
  verdict.
- The page gives **no finish date**. Accounts are checked on a cadence that depends on their upload
  age, and a rate limit slows every account at once; any ETA computed from recent throughput would be
  wrong in a way that looks precise. It shows what is left and what came in recently instead.

## Acceptance Criteria

1. After a deep sweep pass on an account, the Volledigheid tab shows that account's listed, held,
   excluded and remaining counts and the time of the pass.
2. A pass that stops at the download cap or on a rate limit still updates the counts and is marked as
   not finished.
3. An account that has never been deep-swept is listed as "nog niet geteld" and counted in the tile
   for that.
4. The summary tiles agree with the table: complete + with backlog + not counted = configured.
5. The table can be filtered to only channels with a backlog and sorted by remaining, most first.
6. Each SoundCloud row shows the time of the newest archive entry; each YouTube row does so for
   entries archived after this feature shipped, and shows "onbekend" before that.
7. The write-off breakdown lists every reason with its count for the selected source.
8. No estimated completion date is shown anywhere.

## Open Questions / Not Yet Decided

- Whether "held" should later be reconciled with the library (archive row present but file gone).
  Deferred: a different question, needs the library join.
- Whether a listing failure should be recorded as its own snapshot state. Deferred: the previous
  snapshot plus "last checked" already tells the story; a `failed` state would need a place to store
  the error.
- Whether the Overview tab should carry one tile for this. Deferred until the Volledigheid tab has
  been used for a while.
