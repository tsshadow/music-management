# List continuation — Functional Design

## Overview

Since the feed paging work (`docs/designs/feed-length/`, bug report 122) a queue started from a
feed — a daily mix, Release Radar — tops itself up before it runs out, and the queue list ends in
"Meer laden". Every other list stopped at whatever was on screen when playback started. Teun
(2026-09-27): "En andere playlists. Kunnen we daar ook een manier krijgen om meer te laden aan het
eind? Stel je hebt 'recent uitgebracht' en bent bij het eind."

This feature gives every list that plays as a queue, and has more rows than its first page, the same
behaviour the feeds have: the list continues on the page, in the queue, and on its own while it
plays. Issue #100.

## User Stories

- As a listener playing "Nummers · Recent uitgebracht", I want the queue to keep going past the first
  page, so that the music does not stop after 50 tracks.
- As a listener looking at the queue, I want "Meer laden" under it when the list it came from has
  more, and a clear "Einde van de lijst" when it has not.
- As a listener playing a preset (a dynamic playlist), a genre, a label, an artist or a search, I
  want the same, without having to go back to the page and scroll.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| A row of a paged list is tapped, or its play button pressed | The queue holds what the page shows, and remembers where the list continues. |
| The playing track is within three of the end of such a queue | The next page is fetched and appended, without a tap. |
| The queue is opened while its list has more | The queue ends in the "Meer laden" pill; a tap fetches the next page now. |
| The list has nothing more | The pill is replaced by a muted "Einde van de lijst" line, in the queue and on the page. |
| A page brings tracks the queue already holds | Those are left out; the order of the rest is the list's own order. |
| A page fails to load | Nothing changes; the next track change or the next tap tries again. |
| A new queue is started from anywhere else (an album, radio, a playlist) | The previous list stops continuing. Radio and the news keep their own behaviour. |
| A list that fits on one page is played | No pill and no end line: there never was more. |

The lists that continue: the songs and sets lists with any sort or filter ("Recent uitgebracht",
"Recent toegevoegd", "Recent beluisterd", ...), the genre, label, podcast, festival, year and lineup
lists, search results, an artist's tracks, presets, the listen history, a memories year, the car-mode
mix, and — unchanged — the feeds and daily mixes. Search results also get "Meer laden" on the page,
which they did not have.

Not in scope: albums and playlists (they are loaded whole), the Home shelf cards (a card plays only
its own track and starts no queue), the "Nu speelt" continuation sections, and voice results.

Android Auto (issue #103): a queue the car starts from its own lists -- a tapped track or a play row
in a Songs/Sets tab sort, a genre, label, festival, podcast, year, lineup or Soort folder, or a
preset -- continues past what was shown in the same way, near its end and without repeats, as the
feeds already did there since issue #84. A shuffled list stays one shuffle across its pages. The
car has no queue pill or end line; the list it shows keeps its size, only the playing queue grows.

## Acceptance Criteria

1. Play "Nummers · Recent uitgebracht" from its first row; skip to the third-last track: the queue
   grows by the next page, with no track twice.
2. Open the queue of that list: it ends in "Meer laden"; tapping it grows the queue at once.
3. A list whose last page has been fetched shows "Einde van de lijst" at the end of the queue.
4. The same holds for a filtered song list, a preset and a search result, on the phone, the tablet
   and the desktop.
5. Starting an album afterwards shows neither pill nor end line under the queue.

## Open Questions / Not Yet Decided

- Whether a Home shelf card should start a queue of the whole shelf (and so continue): deliberately
  left as it is, it changes what a tap on a card means.
- A preset has a size of its own. The page loads that size as before; its continuation goes on past
  it with the same query and the same random seed. If Teun wants a preset to stop at its size, the
  continuation is one line to drop.
