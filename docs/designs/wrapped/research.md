# MuMa Wrapped — Research

> Research note, not yet a functional design. It answers one question: *can MuMa produce a
> year-in-review for 2026, and what would be in it that Spotify cannot do?*
> Measurements were taken against production (`192.0.2.27:8000`) on 2026-08-23 over the HTTP API.

## Verdict

Yes — and the interesting half of it is impossible on Spotify. MuMa knows the **label**, the
**festival and its edition**, the **remixer and producer credits**, the **BPM**, the **acquisition
date** and **where a file came from**. Spotify shows none of those, and since it withdrew its
audio-features API in November 2024, nobody can rebuild the BPM half of it there either.

The catch is not the presentation, it is the listening data. Three defects in the collection path
mean 2026's listens are currently incomplete, undated in playing-time terms, and blind to the device.
Two of the three can only be fixed *forward* — nothing recovers a play that was never recorded. It is
2026-08-23; roughly four months of collection remain. **The data fixes are the deadline, the Wrapped
page is not.**

## What production actually holds

| Figure | Value | Source |
|---|---|---|
| Tracks | 325.101 | `/api/stats/` |
| Artists | 52.903 (30.401 canonical) | `/api/stats/`, `/api/analytics/summary` |
| Labels | 1.320 | `/api/analytics/summary` |
| Genres | 533 | `/api/analytics/summary` |
| Total library duration | 220.940.567 s ≈ **7 years of audio** | `/api/analytics/summary` |
| Average track length | 939 s ≈ **15,6 min** | `/api/stats/` |
| Matched listens (all time) | 17.573 | `scrobble_listens` via `/api/stats/` |
| Unmatched listens (all time) | 35.201 | `scrobble_unmatched_listens` via `/api/stats/` |
| BPM coverage | 27,35 % | `/api/analytics/summary` |
| Genre coverage | 19,93 % | `/api/analytics/summary` |
| Artist coverage | 71,25 % | `/api/analytics/summary` |
| Ratings, user `user` | 1.357 (61×1, 179×2, 235×3, 559×4, **323×5**) | `/api/rating/ratings/user` |
| Ratings, user `someuser` | 0 | `/api/rating/ratings/someuser` |
| BPM peak of the collection | 150–160 (18.491 + 12.686 tracks) | `/api/analytics/bpm-histogram` |
| Release years present | 1992 – 2026 | `/api/analytics/year-histogram` |

Note on one number that reads wrong: the `match_rate: 33.99` in `/api/stats/` is *genre/ML tagging*
coverage, not scrobble matching. Scrobble matching happens to sit at nearly the same value —
17.573 / (17.573 + 35.201) = **33,3 %** — which is a coincidence, not the same measurement.

The 15,6-minute average is the single most important fact about this collection. It is not a library
of songs; it is largely DJ sets, radio shows and podcast episodes. Every design decision below follows
from that.

## What MuMa knows that Spotify does not

1. **Label** — 1.320 of them. Spotify has never once shown a user their top label.
2. **Festival and edition** — `rules_festivals`, `rules_festival_aliases`, `rules_festival_editions`.
   A set can be attributed to *Defqon.1 2024* specifically.
3. **Credit roles** — `library_track_artists.role` is an enum of
   `primary | featuring | remixer | producer | composer`. Top *remixer* is a real query here.
4. **BPM and audio features** — `library_track_audio_features`. Spotify's equivalent endpoint was
   withdrawn for new use in November 2024.
5. **Acquisition** — `library_tracks.created_at` plus `downloads_soundcloud_archive` /
   `downloads_youtube_archive`: when a track entered the library, and which followed channel supplied
   it. Streaming has no equivalent of "you downloaded this on a Tuesday in March".
6. **The unplayed remainder** — a streaming service has no idea what you own and ignore. MuMa does.
7. **Podcasts and radio shows** as a first-class curated entity (`rules_podcasts`).
8. **Release date down to the day** (`migrate_v8_release_date`), which is what the Memories feature
   already rides on.

## Stat catalogue

Feasibility column: **now** = computable from data already in production; **fix first** = needs one of
the collection fixes below; **cheap add** = needs a small amount of new code but no new data.

### The expected core

| Stat | Data | Feasible |
|---|---|---|
| Tracks played in 2026 | `scrobble_listens` + `scrobble_unmatched_listens` | now |
| Unique tracks / artists / genres / labels | same, joined to library | now |
| Minutes listened | requires real played seconds | **fix first** (see B) |
| Top 5 tracks | listens grouped by `track_id` | now |
| Top 5 artists | `library_track_artists` role `primary`; for unmatched rows, raw `artist_name` | now |
| Top 5 genres | `library_track_genres` | now, at 19,93 % coverage |
| First and last listen of the year | `MIN`/`MAX(listened_at)` | now |
| Busiest day, busiest hour, weekday profile | `listened_at` | now |
| Month-by-month curve | `listened_at` | now |
| Longest daily streak | `listened_at` | now |

