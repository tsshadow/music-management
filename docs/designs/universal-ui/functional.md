# Universal UI — Functional Design

> Proposal, not yet agreed. Scope is the phone app (muma-mobile) first, the PC app second; the web
> player is the source and is not redesigned. The implementation contract is in
> [`technical.md`](technical.md). See [docs/designs/README.md](../README.md) for the process.

## Overview

MuMa has two user interfaces that are meant to look like one product and do not. The web player
(`services/frontend`, Svelte) is a Spotify look-alike that already carries every feature of the
product: songs and sets, advanced filtering, feeds, memories, listening stats, curation and
management. The phone app (`services/muma-mobile`, Kotlin, an edited Ultrasonic) implements a
subset of those features a second time in its own widgets, on its own styleguide, with its own
drift: ratings had three copies, the artist display name never reached the phone, the browse tags
exist in the app but are wired to nothing.

This design makes the web player **the** user interface. The phone app becomes a thin native
shell (Capacitor) that shows the same Svelte screens, with the native Android pieces that a
browser cannot provide kept underneath: background playback, Android Auto, offline downloads,
voice capture, crash diagnostics. A PC app follows later on the same principle. What a listener
sees on the phone is what they see in the browser at phone width, pixel for pixel, because it is
the same code.

Three decisions were taken with Teun on 2026-09-12 and are fixed for this design:

- **One style.** The Spotify style is the only style. The MuMa style (warm ramp, gold star) is
  retired; there is no theme switch.
- **In-place upgrade.** The new app ships under the same package name as muma-mobile. Downloads,
  settings, ratings cache and the Google sign-in survive the update.
- **First release must have** offline downloads and playback, Android Auto, MuMa Voice with the
  car-mode screen, and diagnostics. Jukebox and bookmarks are not carried over unless they turn
  out to be free.

## User Stories

- As a listener, I want the app and the website to be the same thing, so that I never look for a
  feature in the wrong place or find a button that only exists on one of them.
- As a listener, I want a slick phone app in the Spotify style I already like on the web, so that
  the phone is not the ugly version.
- As a listener, I want to switch between songs and sets everywhere — home, search, library,
  player, car — so that a two-hour set and a three-minute track are never mixed in one list.
- As a listener, I want to save tracks and sets to the phone and play them without coverage, so
  that a festival set survives the train tunnel.
- As a driver, I want Android Auto and voice to keep working exactly as they do today, so that the
  UI change costs me nothing in the car.
- As a listener at a PC, I want the same app with downloads, so that offline is not a phone-only
  feature.
- As the maintainer, I want to build every screen once and verify it once, so that AI-assisted work
  lands in the fast web test loop instead of the slow Android one.

## What the phone shows

Everything below is the existing web player at phone width (`isMobile`: narrower than 1024px or a
coarse pointer). Screens that exist on the web today are named; the four screens that are new to
the web because they were phone-only are marked **(new)**.

### Navigation frame

```
┌──────────────────────────────┐
│ ⬤ MuMa            🔍   👤    │  top bar: mark, search, profile — hides on scroll down
├──────────────────────────────┤
│                              │
│         <active view>        │  single column, scrolls
│                              │
├──────────────────────────────┤
│ ▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░ │  2px progress line
│ [art] Title        ▶  ⏭      │  mini player, 64px, tap = full-screen player
│       Artist                 │
├──────────────────────────────┤
│  ⌂      ♪      ◔      ▤      │  bottom bar: Home · Songs/Sets · Library · (Management)
└──────────────────────────────┘
```

The bottom bar is the existing `MobileNav`. The second tab is *Songs* in songs mode and *Sets* in
sets mode; it is the same tab, renamed and recoloured by the mode. Management appears only for an
admin. The sidebar of the desktop layout becomes a drawer opened from the profile button; it holds
the same items in the same order (feeds, library sections, playlists, settings, sign out).

### Home

The web dashboard as it is: greeting, shortcuts grid, the personal feeds (release radar, daily
mix), recently released, recently added, memories banner. The configurable home sections built for
the phone in 6.35.0 (button / overview / off per section, counts) are re-implemented once, in the
web dashboard, and apply on every width: the phone does not lose them, and the desktop gains them.

### Songs / Sets

The mode toggle lives in the drawer header exactly as it does in the desktop sidebar: a switch
between *Songs* (green) and *Sets* (blue). The whole app recolours. See "Sets" below for what else
changes.

### Library

The drawer's library section, laid out as a tab strip on the phone: Playlists · Artists · Albums ·
Genres · Labels · Festivals · Years · Podcasts · Lineups · Starred · History · Listening · Memories.
Tabs that hold nothing in the current mode are hidden, which is what the phone already does.

### Track list

The web `TrackList` in its simplified phone row: cover, title, artist, a rating, and a download
state glyph (see Downloads). Long-press opens the row's options sheet: play next, add to queue, add
to playlist, rate, download / remove download, show artist, show album, show song versions, share.
The options sheet is the same component the desktop shows as a context menu.

### Filter bar

