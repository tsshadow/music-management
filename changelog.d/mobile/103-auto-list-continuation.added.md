- **Android Auto keeps playing past the end of its own lists** (issue #103). Since issue #84 a
  feed queue in the car tops itself up near its end; every other list still stopped after what
  was loaded -- 100 tracks of a genre, label, festival, podcast, year, lineup or Soort folder, 500
  of "Recent toegevoegd"/"Recent uitgebracht", one page of a preset. `FeedQueueContinuation` is
  now `ListQueueContinuation` with a source per kind of list (a feed's `next_offset`, or the
  list's own `getSongs` question again with `offset`/`count`), and a tapped track or a play row
  ("Alles afspelen", "Willekeurig", "Recent toegevoegd", a preset's rows, a tab's Random row) arms
  it the same way a feed does. Within three tracks of the end the next 100 are appended, never a
  track twice, one request at a time, and nothing is appended to a queue that has since been
  replaced; radio and news are never extended. A shuffled list (the Random rows, a shuffled
  preset) now carries a random seed from its first page on, so what follows is the rest of the
  same shuffle rather than a new draw that repeats it. The browse lists themselves keep their
  limits; only the playing queue grows. `docs/designs/list-continuation/technical.md` "Android
  Auto".
<!-- release notes -->
- In the car, a genre, label, festival, year, preset or "Recent" list now keeps playing past the
  tracks that were shown, like the daily mixes already did; shuffled lists stay one shuffle.
