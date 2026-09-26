# A festival alias in an EP track's title makes it a live set

# status: fixed

# reported problem

GitLab issue #76: "Radium - Decibel Dictature" -- a 13.5-minute track from a Karnage Records EP
(`/mnt/music/EPs/Karnage Records/KRG_003-RE - Radium_-_Karnage_03_(remastered)-()-WEB-2021/`) --
is classified `form = liveset`, so it turns up under "Live sets" in the sets view.

# Possible reason

`services/common/track_form.py` (`derive_form`, used by the scanner and the hourly
`track_form_sync` pass) decides, for any file of ten minutes or longer outside the `Livesets`,
`Telegram` and `Podcasts` folders: an approved podcast show makes it a podcast, a festival alias in
the title (or in the path together with a year) makes it a live set. The folder the file sits in
played no part beyond those three. "Decibel" is an alias of Decibel Outdoor, so "Decibel
Dictature" matched and became a live set.

Measured read-only on production (2026-09-26): 126,938 media rows under `/mnt/music/EPs/`, of which
344 were `liveset`, 527 `set`, 52 `podcast`. Of the 344 live sets:

- 6 are long tracks like the reported one: Radium - Decibel Dictature, Drokz - Failure and two
  Broken Minds - Humanity Part 3 files (both under a "Masters Of Hardcore" release folder with a
  year), Brennan Heart - Katana ("I AM HARDSTYLE" folder), JDX - The Score ("Qlimax The Source").
- About 300 are a label's own mix album for a festival edition: "Defqon.1 2015 Mix 1 (Mixed by
  Ran-D)", "Decibel Outdoor 2017 Continuous Mix by Angerfist", The Qontinent, Reverze, Bassleader,
  Q-Base, Masters Of Hardcore, Thunderdome compilations. The functional design already lists "a
  label's mix album" as a `set`: it is a studio mix sold under the event's name, not a recording
  of a performance.
- 32 are recordings of the event itself, and every one of them says so in its title or folder:
  "Live at Reverze 2009" (the DVD rips of the "Live Registration" releases), "Qlimax 2008 The Live
  Registration", "Qlimax 2009 Live (Bonus CD)", `VA-Qlimax_2005-DVD-2006` and `Qlimax 2007 Dvd`,
  "Kai Tracid Live at Qlimax", and three `..._Live-STREAM-...` rips in `EPs/__TODO`.

Length does not separate these (the DVD rips are 10-15 minutes, the mix albums 50-80), and neither
does the performance date: the mix albums carry the edition's date just as the recordings do.

# solution

In the label tree (top folder `EPs`) a festival match alone now gives `set`; it gives `liveset`
only together with a live marker in the title or path -- the whole word `live`, `liveset(s)`, or
`dvd`/`dvda`, after `_ - . ( ) [ ]` are read as spaces. Everywhere else the rules are unchanged, so
a SoundCloud upload called "Decibel Dictature" is still a live set, as it was.

Expected effect of the first hourly form pass after deploy, computed from the production export
above: 312 EPs-tree rows go from `liveset` to `set` (97 of them lose the performance date they took
from their festival edition; the year filter falls back to the release date, which for an edition's
album is the same year or the next), 32 stay `liveset`, nothing else changes. The LMS push follows
in the same pass.

Known leftover: Warface's albums "Live For This" and "Live For This Vol. 2" (two continuous album
mixes, 54 minutes) stay `liveset`, since their title carries the word "live" and something in them
matches a festival. That is how they were classified before this change too.

Tests: `services/common/track_formTest.py` -- the Decibel Dictature case, a label's festival mix
album, DVD / "Live @" / live-stream recordings under `EPs` staying live sets, "live" only as a whole
word, and a festival-named track outside `EPs` still being a live set.
