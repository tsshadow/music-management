# URL Routing — Functional Design

## Overview

The web player already put some of its screens in the browser's address bar, but not all of them, and
never consistently. Opening the listening history or the favourites screen left the URL pointing at
whichever page you were on before; opening a playlist left it pointing at the playlist *list*; and every
tab inside Settings and Management was invisible to the URL entirely, so there was no way to send someone
a link to, say, the scanner screen.

This change makes the address bar describe where you actually are. Every screen the sidebar can reach,
every artist, album, genre, label and playlist you can open, and every tab inside Settings and Management
now has its own address. Those addresses survive a refresh, can be bookmarked, and can be pasted to
someone else. The browser's back and forward buttons follow the same trail.

## User Stories

- As a listener, I want to refresh the page and stay on the screen I was looking at, so that I don't lose
  my place every time I reload.
- As a listener, I want to bookmark an artist, album, genre or playlist, so that I can jump straight back
  to it later.
- As an administrator, I want to link a colleague directly to a specific management tab, so that I don't
  have to describe how to click there.
- As a listener, I want the back button to take me to the previous screen rather than out of the app, so
  that navigating feels like a normal website.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| Opening a sidebar page (Songs, Sets, Albums, Genres, Labels, Artists, Playlists, Memories, History, Favourites) | The address bar shows that page, e.g. `/history` |
| Opening an artist, album, genre or label | The address bar names it, e.g. `/artist/1234` or `/genre/Drum%20%26%20Bass` |
| Opening a playlist | The address bar shows `/playlist/<id>` |
| Switching tabs inside Settings | The address bar shows `/settings/general`, `/settings/advanced` or `/settings/about` |
| Switching tabs inside Management | The address bar shows `/management/<tab>`, e.g. `/management/scanner` |
| Refreshing on any of those addresses | The same screen comes back, including the tab that was open |
| Opening `/settings` or `/management` without a tab | The tab you last used opens |
| Opening an address whose tab no longer exists | The first tab of that screen opens, rather than an empty page |
| Opening an address that matches nothing | The home screen opens |
| Refreshing on a genre or search term containing a dot, e.g. `nu.jazz` | The screen comes back; previously this returned a "File not found" page |
| Pressing back or forward | The previous or next screen in the trail opens, tabs included |
| Arriving at any address without being logged in | The login screen opens, as before |

## Acceptance Criteria

1. Every screen reachable from the main sidebar has its own address, and refreshing on it returns to that
   screen.
2. Opening a playlist changes the address to that playlist, and refreshing on it reopens the same playlist.
3. Every tab in Settings and in Management has its own address, and refreshing on it reopens that tab.
4. Visiting `/settings` or `/management` without naming a tab reopens the tab that was last used.
5. Visiting a tab address that no longer exists opens that screen's first tab instead of a blank page.
6. A genre, label or search term containing a dot survives a refresh instead of producing a "File not
   found" page.
7. Back and forward move through the screens visited, including tab switches.
8. Genre and label addresses continue to use the name, so links shared before this change keep working.

## Open Questions / Not Yet Decided

- A track detail screen (`/track/<id>`) was raised as possibly interesting, modelled on the track info
  screen in MuMa Mobile. It is deliberately out of scope here; the routing table has room for it without
  rework once that screen is designed.
