# Wrapped Pre-Work — Functional Design

> Scope note: this document covers the **data groundwork** for a 2026 Wrapped, not the Wrapped page
> itself. The page is deliberately undecided; the data it will need is not, and part of it can only
> be collected going forward. The reasoning behind every choice here is in
> [research.md](research.md).

## Overview

MuMa is going to produce a year-in-review for 2026. Two things stand between the current system and
a truthful one, and they have opposite deadlines.

The first is **listening fidelity**. A listen currently records *that* something was played, never
*how long*, and always claims to come from the same place. A play that ends in a skip is not
recorded at all on mobile. None of that can be repaired afterwards — a play that was never written
down is gone — so it has to be fixed before the rest of the year is spent. This design covers that
fix.

The second is **what a label is**. `Soundcloud`, `Youtube` and `Telegram` currently sit at the top of
the label chart with 132.037, 30.779 and 1.556 tracks. They are not labels; they are the channels a
file arrived through. `__TODO` and `__Free&none` are not labels either — one is a placeholder, the
other a folder that collects music with no label at all. A "your label of the year" card built on
today's data would name SoundCloud. This design covers what replaces it: a **channel** as a first
class thing, separate from a label, and able to point at the artist or the label it actually is.

The Wrapped itself is planned as two pages: a **user wrapped** (what you listened to, what you rated)
and a **server wrapped** (what MuMa collected, tagged and downloaded that year). Their contents are
not decided here.

## User Stories

- As the listener, I want the minutes I actually listened to be counted, so that a 90-minute set I
  sampled for four minutes is not reported as 90 minutes.
- As the listener, I want a set I skipped away from to still count as having been played, so that my
  history reflects what I did rather than what I let run to the end.
- As the listener, I want to see where I listened — at my desk, on my phone, in the car — so the
  year can be split by how I lived it, not just by what played.
- As the listener, I want my top labels to be real record labels, so that "your label of the year"
  says Dirty Workz and not SoundCloud.
- As the listener, I want a channel I follow to be recognised as the artist or the label it belongs
  to, so that a SoundCloud channel and a YouTube channel for the same label count as one thing.
- As the collection owner, I want the server's own year — files downloaded, tagged, scanned — to be
  available as its own story, separate from my listening.

## Functional Flows

### Listening fidelity

| Situation | Observable outcome |
|---|---|
| A track plays to its natural end | A listen is recorded, with the seconds actually played |
| A track is skipped after a while | A listen is recorded, with the seconds actually played |
| A track is skipped within a few seconds | Nothing is recorded — a glance is not a listen |
| Playback happens in the web player | The listen is marked as coming from the web frontend |
| Playback happens in the phone app | The listen is marked as coming from mobile |
| Playback happens while the phone is connected to the car | The listen is marked as coming from the car |
| Playback happens in the legacy LMS interface | The listen is marked as coming from that interface |
| A listen arrives from an older client that sends nothing new | It is still recorded; playing time is simply absent for that listen |
| A listen recorded before this change is read back | Its playing time is absent and its origin is the old generic value; nothing breaks |

### Channels and labels

| Situation | Observable outcome |
|---|---|
| A file arrives from a followed SoundCloud channel | Its channel is recorded as a SoundCloud channel; no label is invented |
| A file arrives from a followed YouTube channel | Its channel is recorded as a YouTube channel |
| A file sits under the placeholder or the no-label folder | It carries no label at all, rather than a made-up one |
| A file comes from a real label release | Its label is recorded as today |
| A channel is recognised as belonging to a label | Plays through that channel can be attributed to the label |
| A channel is recognised as being an artist | Plays through that channel can be attributed to the artist |
| The same label has both a SoundCloud and a YouTube channel | They remain two channels, both pointing at the one label |
| A channel has been linked to nothing yet | It still counts as a channel; it simply has no label or artist behind it |

## Acceptance Criteria

1. A listen submitted by an up-to-date client carries the number of seconds actually played, and that
   number is visible when the listen is read back.
2. A play abandoned within the ignore threshold produces no listen; a play abandoned after it does.
3. Listens can be counted separately per origin, with at least the web frontend, mobile, car and the
   legacy interface distinguishable from one another.
4. A client that has not been updated can still scrobble successfully, and its listens are stored
   without playing time rather than rejected.
5. Listens recorded before this change remain readable and countable; only their playing time and
   their origin are absent or generic.
6. No entry in the label list is an acquisition source (`Soundcloud`, `Youtube`, `Telegram`), a
   placeholder (`__TODO`) or the no-label folder (`__Free&none`).
7. A channel can be listed with its platform, and separately from any label.
8. A channel can be pointed at the label or the artist it represents, and two channels on different
   platforms can point at the same one.

## Out of Scope

- **The Wrapped page itself.** Deliberately undecided. Web-only is the current thinking, on the
  grounds that what gets shared is a screenshot; that is not yet settled.
- **Re-matching old listening history.** Most of the unmatched two thirds is imported ListenBrainz
  history for music that was never in the library. The raw rows are kept, so nothing is lost, but
  they are not a target.
- **Restructuring the music folders** (`/music/labels/<label>/<ep>`, `/music/songs/…`,
  `/music/import`). Agreed to be the correct end state, but it moves files on disk and therefore
  touches the keys ratings and listens are stored against. It gets its own design and its own
  migration; see issue [#61](https://gitlab.example.com/muma/music-management/-/issues/61).
- **Wider BPM detection.** Wanted, and independent of everything here.
- **Genre completeness.** Where the rules do not cover something and the download carried no genre,
  a missing genre is accepted.

## Open Questions / Not Yet Decided

- Where the Wrapped lives (web only vs. also mobile) and what each of the two pages contains.
- Whether the car should be its own origin or a flag on top of mobile. Treated here as its own
  origin, because that is how it will be read on the page.
- Whether a channel may point at both a label and an artist at once, or must pick one.
- Whether channel-to-label links are curated by hand, proposed automatically for confirmation (as
  label proposals already are), or both.
