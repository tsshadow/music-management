# Configurable Home Screen — Functional Design

> Status: **draft, not agreed**. The open questions at the end are real; nothing here is built yet.
> Scope is the muma-mobile phone app. See [docs/designs/README.md](../README.md) for the process.

## Overview

The phone's home screen — the "Mediabibliotheek" tab — is a fixed stack of sections in a fixed
order, each rendering its content in a way it decides for itself. You can switch the memories
carousel off and change two counts; everything else is whatever the app decided.

This makes the home screen the listener's. Every section gets one setting: show it as a **button**,
as an **overview**, or not at all. A section shown as buttons contributes its entries to one grid at
the top of the screen, so "start the daily mix" is a tap from the moment the app opens. A section
shown as an overview keeps its own heading and its list below that grid. Counts say how much each
section contributes.

The trigger was the two personalized feeds. They shipped as full inline track lists, which pushed
the library's own "recently released" and "recently added" lists off the screen entirely — and what
was wanted was an entry next to the shortcuts, with those lists still underneath.

## Why this is not only a settings feature

**The home screen can currently render only four sections, and which four is decided by position.**
`res/layout/primary.xml` contains four `<include>` slots and `MainFragment.render()`
(`MainFragment.kt:176`) pairs them with the view model's sections by index. Adding the two feeds as
the third and fourth providers therefore did not add two sections — it *replaced* the two recent
lists, while leaving each slot's "Meer" button pointing at what used to be there.

In app 6.34.0 that means the third card reads "Dagelijkse mix" and its "Meer" opens *recently
released*; the fourth reads "Release radar" and opens *recently added*; and the two recent lists
render nowhere. The bug is live and this design supersedes rather than patches it: a configurable
home screen cannot have a fixed number of slots at all.

## User Stories

- As a listener, I want to start my daily mix from the moment the app opens, so that I do not have
  to walk into the library first.
- As a listener, I want the sections I do not use to disappear, so that the screen is about what I
  actually play.
- As a listener, I want to see more or fewer entries per section, so that the screen fits what I
  keep an eye on rather than a number somebody picked.
- As a listener, I want a section to keep its place when it happens to be empty this week, so that I
  can tell "nothing new" apart from "this is gone".
- As a listener who upgrades, I want my home screen to keep the shape I know unless I change it.

## The three modes

| Mode | What it looks like |
|---|---|
| **Button** | One or more entries in the shared grid at the top. Each entry opens that thing; nothing is listed inline. |
| **Overview** | Its own heading and its content below the grid: a list of tracks, or the shortcut cards. A "Meer" action opens the full page. |
| **Off** | Not on the home screen at all. The section's own page stays reachable from the Library tab or the bottom bar. |

"Preview" from the first sketch is the same thing as Overview and does not become a fourth mode: one
word per behaviour, or a setting means something different per section and nobody can predict it.

A button is **one** button. A section can contribute several — four shortcuts are four buttons — so
the grid is built out of the buttons of every section that is set to Button, in a fixed section
order. The buttons of one section stay next to each other, but a row may hold buttons from two
sections: forcing every section onto a fresh row leaves a half-empty row behind every odd count.

**A button says where it came from when it cannot say so itself.** "Release radar" and "Daily mix"
name themselves. A favourite and a shortcut do not: both are an album or an artist with cover art
and a name, and the same album can legitimately be both. Those buttons carry a small second line —
"favoriet", "recent gespeeld" — which is what a heading would have told you, without five headings
eating the top of the screen. It also explains why an entry appears, why it vanishes, and which
count controls it.

This is a hybrid of the two obvious layouts and deliberately so. Worth knowing: Garmin Connect,
which was the reference, does *not* use one undifferentiated grid — it has named areas ("In Focus",
"At a Glance") with smaller cards in the second. The compact grid here is what was asked for; the
per-button labels are what replaces the names Garmin uses.

```
Memories        │ Release radar
Daily mix 1     │ Daily mix 2
Favoriet 1      │ Favoriet 2
Shortcut 1      │ Shortcut 2
Shortcut 3      │ Shortcut 4
─────────────────────────────────
Recent uitgebracht        Meer →
  <track>
  <track>
Recent toegevoegd         Meer →
  <track>
```

## The sections

| Section | Modes | Count | A button opens | An overview shows |
|---|---|---|---|---|
| Memories | Button, Off | — (always one) | The Memories page for the nearest year with tracks | — |
| Release radar | Button, Overview, Off | Button: fixed 1. Overview: 1–10 rows | The whole radar, in MuMa's order | The first N tracks |
| Daily mix | Button, Overview, Off | 1–10 | That mix, in MuMa's order | The first N tracks |
| Favorieten | Button, Overview, Off | 1–10 | That favourite album or artist | N favourite albums and artists |
| Shortcuts | Button, Overview, Off | 2–10 | That place, exactly as the grid does today | The grid as it is today |
| Recent uitgebracht | Button, Overview, Off | Overview: 1–10 rows | The full list, newest release first | The first N tracks |
| Recent toegevoegd | Button, Overview, Off | Overview: 1–10 rows | The full list, newest addition first | The first N tracks |

