# Release And Series Markers In Download Titles — Functional Design

## Overview

SoundCloud and YouTube uploads often name the release or series they belong to in the title:
"Luner - Holding On To You ｜ Q-dance presents SPEQTRUM", "Deviouz & Matzic - Tomorrow (Gearbox
Presents Lockdown 3.0)". The tagger read that marker as the artist and title, so every song of a
series got the same artist and title and the Versies grouping hid all but one of them. This change
makes the tagger recognise the marker, keep it out of artist and title, and file it as the album.
Bug report 142 has the production examples.

## User Stories

- As a listener, I want every song of a release series to appear as its own song, so that a
  collapsed list does not hide 60 different tracks behind one.
- As a listener, I want a remix to be a song of its own, not a hidden version of the original.
- As a curator, I want the release a download belongs to as its album, so I can browse it.
- As a curator, I want very large works put in front of me, so I can catch the next false merge.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| `Artist - Title ｜ Label presents Release` | Artist and Title as written; album Release |
| `Artist - Title (Label Presents Release)` / `[Label Presents: Release - CAT042]` | Same; catalogue number CAT042 when the file had none |
| `Artist - Title (Name: The Mini Album)` | Album `Name: The Mini Album` |
| Album already set by hand, or to anything other than the channel default | Album unchanged |
| `ARTIST ｜ Title ｜ <channel>`, `Artist - Title ｜ Series ｜ <channel>` | The channel is never the artist; the series is left out of the title |
| `<Event> ｜ Interview with <Artist>` | Artist the interviewee, title `<Event> Interview` |
| `<Song> ｜ Cover by <Artist>` | Artist the performer, title `<Song> (Cover)` |
| `<Event 2010> ｜ ... Preview ｜ <Artist>` | Artist from the last segment, title `<Event 2010> - ... Preview` |
| `Title Ft. Someone (X Remix)` | Title keeps `(X Remix)`; the remix is its own song |
| `Bloodlust presents: The Assassination ｜ ...` (marker at the start) | Bloodlust is the artist, as before |
| A work with more than 10 versions | Marked suspicious in the Versies review; not split automatically |
| After the release is deployed | Files tagged the old way are re-tagged and regrouped on their own |

## Acceptance Criteria

1. None of the titles in bug report 142 produces the label, channel, series or "Interview" as
   artist, or the release name as title.
2. The release name is the album of a download whose album was empty or the channel default.
3. A hand-set album is never replaced.
4. A remix and its original are in different works.
5. Existing files are corrected after deploy without anybody running a script.

## Open Questions / Not Yet Decided

- Interviews and previews are not music and should get their own marker later (Teun files the
  issue). This change only gives them a sensible artist and title.