The web `FilterBar` (genre, year, role, minimum rating, include unrated, sort) collapses to a
"Filter" chip row on the phone; tapping a chip opens a bottom sheet with that one control. Active
filters are visible as filled chips. This is the same filtering the phone's `FilterButtonBar`
offers today, so nothing is lost; the web's role filter and "include unrated" are gained.

### Full-screen player

```
┌──────────────────────────────┐
│ ⌄          Playing from       │
│         <playlist / album>    │
│                              │
│      ┌────────────────┐      │
│      │                │      │
│      │   cover art    │      │
│      │                │      │
│      └────────────────┘      │
│                              │
│ Title                    ♡ ⋯ │
│ Artist · Label · 2024        │
│ ★★★★☆                        │
│ ▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░ │
│ 1:23                   3:41  │
│   🔀   ⏮    ⏸    ⏭   🔁     │
│  ⬇ download   ≡ queue  ⚙ eq  │
└──────────────────────────────┘
```

New on the web (the styleguide already proposes it; the phone has `NowPlayingFragment`). The queue
button opens the queue as a sheet; the equalizer opens the existing web equalizer.

### Downloads **(new to the web, phone and PC only)**

A library tab that lists what is on the device: grouped by playlist / album / set, with size and
state per item (queued, downloading with progress, done, failed with retry). A header shows total
size and a "free space" line. Swipe or long-press removes a download. In the browser the tab is
absent — the drawer simply does not list it — because a browser cannot offer it.

### Car mode **(new to the web)**

The phone's `CarModeFragment` as one Svelte screen: four oversized buttons (play/pause, next,
voice, favourite), the current track, and nothing else. Opens automatically when Android reports
the car connected, as today, and is reachable from the drawer. Android Auto itself is not this
screen; Android Auto is native and unchanged.

### Voice **(new to the web)**

The phone's `MumaVoiceFragment` as one Svelte screen: microphone, "listening…", what was heard,
what was understood in words, what will play. The recogniser is the device's; the parser is the
one the car uses. In the browser the screen exists but the microphone button is disabled with a
note, so the "what the voice search understands" page stays reachable everywhere.

### Settings

The web settings tabs (general, advanced, about). Phone-only settings move into them under their
own headings: server, downloads (Wi-Fi only, storage location, quality), car (auto-open car mode),
voice (language), diagnostics (send report, view logs). Settings already sync to the account
through `/api/users/{id}/settings/frontend`; the phone-only ones join that blob.

### Sign-in and server

The web login page gains a server field, shown only inside the shell (the browser already knows
its server). First launch after the upgrade reads the server and credentials the old app stored
and signs in without asking. Google sign-in goes through the native sheet; the outcome lands in
the same place as the web flow.

### Management

Every management page the web has (19 tabs, grouped as the sidebar groups them), at phone width.
This is more than the phone's ten built pages today and replaces them.

## Sets

"Sets" is a mode, not a section: long recordings (DJ sets, festival sets, mixes, podcast episodes)
against tracks. The boundary is what the web uses today: ten minutes. Everything the mode already
does on the web carries over unchanged; the rows marked **+** are what this design adds so that
sets are first-class on a phone.

