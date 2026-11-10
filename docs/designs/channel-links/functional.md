# Channel Links — Functional Design

See [docs/designs/README.md](../README.md) for the process. This is the user-observable half; the
implementation contract is in [technical.md](technical.md). It builds on
[channel-coverage](../channel-coverage/functional.md), which introduced the channel as its own thing,
and borrows its review flow from the label proposals of the importer (Management > Label proposals).

## Overview

Since 0.70.0 every file that arrived through SoundCloud, YouTube or Telegram is filed under a
*channel* (the account it came from), instead of under the platform as if that were a record label.
A channel is usually an artist or a label wearing the platform's clothes — `Traxtorm` on SoundCloud
is the label Traxtorm, `D-Sturb` is the artist D-Sturb — but the system does not know that: every
channel starts out pointing at neither.

This feature proposes those links where the names leave no doubt, and gives the curator one place
to confirm or reject each proposal. A confirmed link is shown wherever channels are shown (the
Coverage table under Management > Downloaders). Nothing is linked without a human saying yes.

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
| The curator presses **Voorstellen zoeken** on the Links tab | Every SoundCloud and YouTube channel is compared again. New proposals appear; the tab reports how many were added, how many open ones no longer hold and were withdrawn, and how many channels were skipped as ambiguous. |
| The same button is pressed twice in a row | The second run adds nothing and withdraws nothing. |
| An open proposal no longer holds (the artist was rejected, the label renamed, or the channel was linked another way) | It is withdrawn ("verouderd") and leaves the list. |
| A proposal was rejected earlier | It never comes back, however often the search runs. |

### Deciding

Under **Management > Downloaders** a new sub-tab **Links**, next to Coverage.

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
| Coverage table, a channel linked to a label and/or artist | A "Gekoppeld aan" column shows the label and/or artist name. |
| A channel with an open proposal | The column shows "voorstel", which opens the Links tab. |
| A channel that was never downloaded into a folder yet | The column stays empty: the table cannot tell which channel folder the account writes to until it has written one. |
| A wrong link was confirmed | "Ontkoppelen" in the column removes it; the proposal that led to it counts as rejected from then on. |

## Acceptance Criteria

1. With production's data, pressing Voorstellen zoeken produces proposals for roughly 860
   channels, and none for a channel whose name only resembles a label or artist.
2. Confirming a proposal makes the label or artist appear in the Coverage table for that
   channel, after a refresh of the table.
3. A rejected proposal does not come back after pressing Voorstellen zoeken again.
4. Pressing Voorstellen zoeken twice in a row adds nothing the second time.
5. A channel whose name equals several differently spelled artists gets a proposal only when one of
   those spellings is exactly the channel's, capitals aside.
6. A plain listener sees the proposals but cannot confirm, reject, search or unlink; that takes the
   rule-management permission, as label proposals do.
7. A channel that got no proposal (`Hysta Official`) can be linked to the approved artist `Hysta`
   from the Links tab by typing part of either name; the link shows in the Coverage table.
8. After the tagger's next pass over the channel, a track from a channel linked to a label carries that label, and
   a track from a channel linked to an artist whose artist was only the channel's own name carries
   the linked artist instead. A track whose title named its own artist keeps that artist.

## Linking by hand (issue #58)

Measured read-only on production on 2026-09-27: 1.379 channels (1.114 SoundCloud, 264 YouTube,
1 Telegram), none linked yet; 898 open proposals (149 label, 749 artist) waiting for review. 515
SoundCloud/YouTube channels got no proposal at all; they hold 77.171 tracks, 8.632 of which credit
the channel's own name as their artist and 877 no artist at all. Those are the channels only a
hand link can reach.

On the Links tab, above the proposal list, a **Link by hand** panel:

| Element | Content |
|---|---|
| Kanaal | A search box over every SoundCloud and YouTube channel (by name). Each suggestion shows platform, track count and what it is already linked to. |
| Soort | Label or artist. |
| Koppelen aan | A search box over the labels (placeholders and platform names are not labels) or over the **approved** artists, depending on the kind. Only approved artists are offered, the same rule the proposals follow: linking to a name that is still in the curation queue or was rejected would approve it through the back door. |
| Koppelen | Links the channel. The panel says how many tracks were queued for the tagger. |

| Situation | Observable outcome |
|---|---|
| The channel is not linked for that kind yet | It is linked; the Coverage table shows it after a refresh. |
| The channel is already linked to the same label or artist | Nothing changes, no error. |
| The channel is already linked to a *different* one of that kind | Refused with a message; unlink first (Coverage table). Relinking in one step would make a slip of the mouse undo a confirmed decision. |
| There was an open proposal for exactly this link | It counts as confirmed. Other open proposals of that kind for the channel are withdrawn. |
| There was a rejected proposal for exactly this link | The hand link wins: the curator has now said yes. |
| The artist was rejected or is still in the queue, or the label is a placeholder | Refused. |
| In the Coverage table, a channel without a link and without an open proposal | A **Koppelen** button opens the Links tab with that channel already picked, so the entry point sits on the row, not in a menu. |
| A plain listener | Sees the channels, cannot link (same permission as confirming). |

A hand link and a confirmed proposal are the same thing afterwards: both show in the table, both
are undone with Ontkoppelen, and unlinking either one keeps the search from proposing it again.

## What a link changes in the tags (issue #58)

A link is evidence about every track that came in through that channel. The tagger reads it for
SoundCloud, YouTube and Telegram files (the song types that know they came from a channel), and
only ever where the tag is empty or holds something weaker.

