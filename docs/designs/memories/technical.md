# Memories — Technical Design

Implements [`functional.md`](functional.md).

## Where this lives, and why

The whole feature is served by `music-management-server` (LMS) and consumed over Subsonic by both clients.
Three facts force that placement:

- LMS already stores per-track release dates: `Track::_date` and `Track::_originalDate`, both
  `core::PartialDateTime`, mapped to the `date` and `original_date` columns of the `track` table
  (`src/libs/database/include/database/objects/Track.hpp`). No other component has this data.
- Only LMS can hand out playable identifiers. `music_manager`'s `library_tracks.track_uid` is a SHA-256 of
  title/duration/artist (`services/music_manager/routers/scanner.py`), which no client can resolve to a
  stream.
- Both clients already speak Subsonic against LMS, and the codebase has a precedent to follow: the
  `spotify:*` virtual playlists in `src/libs/subsonic/impl/endpoints/Spotify.cpp`, registered in the
  endpoint map of `SubsonicResource.cpp` and consumed by the web UI over `/rest/…`.

Putting it in `music_manager` instead would mean duplicating release dates into MariaDB and inventing a
path-based mapping back to LMS track ids for playback. That is rejected.

The follow-up MusicBrainz/Discogs enrichment fits this placement without change: enrichment writes the
`DATE`/`ORIGINALDATE` tag, the LMS scanner picks the tag up, and Memories fills out on its own.

## Data Model

No schema change, in any database.

`PartialDateTime` is persisted as its `toString()` form by
`src/libs/database/impl/traits/PartialDateTimeTraits.hpp`, so `date` and `original_date` are strings whose
length reflects their precision: `"2018"` for year precision, `"2018-08"` for month, `"2018-08-02"` and
longer for day precision or finer. Two consequences the implementation depends on:

- Day precision is testable as `LENGTH(x) >= 10`, which is what excludes year-only and year-month tags from
  Memories (functional criterion 6) without a separate precision column.
- The month-day of a day-precision value is `SUBSTR(x, 6, 5)`, i.e. `'MM-DD'`.

The effective release date of a track is `original_date` when present, else `date`.

## Query Layer

New static on `db::Track` (declared in `objects/Track.hpp`, implemented in `impl/objects/Track.cpp`
alongside the existing `createQuery` helpers):

```cpp
static RangeResults<TrackId> findIdsByReleaseAnniversary(
    Session& session,
    const ReleaseAnniversaryParameters& params);
```

with

```cpp
struct ReleaseAnniversaryParameters
{
    unsigned month{};           // 1-12, the client's local date
    unsigned day{};             // 1-31
    unsigned windowDays{ 3 };   // days either side
    int currentYear{};          // releases from this year and later are excluded
    std::optional<Range> range;
};
```

The window is expanded in C++ into the set of `'MM-DD'` strings it covers and bound as an `IN (...)` list.
Doing the arithmetic in C++ rather than SQL is deliberate: it makes the month boundary (1 January reaching
back to 29 December) and 29 February ordinary list construction instead of dialect-specific date maths, and
it keeps the generated SQL a plain string comparison against an index-friendly expression.

29 February is handled by generating from a leap year, so that a window around 28 February or 1 March
includes 29 February releases in every year.

Ordering is effective-year descending, then artist name, then track name. The current year and any later
year are excluded by comparing the leading four characters of the effective date against `currentYear`.

Grouping into years is done by the endpoint, not the query: the query returns an ordered flat list.

## API Contract