Memories has no overview: a memory is already a summary of a year ("Today, 1 year ago · 30
nummers"), and listing its tracks inline would be the Memories page with extra steps.

The release radar is one radar, so it is one button. A count there would have to mean "the first N
tracks of the radar as N separate buttons", which is not a thing anybody wants. The daily mix does
take a count, because there is expected to be more than one mix later — today there is one, so a
count above 1 simply yields what exists.

Favourites are new to the home screen; they exist today only as the bottom-bar tab, which stays.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| A section is set to Button | Its entries appear in the grid at the top, in section order, without a heading |
| A section is set to Overview | It appears below the grid with its own heading and a "Meer" action |
| A section is set to Off | It is absent from the home screen; its own page stays reachable elsewhere |
| A section set to Button has nothing to show | Its entry stays, and says so when opened. Only "Off" removes a section |
| A section set to Overview has nothing to show | The heading and the "Meer" action stay; one line explains why it is empty |
| A section fails to load | Whatever was shown last stays, with a short "kon niet verversen" and a retry. Nothing is silently cleared |
| Every section is set to Off | The home screen says so and points at the Library tab, rather than being blank |
| A count is changed | The next return to the home screen shows the new number; no restart needed |
| The daily mix button is tapped | The full mix opens in MuMa's order. It does not start playing by itself |
| A shortcut button is tapped | The same place it opens today |
| The app is upgraded | The home screen keeps the shape described under "Defaults" without anything being asked |

## Defaults

For everyone, on upgrade and on a fresh install:

| Section | Mode | Count |
|---|---|---|
| Memories | Button (Off if the memories setting was switched off) | — |
| Release radar | Button | 1 |
| Daily mix | Button | 2 |
| Favorieten | Off | 4 |
| Shortcuts | Overview | whatever `home_shortcut_count` holds, normally 8 |
| Recent uitgebracht | Overview | whatever `home_list_count` holds, normally 5 |
| Recent toegevoegd | Overview | whatever `home_list_count` holds, normally 5 |

This is the arrangement that was asked for: the two feeds as entries at the top, the two recent
lists as overviews below them. It also puts the recent lists back on screen, which 6.34.0 removed.

The two existing count settings keep their values. `memories_on_home` decides the memories mode once
and is then replaced by it. Nobody is asked to confirm anything: a settings page that demands a
visit before the app works properly is worse than a changed screen.

## Out of scope for v1

- **Reordering.** Garmin Connect lets you drag cards; this does not. The order is fixed as in the
  table above. Adding it later means a stored order, an editor with drag handles, and rules for
  sections that did not exist when the order was saved — none of which blocks the rest.
- **The web UI.** `services/frontend` has its own home screen with its own rows. This setting is the
  phone's; the web is not changed and does not read it.
- **Syncing the choice between devices.** MuMa can store per-app settings server-side, but the
  phone's sync hook is empty today, so this stays local to the device.
- **New sections.** Nothing is added beyond favourites.

## Acceptance Criteria

1. Every section can be set to its supported modes, and the choice survives closing the app.
2. Sections set to Button share one grid at the top, in the documented order, with no per-section
   headings; sections set to Overview appear below it with their own heading.
3. Setting both feeds to Button and both recent lists to Overview yields exactly the layout in the
   sketch above, including the two recent lists being visible.
4. A section's "Meer" action and its buttons open that section's own content — never another
   section's. In particular, the third and fourth sections open what their heading says.
5. A count changes how many entries that section contributes, in both modes where a count applies,
   and never changes what the destination page shows.
6. The release radar contributes exactly one button and offers no button count.
7. A section with no content keeps its place unless it is set to Off, and says why it is empty.
8. A failed refresh keeps what was last shown and offers a retry; it is distinguishable from a
   section that is genuinely empty.
9. After upgrading, the home screen matches the Defaults table without the user opening settings.
10. Changing any of this has no effect on the web dashboard.

## Open Questions / Not Yet Decided

1. **Is a small "favoriet" / "recent gespeeld" line on a button enough?** It is the proposal, and
   it is a guess that wants a look at a real phone with long track names and large text before it is
   built. The star that already exists (`HomeCard.isFavorite`) is *not* a substitute: a favourite
   album can also turn up among the shortcuts, so the star says "you like this", not "this button
   comes from Favorieten". The alternative is a heading per section in the grid, which costs the
   compactness the sketch was about.
2. **What does the daily-mix count mean while there is only one mix?** Proposed: it yields what
   exists, so a count of 2 shows one button today and two when a second mix is built. The
   alternative is to hide the count until there is more than one mix, which is less honest but shows
   nothing that looks broken.
3. **Does a button start playing?** Proposed: no, a button opens the list and you press play there.
   For a daily mix, "tap and it plays" is arguably the whole point.
4. **Does the shortcuts count still mean pairs?** It steps 2/4/6/8/10 today because the grid is two
   columns. In a shared grid that constraint is gone, so 1–10 would work — but an odd count leaves a
   half-empty row wherever that section lands.
5. **Two things in the code make this more than a layout change, and both need a decision.** The
   grid card layout (`home_card_grid.xml`) has no second line at all — 56dp artwork, a title of at
   most two lines, an optional star — so the source label needs a new view, which changes how every
   existing grid card looks. And `HomeCard.key` is `type:itemId`, so the same album contributed by
   both Favorieten and Shortcuts is one key twice; the grid's diffing needs an identity that
   includes which section put it there.
6. **Where does the setting live?** Proposed: a "Startscherm" block on the existing settings page,
   one row per section. With seven sections plus counts that is fourteen rows, which may deserve its
   own sub-page.
