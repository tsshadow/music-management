# GetSongBPM As An Octave Prior — Functional Design

## Overview

The BPM analysis measures a pulse, and it must then pick the octave: 64, 128 or 256. For a track
on a label or by an artist the collection knows, the label's and the artist's other tracks settle
it ([bpm-octave](../bpm-octave/functional.md)). A mainstream track from Hitzone, Spotify, Lidarr or
Top 100 often has neither. Only two general rules decide for it: "pop sits around 105" and "most
music sits around 135". Such a guess is shown, but never marked reliable and never written into
the file.

GetSongBPM (getsongbpm.com) lists a tempo for most mainstream songs. Its API is free with a key,
and its terms ask for a link to getsongbpm.com wherever its data is used. This change asks
GetSongBPM about those weak tracks, and lets the listed tempo pick the octave. The listed tempo is
never shown as the track's tempo: the measurement stays the number, GetSongBPM only says which
octave of it is right.

The feature is off until someone enters a key in Beheer > Config > BPM.

## User Stories

- As a listener, I want a Hitzone ballad measured at 64 to show 128 and count as reliable, so that
  it lands in the right place in Browse by BPM and its tag gets written.
- As the owner, I want nothing sent to an outside service until I enter a key, so that the library
  stays private by default.
- As the owner, I want GetSongBPM credited where its data helped, so that the API's terms are met.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| No key in Beheer > Config > BPM | Nothing is asked. Tempos are chosen as before. |
| A key is entered | On its next round the analysis asks GetSongBPM about 50 songs, and 50 more every ten minutes after that, newest tracks first. Only tracks in a mainstream folder without a label or artist to go by are asked. |
| GetSongBPM lists the song at 128, measured at 64 | The track shows 128 at once, marked reliable when the pulse was clear. The tag writeback writes it. |
| GetSongBPM lists a tempo that matches no octave of the measurement (100 against 64/128) | Ignored: that is another recording. The track keeps the tempo it had. |
| GetSongBPM does not know the song | Remembered for 90 days, then asked again. |
| The key is wrong | The analysis logs one warning and stops asking for a day, or until the key changes. |
| GetSongBPM is busy (HTTP 429) or unreachable | That pass stops. The next pass, ten minutes later, tries again. |
| The key is removed again | Every track is re-decided without GetSongBPM within minutes. |
| A track's tempo was decided with GetSongBPM | The player's track details show "via GetSongBPM" after the BPM, a link to getsongbpm.com. |
| A tempo set by hand | No GetSongBPM link: the person's value is shown. |

## Acceptance Criteria

1. Without a key, no request leaves the analyzer and no tempo changes.
2. With a key, André Hazes's "Vaag en Stil" (Hitzone, measured 64) shows 128 and is reliable once
   GetSongBPM lists it at 128.
3. A track on a label or by an artist with enough measured tracks is never asked about.
4. A song is asked about once; a miss is asked again after 90 days.
5. The key never appears in a log line or in the config page (it shows as dots).
6. The track details show the GetSongBPM link exactly when its tempo helped decide.

## Open Questions / Not Yet Decided

- **Pace.** 50 songs per ten minutes (300 an hour) is below any limit GetSongBPM has published. If
  its answer to a key states a different limit, change `PASS_BUDGET` and `PASS_SECONDS`.
- **The API host.** The client asks `api.getsongbpm.com/search/`. If the key's welcome mail names
  another host, change `API_URL`. Nothing in the tests depends on it.