| Surface | Songs mode | Sets mode |
|---|---|---|
| Brand colour | green `#1db954` | blue `#2d5afc` — every accent, switch, progress bar, active tab |
| Second bottom tab | "Songs" | "Sets" |
| Search | tracks under 10 min | recordings of 10 min and up, placeholder says so |
| Library tabs | all with content | all with content — Festivals, Lineups, Podcasts typically only here |
| Home sections | feeds + recents of tracks | feeds + recents of sets, memories by set |
| Track row | title, artist | title, artist, **+ duration in h:mm** (the one thing worth the space) |
| Full-screen player | as drawn | **+ ±30 s skip buttons** flanking play; **+ scrub shows h:mm:ss** |
| Resume | none | **+ resumes where you left a set**, per set, on every device through the account (the phone's bookmarks feature, generalised; the reason bookmarks need no screen of their own) |
| Downloads | per track | per set; **+ a size line before confirming** (a set is hundreds of MB) |
| Android Auto | browse tree of songs | **+ the same tree of sets under one "Sets" root**, both roots always present |
| Voice | "play genre hardstyle" | **+ "play a set", "play a Defqon set", "play the latest set of <artist>"** |
| Radio / news | as today | as today — channels are mode-independent |

The mode is one setting, stored with the account, so switching on the phone switches the PC.

## How the web's features fit

Every route the web player has today, and where it lands on the phone. Nothing is dropped.

| Web route(s) | Phone placement |
|---|---|
| `/`, `/release-radar`, `/daily-mix` | Home; feeds as home sections and as drawer entries |
| `/songs`, `/sets` | second bottom tab (mode-dependent) |
| `/playlists`, `/artists`, `/albums`, `/genres`, `/labels`, `/podcasts`, `/festivals`, `/years`, `/lineups`, `/starred`, `/history`, `/listening`, `/memories` | Library tab strip |
| `/genre/…`, `/label/…`, `/podcast/…`, `/festival/…`, `/year/…`, `/lineup/…`, `/lineups/…`, `/artist/…`, `/album/…`, `/song/…`, `/memories/<year>`, `/search/…` | pushed detail pages with a back chevron; Android back button pops them |
| `/artist/…/edit`, `/label/…/edit`, `/genre/…/edit` | same detail pages, admin only |
| `/settings/{general,advanced,about}` | Settings from the profile button |
| `/management/*` | Management bottom tab, admin only |
| Queue panel | sheet from the full-screen player |
| Equalizer, radio picker, news mode, sync mode, deduplicate | unchanged; opened from where they open today |
| Release notes modal, toaster | unchanged |

URLs keep working inside the shell: a deep link `muma://` or the site's `https://…/set/…` opens
the matching page, and the Android back button follows the same history the browser would.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| Listener installs the update over muma-mobile 6.x | App opens signed in, on Home, with existing downloads listed and playable; no wizard |
| Listener opens the app in the browser on a phone | Identical screens; Downloads, car mode and the microphone are absent or disabled with a note |
| Listener taps play, then closes the app | Playback continues; notification with art and controls; lock-screen controls work |
| Listener reopens the app during playback | Mini player shows the playing track and correct position within a second |
| Listener flips Songs → Sets | Whole app turns blue; second tab says Sets; search, library tabs and home change; the PC follows on next load |
| Listener long-presses a set and picks Download | Sheet shows the set's size; confirm starts it; row shows progress; Downloads tab lists it |
| Phone loses connectivity | Downloads tab and every list that has downloaded content remain playable; other lists show the existing offline empty state |
| Listener plays a set, quits at 1:12:00, opens the set on the PC | PC offers "resume at 1:12:00" |
| Car connects | Android Auto shows the MuMa tree with a Songs and a Sets root; car-mode screen opens on the phone if that setting is on |
| Listener says "speel een Defqon set" to the car or the voice screen | A set from a Defqon lineup starts; the voice screen says which and why |
| Admin opens Management | The same nineteen pages as the web, grouped identically |
| App or native layer crashes | On next start a diagnostics report is offered; sent reports appear in the web's management → health, as today |
| Listener opens Settings → appearance | There is no appearance setting |

## Acceptance Criteria

1. A screenshot of any listener-facing screen in the phone app and of the web player at the same
   width, mode, data and settings are indistinguishable except for the Android status bar.
2. Every route in the "How the web's features fit" table is reachable in the app and renders the
   same content as on the web.
3. Upgrading from the last muma-mobile 6.x keeps the signed-in session, every completed download,
   and every setting that has an equivalent, without user action.
4. Playback survives closing the app, screen off, and a WebView being reclaimed; the notification,
   lock screen and Bluetooth controls keep working throughout.
5. Android Auto shows the same browse tree as before this change, plus a Sets root, and every feed,
   rating and search action in the car works as it did in 6.35.0.
6. A set downloaded to the phone plays in airplane mode, from the Downloads tab and from any list it
   appears in, with the full-screen player working (skip ±30 s, scrub, resume).
7. A set's playback position is resumed on the same device and on another device signed in to the
   same account, in both directions.
8. Voice commands listed on the "what the voice search understands" page work from the car and
   from the voice screen with the same outcome, including the three new set phrasings.
9. The mode switch changes colour, tab label, search boundary, library tabs and home content in one
   action, and the other device is in the same mode after its next load.
10. The Spotify style is the only style; no appearance or theme setting exists anywhere.
11. Every management page the web has renders and works on the phone for an admin.
12. A crash in the native layer or an uncaught error in the UI produces a diagnostics report that
    reaches the same endpoint and management page as today.
13. In a plain browser, the Downloads tab does not appear, the microphone is disabled with a note,
    and no other screen differs.

## Open Questions / Not Yet Decided

- **PC shell — decided 2026-09-12: PWA first.** The PC gets the web player as an installable PWA
  (service worker, Cache Storage for downloads, the MediaSession the player already has). That
  covers downloads, an own window and media keys without a third shell. Tauri 2 becomes a later
  phase only if a visible music folder, a tray icon or an unevictable cache turn out to be
  needed; the `platform` adapter makes that one more implementation, not a rebuild. Capacitor
  stays the Android shell; "Tauri for both" is closed.
- **Jukebox and bookmarks.** Not carried over. Bookmarks are replaced by set resume (functional
  criterion 7). If the jukebox is missed it becomes its own design.
- **Home sections on the desktop.** This design applies the configurable home to every width. If
  the desktop should keep its fixed dashboard, the setting is phone-only and the code still lives
  in the web.
- **Ten-minute boundary.** The web hard-codes 10 minutes; the phone passes `minDuration` through.
  Keep 10, or make it a setting? Proposal: keep 10, not a setting.
- **Diagnostics content.** The phone's report records recent user actions. Whether the UI's action
  log should be included from day one, or only the native log plus JS errors, decides part of
  phase 4.
- **Podcasts in songs mode.** Episodes over ten minutes count as sets today, short ones as songs.
  Fine, or should podcasts be mode-independent like radio?
