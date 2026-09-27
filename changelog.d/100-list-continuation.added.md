- **Every long list keeps going in the queue, not only the daily mixes** (issue #100,
  `docs/designs/list-continuation/`). Playing "Nummers · Recent uitgebracht" from its first row
  queued the 50 tracks on screen and then stopped. The same happened with every other sort and
  filter of the songs and sets lists, with a genre, label, podcast, festival, year or lineup, with
  search results, an artist's tracks, a preset, the listen history, a memories year and the car-mode
  mix. Each of these lists now hands the queue it starts a continuation. The queue tops itself up
  near its end, as the daily mixes already did, and the queue sheet and side panel end in "Meer
  laden" while the list has more. Once a list that did continue has nothing more, both the page and
  the queue end in "Einde van de lijst". A track the queue already holds is never added twice, and
  a failed page is tried again on the next track or tap. Search results now also get "Meer laden" on
  the page. The feed-only top-up (`feedQueue.js` `extendFeedQueue`, `QueueFeedLoadMore`) became one
  source among several (`listContinuation.js`, `trackPages.js`, `QueueLoadMore`, `ListEnd`). Albums
  and playlists are loaded whole and are unchanged.
<!-- release notes -->
- A queue started from any long list keeps going past the first page: "Recent uitgebracht" and the
  other sorts and filters of the songs and sets lists, genres, labels, search results, artists,
  presets and the listen history. The queue ends in "Meer laden" while the list has more, and in
  "Einde van de lijst" when it has not.