One new Subsonic extension endpoint, in a new `src/libs/subsonic/impl/endpoints/Memories.cpp` /
`Memories.hpp`, registered in the endpoint map of `SubsonicResource.cpp` next to the existing Spotify
extensions.

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /rest/getMemories` | Standard Subsonic auth parameters, plus `date` (optional, `YYYY-MM-DD`), `windowDays` (optional, default 3, clamped to 0–14), `maxPerYear` (optional, default 30, clamped to 1–1000), `year` (optional: answer for that release year alone) | `subsonic-response` containing a `memories` node with zero or more `memory` array children | Malformed `date` or non-numeric `windowDays`/`maxPerYear`: standard Subsonic error code 10 (required parameter missing / invalid). Auth failures use the standard Subsonic codes, unchanged. No matches is **not** an error: `memories` is present and empty |

`date` defaults to the server's local date. Clients send their own local date so that a device in another
time zone gets its own "today" (functional criterion 12).

Each `memory` node carries:

| Attribute | Meaning |
|---|---|
| `kind` | `"release"` in this iteration. Present from day one so a later "first listened" memory is an additional `kind` rather than a breaking change |
| `year` | The release year of the group |
| `yearsAgo` | `requestYear - year`, always >= 1 |
| `exact` | `true` when at least one track in the group matches the request's month-and-day exactly, `false` when the group only exists because of the window. Drives the "today" versus "this week" wording |
| `songCount` | The year's full size, **before** `maxPerYear` truncated it, so a client can say how big the year is while holding only a page of it. The number of `song` children says how much of that year this answer carries |
| `cover` | Up to four `{id}` children: distinct cover art from anywhere in the year, best-ranked first. A tile draws a mosaic, and the tracks that rank highest are frequently the ones without artwork -- a label release carries an embedded cover far less often than a rip does -- so a mosaic built from the page alone goes blank exactly for the years worth showing. Empty when the year has no artwork at all |

and contains `song` array children produced by the existing `createSongNode(ctx, track, true)` helper used by
`Spotify.cpp`, so the entries are ordinary Subsonic songs that both clients can queue and play without a
second lookup.

Within a group, tracks are ordered by what the requesting user values most -- a five-star favourite first,
then the listen count -- and `maxPerYear` truncates after that ordering. A client showing only the head of a
group therefore shows the best of the year rather than whichever tracks the query returned first. Tracks the
user treats identically are separated by the date, which preserves the original guarantee that an exact
anniversary is never dropped in favour of a near miss; a full tie falls back to the track id so that two
identical requests cannot return the same year in a different order.

Most of a year is neither rated nor played -- measured on the production library on 2026-08-23, none of that
day's 3.600 candidate tracks were -- so a third key decides there: how deliberate the release is, read from
its label names. The scanner stores the publisher tag as a label, and the downloaders write the platform into
that tag, which makes "which label" double as "where did this come from". Highest first: a real label, no
label at all (often a release whose publisher was never matched), `Free&None` (a giveaway rather than a label
release), `Soundcloud`, `Youtube`, `Telegram`, `TODO` (the import pile, not a release). Leading underscores
and capitalisation are ignored, since the same placeholder exists with two and three underscores; a release
with several labels takes its best one. This key sits below the listen count deliberately: it is a fallback
for a year nobody has touched, not a reason to bury a track the listener plays.

The ranking needs a rating and a play count per candidate track, which are two service calls each. `year` is
what keeps that bounded: a client asking for one year pays for one year, and the filter is applied before the
lookups rather than after.

This is a new endpoint only. No existing endpoint changes shape, so there is no breaking change for existing
clients.

## Cross-App Impact

Three apps change together, in one commit, per AGENTS.md rule 7.

**`music-management-server`** — the query layer and endpoint described above.

**`frontend`** — `MemoriesView.svelte` renders the year groups as a grid of tiles (`MemoryYearCard.svelte`),
and `MemoriesYearView.svelte` is one year's own page, reusing the existing `TrackList` component for the
tracks (whose default column already shows a track's release date). A `memories` entry in the `menuItems`
array of `Sidebar.svelte` next to Release Radar, a `/memories` path and a `/memories/<year>` argument route
in `router.js`, and the matching `activeView === 'memories'` and `activeView.startsWith('memories:')`
branches in `Dashboard.svelte`. On the home screen, `Dashboard.svelte` gains a
memories carousel above the existing rows, one card per year group capped at ten cards; clicking a card
opens that year's page. Visibility is a new store in `store.js` (`memoriesOnHomeEnabled`,
default `true`) persisted with the existing `persist()` helper, exposed as a toggle in `GeneralSettings.svelte`
next to the deduplication toggle. The sidebar entry is the permanent way in and is not affected by that
toggle.

Response parsing, the request URL, the local-date format and the heading rule live in a shared `memories.js`,
because the overview, the year page and the carousel need them and the rules are the pieces worth testing on
their own. Two more live there for the tiles: `rankSongs`, which turns `userRating` and `playCount` -- both
already on every song node -- into the "favourites first, then listens" order the tiles show, and
`yearTiles`, which reduces a group to its count, its top three and four covers. The ranking now happens on the server, which is what
lets the overview ask for a short page: it requests twelve songs per year -- enough to name three and fill a
four-cover mosaic -- and reads the year's real size off `songCount`. Asking for every year in full instead
made the overview a multi-megabyte download that still could not count a year of 450 tracks correctly.
`rankSongs` stays as the client's own ordering of that short page, which keeps the tiles sensible against a
server too old to rank.
All of it is covered by `tests/unit/memories.test.js` (the frontend does have a Vitest suite, see
`docs/testing-inventory.md`).

The year page fetches for itself rather than inheriting the overview's groups, so that a bookmarked
`/memories/2025` survives a refresh; it asks with `year=` so that one page costs one year instead of all of
them. The tile's play action does the same on click, since the tile itself holds only a page of its year. Because memories are relative to today, the same URL is a different
page tomorrow; the page says so through its own empty state instead of pretending the year is gone.

New user-facing strings go through the existing i18n layer. The `memories` block is translated in all four
locale files under `src/lib/i18n/locales/` (`en`, `nl`, `brabants`, `sallands`); the settings toggle's
strings live under `settings.general` in `en` and `nl` only, because the two dialect files deliberately
translate just a subset of the settings screen and fall back for the rest. Both headings use the i18n
layer's CLDR plural forms (`{ one, other }` keyed on `count`) rather than separate singular keys.

**`muma-mobile`** — `getMemories.view` added to `SubsonicAPIDefinition.kt` with its own response DTOs, in the
same Retrofit style as the surrounding calls.

Memories gets two entry points, and they serve different purposes. The permanent one is a new page in the
Library tab: a `PAGE_MEMORIES` constant in `LibraryPagerAdapter` with its own branch in `createFragment` and
`titleResFor`, alongside genres, labels, years, festivals, lineups and ratings. It is deliberately *not* a
`BrowseCategory` value — that enum drives `FilterBrowseFragment`, which browses tag values, and Memories is
its own screen. This page is the "tab", and it exists whatever the user does with the carousel preference.
The optional entry point is the teaser on home: a `SectionSlot` at the top of `MainFragment` with
`CardStyle.CAROUSEL`, capped at ten cards, fed by a new `MemoriesProvider` whose `load()` returns `null`
when there is nothing to show — the existing contract that hides a section.

A carousel card is one *year*, not one track: a day can hold sixty releases and the strip has to stay
short. That needs a new `HomeCardType.MEMORY`, a `MemoryGroup.toHomeCard(label)` mapper, and a `toMemories`
global action in `navigation_graph.xml` that `HomeCardNavigator` routes those cards to, so tapping one opens
the Memories screen rather than playing anything. The home screen therefore still produces no playable
cards, and `MainFragment` keeps its navigation-only card handling.

The full list is a new `MemoriesFragment`, registered in `navigation_graph.xml`, used both as the Library
pager page and as the destination `HomeCardNavigator` routes a carousel tap to. It is modelled directly on
`FavoritesFragment`: one section per year, cards produced by the existing `Track.toHomeCard()` mapper, taps
routed through `HomeCardNavigator` to `HomeCardAction.PlayTrack` and played with
`MediaPlayerManager.playTracksAndToast`. Nothing about the card or list rendering is new.

One small extension to shared code is unavoidable: `HomeSection.titleRes` is a `@StringRes Int`, and a
memories section title is dynamic ("Today, 8 years ago"). `HomeSection` gains a `titleArgs: List<Any>`
defaulting to empty, and the three places that set a section title — `MainFragment.SectionSlot.showContent`,
`FavoritesFragment.render` and the new `MemoriesFragment` — format with `getString(titleRes, *titleArgs)`.
Existing sections pass no arguments and are unaffected.

Which wording a group gets lives in one place, `memoryHeadingRes`/`memoryHeadingArgs`, because the carousel
card and the screen section must never disagree about whether a group is allowed to say "today".
`MemoriesProvider` takes the finished label as a lambda rather than resolving it itself, which is what keeps
it testable as plain Kotlin with no Android context.

The bottom navigation menu is unchanged and stays at four items. The preference to hide the carousel is
added alongside the existing settings in `Settings.kt`, following the `BooleanSetting` pattern used by
`isSetsMode`, with strings in `strings.xml`.

`music_manager` does not change.

The memory card — the year-group card used by both carousels and by the group headers — is a new visual
component on both clients. Per AGENTS.md rule 14 it is added to [docs/styleguide.md](../../styleguide.md)
before it is implemented, so the web and Android versions are built against one agreed description rather
than drifting apart.

## Error Handling and Degradation

A client talking to a server without this endpoint gets an HTTP 404 or a Subsonic "unknown method" error.
Both clients must treat that exactly like an empty result — no carousel, no error surface. This matters most
for MuMa Mobile, which can be pointed at any Subsonic server. On the Android side this falls out of returning
`null` from the section provider's `load()`; the existing `safely()` helper in `HomeSectionProvider.kt`
already swallows the throw.

## Technical Acceptance Criteria

1. `findIdsByReleaseAnniversary` returns a track whose `original_date` is `YYYY-08-02` when queried for
   month 8, day 2, for every year before the request year.
2. It falls back to `date` when `original_date` is empty, and prefers `original_date` when both are set.
3. It excludes tracks whose effective date is year-only (`"2018"`) or year-month (`"2018-08"`), at any window
   size.
4. It excludes tracks whose effective year equals or exceeds the request year.
5. Querying month 1, day 1 with `windowDays = 3` returns tracks dated 29, 30 and 31 December of earlier
   years as well as 2, 3 and 4 January.
6. Querying month 2, day 28 with `windowDays = 3` returns tracks dated 29 February in leap years.
7. Results are ordered by effective year descending.
8. `GET /rest/getMemories` with no matching tracks returns a success response with an empty `memories` node,
   not an error.
9. `GET /rest/getMemories?date=2020-13-45` returns Subsonic error code 10.
10. `windowDays=999` is clamped to 14 and `maxPerYear=0` is clamped to 1, rather than rejected;
    `maxPerYear=9999` is clamped to 1000.
11. A `memory` node has `exact="true"` if and only if at least one of its songs matches the requested
    month-and-day exactly.
12. `maxPerYear` truncation never removes an exact-date match while an equally-loved window match remains in
    the same group.
13. Every `song` child validates as an ordinary Subsonic song entry and its `id` can be streamed via
    `/rest/stream`.
14. The MuMa Mobile response DTOs parse a two-group response, including the `kind`, `exact` and `yearsAgo`
    attributes, in a JVM unit test.
15. When the API call fails or returns no groups, the MuMa Mobile home section provider returns `null` and no
    memories carousel is rendered.
16. With the home preview preference off, the carousel is absent on both clients after a restart/reload,
    while the sidebar entry (web) and the Library pager page (Android) still open Memories.
17. `./scripts/test/lms-unit.sh`, `./scripts/test/android-unit.sh` and `./scripts/test/frontend-unit.sh` pass.
18. `./scripts/test/contracts.sh` covers `/rest/getMemories` returning a well-formed success response against
    the test stack.
19. A year is ordered five-star favourites first, then by listen count, then by how deliberate the release
    is, so truncation keeps the best of the year rather than the head of the query.
20. `songCount` reports the year's size before truncation, so a group truncated to twelve of four hundred
    still says four hundred.
21. `year=2025` answers with that year alone, and with an empty `memories` node when it holds nothing.
22. `sourceRank` places a label release above an unlabelled one, above `Free&None`, above `Soundcloud`,
    above `Youtube`, above `Telegram`, above `TODO`, ignoring case and leading underscores.
23. A group carries up to four distinct `cover` children even when none of the tracks on its page has
    artwork, because they are collected from the whole year rather than from the page.

## Related Docs

- [functional.md](functional.md) — user-observable behaviour and acceptance criteria.
- [../../architecture.md](../../architecture.md) — the data boundary
  between `music_manager` and LMS that determines where this feature lives.
- [../favorite-genres/](../favorite-genres/) — precedent for a client-side, persisted display preference.

This document is the endpoint's contract. It is not repeated in
[docs/api-specification.md](../../api-specification.md), which covers the `music-manager` API; the existing
LMS Subsonic extensions are not described there either.
