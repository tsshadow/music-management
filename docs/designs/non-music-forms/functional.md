# Interviews and previews as non-music — Functional Design

> Status: **agreed** (2026-10-03). Issue
> [#157](https://gitlab.example.com/muma/music-management/-/issues/157). The decisions are
> at the end.

## Overview

The YouTube and SoundCloud downloads include talk: festival interviews ("QAPITAL 2019 ｜ Interview
with Rejecta"), DJ Mag profiles, and the trailers Q-dance makes for its DVDs ("Qlimax 2010 ｜
Blu-ray ⧸ DVD Preview ｜ Zatox"). Since bug report 142 these files get a sensible artist and title.
They are still songs to MuMa. A daily mix can pick one, the radio can play one, and the library
counts them as tracks.

This change gives them a form of their own, next to `track`, `set`, `liveset` and `podcast` (see
[track-form](../track-form/functional.md)): `interview` or `preview`. A file with one of these two
forms stays in the library and you can still find it. No music feature picks it.

## What production holds (2026-10-03)

| Group | Files | Examples |
|---|---|---|
| Interviews, by the rule below | 231 | "Ground Zero Festival 2014 - Lenny Dee Interview", 13 x "QAPITAL 2019 Interview", "Headhunterz interview", "Top 100 DJs Profile Interview (2014)", 101Barz "'Ik houd echt van Rotterdam' - Interview" |
| DVD and Blu-ray previews, by the rule below | 20 | Q-dance "DVD Preview", "Blu-ray;DVD Preview", "DVD;Bluray preview" |
| Song previews, which stay music | about 5,400 | "Zudröhnen (Preview)", "\"TKT\" Studio Preview", "【Preview】Srav3R" |

Of the 251 files, 212 are `track` today, so the songs side holds them. The other 39 are `set`,
`liveset` or `podcast` because they are longer than ten minutes. No listen in `scrobble_listens`
points at any of the 251, so the listening statistics do not change today. The change stops the
next listen from going there.

Most uploads with "preview" in the title are a short part of a real song, from the producer before
the release. That is music, and it stays music. Only a preview of a DVD or Blu-ray is talk and
crowd footage.

## How MuMa decides

| Form | Rule |
|---|---|
| `interview` | The title has the word "interview" or "interviews", the file is under `Youtube/` or `Soundcloud/`, and the title does not also say "set", "liveset", "mix", "intro" or "outro" |
| `preview` | The title has "DVD" or "Blu-ray" next to "preview" ("DVD Preview", "Blu-ray / DVD preview", "Preview DVD") |

These two rules come before every other form rule, length included. A 12-minute interview is an
interview, not a set.

The music-word guard keeps these as music: "Pat B At Topradio Liveset + Interview" (a radio set
with a short talk), "Going To An Interview (Outro Storytelling Audio)" (a song on a label EP).
The folder guard keeps every label release music, because a song can be called "Interview".

## User Stories

- As a listener, I want my daily mix and the radio to play only music, so that a five-minute talk
  does not come between two songs.
- As a listener, I want the songs view to list songs, so that 13 "QAPITAL 2019 Interview" rows do
  not take up the page.
- As a listener, I want to still find an interview when I search for it, so that I can watch the
  one I downloaded.
- As the curator, I want the library counts to count music, so that the numbers mean something.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| Songs view, no filters | No interview or DVD preview in the list |
| Sets view, Soort "All" | No interview or DVD preview in the list |
| Search for "Lenny Dee Interview" | The interview is in the results |
| Open an artist, for example Headhunterz | The interview is not in the artist's track list. Search finds it |
| Daily mix, release radar, old hits, radio | Never pick an interview or a DVD preview |
| Song versions (Versies) | An interview is never a version of a song, and never hides one |
| Beheer, statistics | "Tracks" counts music. A second number shows the non-music files |
| A new interview is downloaded | It is non-music within the hour, the same as the other forms |
| A curator thinks a file is music after all | A rename of the file, so the title no longer matches. Beheer has no per-track correction |

## Acceptance Criteria

1. Each production example in the first two rows of the table above is `interview` or `preview`.
2. "Zudröhnen (Preview)", "Pat B At Topradio Liveset 14-02-2020 + Interview" and "Going To An
   Interview (Outro Storytelling Audio)" keep the form they have today.
3. No interview or DVD preview is in the songs view, the sets view, an artist's track list, a
   daily mix, the release radar, the old-hits feed or the radio.
4. A search by title still finds them.
5. An interview never has a song version, and no song is hidden behind one.
6. The deploy runs no library-wide migration. The hourly form pass changes the forms.

## Decisions

Teun agreed the proposal on 2026-10-03:

1. Two forms, `interview` and `preview`, as the issue names them.
2. A DVD or Blu-ray preview is non-music at every length, the 35-minute one included.
3. Trailers, teasers and aftermovies stay music.
4. No per-track correction in Beheer for now. A rename of the file is the fix.
5. Interviews are found through search only. The artist page does not list them.