Top artists deserve a note: they can be computed **without** a library match, because
`scrobble_unmatched_listens` keeps `artist_name` and `track_title` verbatim. Two thirds of the
listening history is unmatched, but it is not unusable — it is unusable only for anything that needs
BPM, label or genre. Build artist- and title-level stats over the union of both tables and the
sample size triples.

### The ones only MuMa can do

| Stat | Idea | Data | Feasible |
|---|---|---|---|
| **Label of the year** | "Your 2026 belonged to Dirty Workz." | `library_track_labels` | now, needs a blocklist (see E) |
| **Festival of the year** | "You spent 41 hours at Defqon.1 without leaving the house." | festival tags + editions | cheap add |
| **Time travel** | Oldest edition played: a Thunderdome set from 1996 alongside a 2026 one. | festival editions + release date | cheap add |
| **Top remixer** | The name Spotify never credits. | `library_track_artists.role = remixer` | now |
| **Your BPM** | Average BPM of the year, and the curve across the twelve months. | `library_track_audio_features.tempo` | now, at 27,35 % coverage |
| **Fastest and slowest** | The 200 BPM outlier and the one downtempo lapse. | same | now |
| **Taste vs. shelf** | Your collection peaks at 150–160 BPM. Did you actually *listen* faster or slower than you buy? | listens × BPM histogram | now |
| **Sets vs. tracks** | "63 % of your listening time was not songs at all." Split by duration threshold. | `duration_secs` | fix first (B) |
| **Show of the year** | Top podcast / radio series. | `rules_podcasts` | cheap add |
| **Release-year spread** | You played music from 1993 to 2026 in the same year. | release date | now |
| **Fresh vs. stock** | Share of plays that came from tracks acquired in 2026. | `library_tracks.created_at` | now |
| **The long wait** | A track you downloaded in 2019 and finally played in 2026. | `created_at` vs first listen | now |
| **Impulse score** | Median time between download and first play. "Six days. Your record is three minutes." | download archive vs first listen | now |
| **Supply chain** | Downloads this year by source, and the followed channel that fed you most. | `downloads_*_archive` | now |
| **The 0,3 %** | "Your library is 325.101 tracks. You touched N of them. Here is the rest." Brutal, honest, and no streaming service would ever ship it. | library vs distinct played | now |
| **Rating year** | Ratings given, share of plays that were 5-star, your harshest week. | `rating_tracks.created_at` | now |
| **Contradiction** | "You rated this a 2 and played it fourteen times." | ratings × listens | now |
| **New genre unlocked** | Genres whose first-ever listen falls in 2026. | listens × genres | now |
| **Discovery of the year** | Artist first heard in 2026 with the most plays after. | listens | now |
| **The loyal one** | Artist played in the most *distinct months* — consistency instead of volume. Usually a different name than the top-5, which is what makes it worth showing. | listens | now |
| **One-hit fever** | Artist whose plays all land inside a single day. | listens | now |
| **Two of you** | `user` and `someuser` both exist. Shared tracks, and the one record only you defended. | listens per user | now, thin (someuser has 0 ratings) |
| **Night shift** | Share of listens between 00:00 and 05:00. | `listened_at` | now |
| **Seasons** | Dominant genre per season. "Your summer was uptempo, your winter was raw." | listens × genres | now |
| **Longest session** | Consecutive listens with gaps under 15 minutes. | `listened_at` | now |
| **Word of the year** | Most frequent word in the titles you played — *Remix*, *Edit*, *Live*, *ID*. | titles | now |
| **Unidentified** | How many "ID - ID" tracks you played without ever learning what they were. | titles | now |
| **Seven years** | The collection holds 220.940.567 seconds. Start now, never sleep, finish in 2033. | summary | now |
| **MuMa's own year** | Scans run, files tagged, downloads, news bulletins produced, jobs failed. The system gets a Wrapped too. | `events`, `jobs` | cheap add |
| **Car mode** | Hours driven to hardstyle. | device on the listen | **fix first** (D) |

## What blocks it

### A. Two thirds of listening history never resolves to a track

17.573 matched against 35.201 unmatched. `scrobble_rematch.py` already runs as a background thread
from `main.py:124`, so this is not an unstarted job — it is a plateau. A large share of the unmatched
rows are imported LMS/ListenBrainz history for music that is not in the library at all, and those will
never match by design.

Consequence: accept it. Design the Wrapped so that artist- and title-level cards read from both
tables, and only the BPM/label/genre cards require a match. Report the coverage honestly on the page
rather than pretending.

### B. The real played duration is thrown away

`services/music-management-server/src/libs/services/scrobbling/impl/musicmanagement/MusicManagementBackend.cpp:70`:

```cpp
void MusicManagementBackend::sendScrobble(const Listen& listen, const Wt::WDateTime& timePoint, std::optional<std::chrono::seconds> duration)
{
    (void)duration;
```

LMS receives how long the track was actually played and discards it before the payload is built. The
Subsonic path is worse: `MediaAnnotation.cpp:198` calls `listenFinished({...})` with no duration
argument at all, so mobile plays carry no listened-seconds even inside LMS.

Consequence: **"minutes listened" cannot be computed today.** The fallback — plays × `duration_secs` —
is fiction for this collection specifically, because the average track is 15,6 minutes. A 90-minute
festival set sampled for four minutes would count as 90. Every duration-derived stat (minutes
listened, sets vs. tracks, hours per festival) depends on fixing this.

### C. Mobile only scrobbles a track it played to the end

`MediaPlayerManager.kt:133` submits on `MEDIA_ITEM_TRANSITION_REASON_AUTO` — the previous track ended
by itself — and `:290` on `STATE_ENDED`, the whole queue finishing. A manual skip to the next track
never submits.

Consequence: with 15,6-minute average tracks, most mobile plays end in a skip, and Android Auto is
where skipping is most likely. Mobile listening is systematically under-recorded, and the bias is not
random — it under-counts exactly the long sets that dominate the collection.

### D. Every listen looks like it came from the same place

`MusicManagementBackend.cpp:91` hardcodes `payload["source"] = "lms"`. Mobile, car mode, the web
player and a desktop browser are indistinguishable in `scrobble_listens.source`. The Subsonic client
identifier (`c=`) is already on every mobile request and is simply not forwarded.

Consequence: no device split, no car-mode stat — unless it is wired up before the listening window
closes.

### E. Top labels are polluted

`/api/analytics/top-labels` currently returns `Soundcloud` (132.037), `Youtube` (30.779), `Telegram`
(1.556) and `__TODO` (1.243) among the leaders. These are acquisition sources and a placeholder, not
labels. The first genuine label is *Dirty Workz* at 2.299.

Consequence: a "label of the year" card needs a blocklist, or it will proudly announce that your
favourite record label is SoundCloud.

### F. Coverage caps some cards

BPM 27,35 %, genre 19,93 %. Those cards describe a quarter to a fifth of the library. That is enough
for a headline figure but the page should say what it is based on.

## Sequencing

The distinction that matters: **collection fixes are dated, presentation is not.**

Fix forward, before the listening window closes (B, C, D). Every week that passes is a week of 2026
that can never carry played-seconds or a device label. These are small, contained changes — forward
one already-available value in the C++ payload, add one Subsonic parameter, change the mobile submit
condition — and they are the difference between a Wrapped built on real listening time and one built
on multiplication.

Fix any time, including in December (A partial, E, F, and the whole page). Rematching, label
blocklists and the aggregation endpoint all work retroactively on data already stored.

## Delivery sketch

Not decided, but the obvious shape: a `/wrapped/2026` route in the Svelte frontend, built on the card
and year-tile pattern the Memories feature already ships (`services/frontend/src/lib/memories.js`,
routes in `router.js`), fed by a new `GET /api/analytics/wrapped?year=&user=`. The aggregation scans
listens against a 325.101-row library, so it should be precomputed into a table rather than run per
request — it changes once a year.

There is no listening-analytics endpoint of any kind today: `/api/analytics/*` covers the library
only (`summary`, `genre-distribution`, `bpm-histogram`, `year-histogram`, `top-artists`, `top-labels`,
`artist-search`). Everything listening-shaped is new surface.

## Open questions

- Scope: user-facing feature for both users, or a personal page for `user`? `someuser` has zero ratings,
  which makes the shared cards thin.
- Web only, or also a mobile screen? Car mode is where the listening happens but not where a Wrapped
  is read.
- Does Wrapped count *matched listens only* (honest but small) or *all listens* (larger, with
  artist-level cards only)? Recommendation: all listens, with per-card coverage stated.
- How much of the pre-2026 history should be usable — is a 2026-only Wrapped the goal, or an
  all-time "your library so far"?

## The one measurement not taken

Listens per year is the number that decides how rich a 2026 Wrapped can be, and it is not exposed by
any endpoint. Direct database access from this session was blocked, so it was not measured. On the
production host:

```sql
SELECT YEAR(listened_at) AS y, username, COUNT(*) AS listens,
       COUNT(DISTINCT track_id) AS tracks
FROM scrobble_listens GROUP BY y, username ORDER BY y DESC;

SELECT YEAR(listened_at) AS y, username, COUNT(*) AS unmatched
FROM scrobble_unmatched_listens GROUP BY y, username ORDER BY y DESC;
```

If 2026 to date holds only a few thousand listens, the honest move is to widen the page from "your
2026" to "your library so far" and let the collection, acquisition and rating stats carry it — those
have years of depth regardless of what the scrobbler managed to record.