| Tag | Before | With a link |
|---|---|---|
| Publisher (becomes the track's label) | Always the platform (`Soundcloud`, `Youtube`), which is not a label, so the track had none. | The linked label. |
| Artist | Whatever the title said; failing that, the uploader's or channel folder's name standing in for an artist. | Where an artist value *is* that stand-in name, the linked artist replaces it. A name the title supplied is never touched. With no artist at all, the linked artist is it. |
| Genre | The artist's genre rules (and, on YouTube, the channel name looked up as a label). | Also the linked label's genre rules, exactly as a label release gets them. Added to, never replacing. |

The library stores that label for the track: a file under a platform folder still cannot carry
any other label (the platform itself least of all), only the one its channel is linked to.

The artist is then run through the usual artist curation (corrections and rejections), so a link
cannot smuggle a spelling past it. A link to an artist who was rejected *after* the link was made is
ignored by the tagger.

Linking, confirming or unlinking queues the channel's tracks for the tagger. That queue is served
after decisions (a genre or artist rule) and after newly arrived files, because a link enriches
tracks that are already correct and can easily cover thousands of them (Monstercat on SoundCloud
holds 5.154). Unlinking takes the label back off on the next pass (the publisher is recomputed
every time); an artist the link wrote stays, because by then it is indistinguishable from one the
file carried — Ontkoppelen is for undoing a wrong decision quickly, before that pass.

What this would add on production, if every open proposal were confirmed as it stands (read-only,
2026-09-27):

| | Channels | Tracks |
|---|---|---|
| Label proposals | 149 | 52.128 tracks, of which 50.449 have no label today and would gain one |
| … of which the label carries genre rules | 28 | 10.257 would get that genre as extra evidence |
| Artist proposals | 749 | 84.444 tracks; 45.130 already credit that artist, 777 credit nobody and would gain it, 285 credit the channel name in a different spelling and would get the artist's |

The artist proposals change little because they were made *because* the channel is named after the
artist, so the stand-in is usually already right. The artist half matters for hand links: the 8.632
tracks above credit a channel name like `Hysta Official`.

## A label page lists its channels (issue #122)

With the tagger writing the label, a linked channel's tracks already appear under that label
everywhere the library groups by label. The label page now also names the channels themselves.

Measured read-only on production on 2026-09-27: no channel is linked yet (0 of 1.379), with 898
proposals waiting for review. So today every label page shows no channels; the section fills as the
proposals are confirmed.

| Situation | Observable outcome |
|---|---|
| A label with linked channels | Under the heading, a **Kanalen** section: one card per channel, busiest first, with the platform's icon (SoundCloud, YouTube, Telegram), the channel's name and its number of tracks. The cards scroll sideways on a narrow screen; the page itself never gets wider than the screen. |
| Tapping a card | Opens the channel's tracks: the album the downloads are filed under (`Soundcloud (<channel>)`, `Youtube (<channel>)`). When the library has no album of exactly that name (the platform reported the uploader in another spelling), the account's page on the platform opens instead, if a followed account carries the channel's name. Failing both, a library search for the channel's name. |
| A label nothing is linked to (almost every label today) | No section, for a listener. |
| The same, for a curator (rule-management permission) | The section with "Nog geen kanaal aan dit label gekoppeld." and a **Manage links** link. |
| A curator, any label | **Manage links** next to the heading opens Management > Downloaders on the Links tab, where channels are linked and (from the Coverage table) unlinked. |
| The first visit to a label page | A curator sees three card-shaped placeholders until the answer arrives. A listener sees nothing until then: a placeholder on every label page that then disappears would move the track list for nothing. |
| A revisit in the same session | The last answer shows at once and is refreshed behind it. |
| The channels cannot be loaded | The section says so with **Opnieuw**, for everyone; the track list is unaffected. |

**A channel view showing its label or artist.** There is no channel page in the web interface; the
only place a channel is shown is the Coverage table under Management > Downloaders, which already
has the "Gekoppeld aan" column.

## The artist page and the label edit page list their channels (issue #126)

The same **Kanalen** section, in two more places. It behaves as on the label page in every row of
the table above, except where this table says otherwise.

| Situation | Observable outcome |
|---|---|
| An artist with linked channels | On the artist page, above the biography, the cards of the channels a curator linked to this artist, busiest first. |
| An artist nothing is linked to, for a curator | The section with "Nog geen kanaal aan deze artiest gekoppeld." and **Koppelingen beheren**. |
| The artist page before its name is known | No section. The page's address carries the player's artist number, which MuMa does not know, so the section waits for the artist's name and asks by name. |
| The label edit page (Beheer > Curatie > label) | The section after the catalogue, always shown (only a curator reaches this page), with **Koppelingen beheren**. Tapping a card opens the channel's tracks, as on the label page. |
| Unlink on the label edit page | Every card has an **x**. It removes the link at once, without a question, as the **x** in the Coverage table does: linking again is one step under Koppelingen. The card goes, the page's message line says "<channel> ontkoppeld.", and the next search does not propose the link again. The channel's files go back to the tagger, which takes the label off them. |
| An unlink that fails | The card stays and the page's error line gives the reason. |

Out of scope: filtering a label's track list by channel (the optional third item of the issue).
Unlink is offered only on the label edit page, not on the artist page or the label page, which are
pages for listening.

## Open Questions / Not Yet Decided

- Checking on production that a link does put its label on the tracks is issue #123.
- **Running the search automatically.** It runs when the curator asks. New channels appear only as
  fast as the downloaders follow new accounts, which is a handful a month.
