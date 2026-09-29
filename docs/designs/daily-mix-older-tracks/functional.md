# Daily mixes with older tracks — Functional Design

Bug report [131](../../bug-reports/131-daily-mixes-only-contain-this-year.md). Extends
[feeds](../feeds/functional.md) ("Daily mixes v2 — the spectrum").

## Overview

Every daily mix drew only from releases of the last 90 days, so on 2026-09-29 Klassiek, Zachter,
Middenin and Harder were 96–100 % tracks from 2026. Teun: "otherwise I might as well pick 'uptempo
this year'". The daily mixes now mix the new with the older part of the library, still chosen on the
listener's own taste. Release Radar stays the feed for what is new.

## User Stories

- As a listener, I want half of each daily mix from the last year and half from before, so a daily mix
  is not a second Release Radar.
- As a listener, I want the older half to leave out what I rated 1 or 2 stars, and to prefer what I
  have not played lately, so it is rediscovery rather than repetition.
- As an admin, I want the share, the "recent" window and the older half's minimum rating as settings,
  so the balance can be tuned without a release.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| The listener opens Klassiek, Zachter, Middenin, Harder or the label mix | About half the tracks were released in the last 12 months, about half before that |
| An older song is rated 1 or 2 stars by the listener | It never appears in the older half |
| An older song is rated 3–5 stars, or not rated at all | It can appear, heard before or not |
| An older song was played last week | It can still appear, but much less often than one untouched for half a year |
| An older song does not match the listener's artists, labels or genres | It does not appear |
| One half has too few songs (a thin band, a small label) | The other half fills the places, so the mix keeps its length |
| A song has no known release date | It does not appear in the older half (as before, it appeared in no daily mix) |
| The listener opens Release Radar or the artist mix | Unchanged |
| An admin changes one of the three settings | Today's mixes are rebuilt on their next read |

## Acceptance Criteria

1. With default settings a full daily mix (Klassiek, the three hardness mixes, the label mix) holds
   50 % tracks released within the last 365 days and 50 % released earlier, give or take the
   per-artist cap.
2. No track the listener rated 1 or 2 stars appears in the older half.
3. When either half runs short, the mix is filled from the other one.
4. Release Radar and the artist mix are unchanged.
5. The share (0–100 %), the recent window (days) and the older minimum rating (1–5) are settings in
   Beheer → Config, group Feeds; a change takes effect on the next read.

## Open Questions / Not Yet Decided

- An "old hits" feed (favourites from years ago) is a separate design Teun is still working on; it is
  deliberately not part of this change.
- Songs without an agreed release date (~30 % of the library) stay out of the daily mixes. Whether a
  rip should inherit the year of its official version is a release-date question, not a feeds one.
