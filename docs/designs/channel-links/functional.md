# Channel Links — Functional Design

See [docs/designs/README.md](../README.md) for the process. This is the user-observable half; the
implementation contract is in [technical.md](technical.md). It builds on
[channel-coverage](../channel-coverage/functional.md), which introduced the channel as its own thing,
and borrows its review flow from the label proposals of the importer (Beheer → Labelvoorstellen).

## Overview

Since 0.70.0 every file that arrived through SoundCloud, YouTube or Telegram is filed under a
*channel* (the account it came from), instead of under the platform as if that were a record label.
A channel is usually an artist or a label wearing the platform's clothes — `Traxtorm` on SoundCloud
is the label Traxtorm, `D-Sturb` is the artist D-Sturb — but the system does not know that: every
channel starts out pointing at neither.

This feature proposes those links where the names leave no doubt, and gives the curator one place
to confirm or reject each proposal. A confirmed link is shown wherever channels are shown (the
Volledigheid table under Beheer → Downloaders). Nothing is linked without a human saying yes.

Measured read-only on production on 2026-09-25 (1.377 channels: 1.112 SoundCloud, 264 YouTube,
1 Telegram; none linked):

| Candidate | Channels |
|---|---|
| Name equals an approved artist, exactly one | 708 |
| Name equals several approved artists (`Dr. Peacock` vs `Dr Peacock`, `Dr.Peacock`, ...) | 18 |
| Name equals a known label | 149 (114 SoundCloud, 35 YouTube); one of them equals two labels |
| Name equals a curator's artist redirect (`#PLVRZR`, `D - Fence` → `D-Fence`) and no approved artist directly | 23 |
| Name equals both a label and an artist (`Monstercat`) | 35 |

Roughly 860 of the 1.376 SoundCloud/YouTube channels (about 60 %) get at least one proposal; the
rest have a name that matches nothing strongly (`Djkronosofficial`, `A-KRIV Official Profile`,
`Hysta Official`) and get none. The counts were taken with SQL that approximates the name key
(punctuation to spaces, case- and accent-insensitive comparison); the real key is computed in
Python and may differ by a handful.

## User Stories

- As the curator, I want the system to suggest which label or artist a channel is, so that I do not
  have to type 1.400 links by hand.
- As the curator, I want to confirm or reject each suggestion, so that nothing is linked on a guess.
- As the curator, I want a rejected suggestion to stay rejected, so that I only ever decide it once.
- As the collector, I want to see in the channel table which label or artist a channel belongs to,
  so that the table reads as music rather than as account names.

## Functional Flows

### What counts as a proposal

| Situation | Observable outcome |
|---|---|
| The channel's name, ignoring case, accents, punctuation and spacing, equals one approved artist | One artist proposal ("naam"). |
| It equals a label the library knows | One label proposal ("naam"). |
| It equals both | Two proposals, one of each kind; they are decided independently. A channel may be linked to a label *and* an artist. |
| It equals several approved artists (or labels) and exactly one of them is spelled exactly like the channel apart from capitals | A proposal for that one. |
| It equals several and none (or more than one) is spelled exactly like it | No proposal. A guess between spellings is not strong. |
| It matches no approved artist directly, but equals an alias recorded on an artist's edit page | An artist proposal for that artist ("alias"). |
| It equals a spelling the curator redirected to an approved artist (artist curation, black + rewrite) | An artist proposal for the target ("redirect"). |
| It only resembles a name (`Hysta Official` vs `Hysta`, a substring, a different word order) | No proposal. |
| The name is an artist still in the curation queue, or a rejected artist | No proposal: only approved artists count. |
| The channel already has a link of that kind | No new proposal of that kind. |
| The channel is a Telegram channel | Not considered. |

### Where the proposals come from

| Situation | Observable outcome |
|---|---|
| The curator presses **Voorstellen zoeken** on the Koppelingen tab | Every SoundCloud and YouTube channel is compared again. New proposals appear; the tab reports how many were added, how many open ones no longer hold and were withdrawn, and how many channels were skipped as ambiguous. |
| The same button is pressed twice in a row | The second run adds nothing and withdraws nothing. |
| An open proposal no longer holds (the artist was rejected, the label renamed, or the channel was linked another way) | It is withdrawn ("verouderd") and leaves the list. |
| A proposal was rejected earlier | It never comes back, however often the search runs. |

### Deciding

Under **Beheer → Downloaders** a new sub-tab **Koppelingen**, next to Volledigheid.

| Element | Content |
|---|---|
| List | One row per open proposal: platform, channel name, the proposed label or artist, the kind (label / artist), why it was proposed (naam / alias / redirect) and how many tracks the channel holds. Filter on kind and platform, search on name. |
| Bevestigen | Links the channel to the proposed label or artist. The row leaves the list. |
| Afwijzen | The row leaves the list and the proposal never returns. |
| Clicking twice, or two tabs deciding the same row | The second click changes nothing and is not an error. |
| The proposed label or artist was deleted since | The proposal is withdrawn instead of confirmed, and the tab says so. |

### Where a link is shown

| Situation | Observable outcome |
|---|---|
| Volledigheid table, a channel linked to a label and/or artist | A "Gekoppeld aan" column shows the label and/or artist name. |
| A channel with an open proposal | The column shows "voorstel", which opens the Koppelingen tab. |
| A channel that was never downloaded into a folder yet | The column stays empty: the table cannot tell which channel folder the account writes to until it has written one. |
| A wrong link was confirmed | "Ontkoppelen" in the column removes it; the proposal that led to it counts as rejected from then on. |

## Acceptance Criteria

1. With production's data, pressing Voorstellen zoeken produces proposals for roughly 860
   channels, and none for a channel whose name only resembles a label or artist.
2. Confirming a proposal makes the label or artist appear in the Volledigheid table for that
   channel, after a refresh of the table.
3. A rejected proposal does not come back after pressing Voorstellen zoeken again.
4. Pressing Voorstellen zoeken twice in a row adds nothing the second time.
5. A channel whose name equals several differently spelled artists gets a proposal only when one of
   those spellings is exactly the channel's, capitals aside.
6. A plain listener sees the proposals but cannot confirm, reject, search or unlink; that takes the
   rule-management permission, as label proposals do.

## Open Questions / Not Yet Decided

- **Linking by hand.** A channel with no proposal cannot be linked from this page yet. Deferred: the
  proposals cover most of the value, and a free-text picker is its own design.
- **What a link changes elsewhere.** A link is shown, not used: the tagger does not yet read it
  (e.g. to fill the publisher of a label channel's uploads), and browsing by label does not yet
  include the label's channels. Each is a separate follow-up.
- **Running the search automatically.** It runs when the curator asks. New channels appear only as
  fast as the downloaders follow new accounts, which is a handful a month.
