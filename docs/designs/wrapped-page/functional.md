# MuMa Wrapped Page — Functional Design

The year-in-review page for issue #60. It shows one year (or a range you pick) in two tabs:

- **MuMa User**: your own listening year.
- **MuMa Library**: the year of the whole server, all listeners together, plus what the collection
  and the system did.

The page is the same Svelte page in the browser and in the Android app, because the app shows the
web bundle. It takes its look from the MuMa style guide, with the full-screen, one-number-per-card
rhythm of Spotify Wrapped and the dense, chart-heavy cards of ListenBrainz Year in Review.

The data groundwork (played seconds, listen origin, channels as their own thing) is in
[../wrapped/](../wrapped/functional.md). The candidate stats and why they matter are in
[../wrapped/research.md](../wrapped/research.md). This design uses every stat from that research. The
exact definition and data source of each card are in [technical.md](technical.md).

## What the data supports, measured on production on 2026-11-12

These numbers decide what the page can say honestly. They are why many cards carry a coverage line.

| Fact | Value |
|---|---|
| Listens in 2026 linked to a library track | 20.532, by 5 accounts |
| Listens in 2026 not linked to a track | 29.360, by 2 accounts |
| Linked 2026 listens that measured their played seconds | 5.044 (25%) |
| Linked 2026 listens with a known origin (web, phone, car) | 6.321 (31%); the rest are imports or older rows |
| Linked 2026 listens by form | 19.759 tracks, 406 sets, 318 live sets, 49 podcast episodes |
| Years with any listens | 2024 (4.779), 2025 (7.329), 2026; 2024 and 2025 are one account only |
| Tracks in the library | 358.857 |
| Tracks with a BPM | 292.943 (82%) |
| Tracks released in 2026 that are in the library | 27.020 |
| SoundCloud downloads recorded in 2026 | 99.787 |
| YouTube downloads recorded in 2026 | 31.038 (53.658 older rows have no date) |
| Track credits with the role `remixer` | 0 (only `primary` and `featuring` are written) |

Four facts limit what the page can show:

1. **No arrival date.** Every `library_tracks` row was created in 2026, because the library was
   rebuilt from July 2026. File dates were rewritten by the tagger. So "added to the collection in
   2026" has no source today for label releases and manual imports. Only the download archives keep
   a real date, and only for SoundCloud and YouTube.
2. **Ratings restart in July 2026.** The ratings table was rebuilt on 2026-07-04, so a rating's date
   is its rebuild date, not the day someone gave it.
3. **Most events expire.** The event log keeps `INFO` for 14 days and `ERROR` for 90. A count of a
   whole year of jobs is only possible for what durable tables keep.
4. **No remixer credits.** The scanner writes only primary and featuring artists to the database, so
   a remixer ranking has no source.

## Navigation

| Situation | Observable outcome |
|---|---|
| You open Wrapped from the sidebar (web) or the Library tab (app) | The MuMa User tab for the current year opens |
| You open Wrapped in December or January | A Wrapped tile also shows on the home screen, next to Memories |
| You switch to the MuMa Library tab | The same period shows for the whole server; the address changes so a link opens that tab |
| You choose another year | Both tabs change to that year; only years with listens are offered |
| You choose "Custom range" and pick two dates | Both tabs show that range; the title says the dates instead of a year |
| The year is still running | The title says "2026 so far" and the date the figures run to |
| You open a link to a Wrapped page from someone else | You see your own User tab for that period, never theirs |
| You press back on the phone | You leave Wrapped, like any other page |

## Layout

The page is a vertical run of cards. Each card has one headline (a number or a name), one sentence,
and at most one chart or list.

- **On a phone**, each card fills the screen and the page snaps from card to card. It feels like a
  story without a separate story mode.
- **On a wide screen**, the cards sit in a two-column grid, with the hero cards at full width.
- The first card of each tab is a title card: the period, the headline total and a one-line summary.
- The last card of each tab is the coverage card. It says which part of the data each card used.
- A card that has nothing to say is not shown. The coverage card lists how many cards were left out
  and why.
- A card's color comes from the genre that leads it, where one does (the genre tints the rest of
  MuMa already uses). Other cards use the panel surfaces and the brand accent.
- A track, artist or label on a card opens its own page. A top-tracks list has a play button that
  queues the list.

## Cards in the MuMa User tab

In the order they appear. "Linked only" means the card counts listens that are linked to a library
track, and says how many listens it could not count.

| Card | What it says | Counts |
|---|---|---|
| Title | "Your 2026": listens, distinct tracks, estimated listening time | All listens |
| Listening time | Measured minutes, estimated minutes, and the share that was measured | All listens; labeled an estimate |
| Top tracks | Your five most played tracks, with plays, playable | Linked only |
| Top artists | Your five most played artists | Linked only |
| Top genres | Your five most played genres; the bars overlap | Linked only |
| Your seasons | The leading genre in each season | Linked only |
| Label of the year | The label you played most, real labels only | Linked only |
| Channel of the year | The SoundCloud or YouTube channel whose uploads you played most | Linked only |
| Top remixer | The remixer credited on most of your plays | Blocked: see Decision 12 |
| Festival of the year | The festival whose sets you played most, with hours | Linked only |
| Time travel | The oldest and newest festival edition you played | Linked only |
| Show of the year | The podcast or radio show you played most | Linked only |
| Sets vs. tracks | How your plays and time split between tracks, sets, live sets and podcasts | Linked only |
| Your BPM | Your average tempo and its curve over the months | Linked only, tracks with a BPM |
| Fastest and slowest | The fastest and the slowest track you played | Same |
| Taste vs. shelf | Your listening tempo next to the tempo of the whole collection | Same |
| Your clock | Listens per hour of the day and per weekday, in your time zone | All listens |
| Night shift | The share of listens between 00:00 and 05:00 | All listens |
| Busiest day | The day with the most listens | All listens |
| First and last | The first and the last listen of the period | All listens |
| Month by month | Listens per month | All listens |
| Longest streak | The most days in a row with at least one listen | All listens |
| Longest session | The longest unbroken listening session | All listens |
| Where you listened | Web, phone, car and imported, with hours in the car | All listens; origin known only since August 2026 |
| Release-year spread | The oldest and newest release you played, and plays per decade | Linked only, tracks with a release date |
| Fresh vs. stock | The share of plays from music that arrived this year | Partial: see Decision 3 |
| The long wait | A track that waited longest between arrival and first play | Partial: see Decision 3 |
| Impulse score | Median time from arrival to first play | Partial: see Decision 3 |
| The 0.3% | How many of the library's tracks you played, and how many you never touched | Linked only |
| New genre unlocked | Genres you played for the first time ever | Linked only |
| Discovery of the year | The artist first heard this period with the most plays after | Linked only |
| The loyal one | The artist you played in the most different months | Linked only |
| One-hit fever | An artist whose plays all fall on one day | Linked only |
| Your ratings | Ratings you gave, the split per star, the share of plays that were 5-star tracks | Your ratings |
| Contradiction | A track you rated 1 or 2 and still played often | Linked only |
| Word of the year | The most frequent word in the titles you played | All listens |
| Unidentified | Plays of "ID - ID" tracks | All listens |
| Only you | Your most played track that no other listener played, and how many of your tracks others also played | Linked only; see Decision 7 |
| Coverage | What each card was based on, and the cards left out | Always shown |

## Cards in the MuMa Library tab

| Card | What it says | Counts |
|---|---|---|
| Title | "MuMa in 2026": listens, listeners, distinct tracks, estimated listening time | All listens, all accounts |
| Listeners | Active accounts, and former listeners whose account is deleted | All accounts, including `deleted-<id>` rows |
| Top tracks, artists, genres, labels | The server's five of each | Linked only |
| Most shared | The track played by the most different listeners | Linked only |
| The server's clock | A weekday-by-hour heat map of all listening | All listens |
| Where MuMa was played | Web, phone, car, imported | All listens |
| Sets vs. tracks | The server-wide split | Linked only |
| Festivals | Hours of festival sets played, and the festival editions in the collection from this year | Linked only; collection |
| Releases of the year | How many tracks released this year are in the collection, and the labels that released most of them | Collection, tracks with a release date |
| Downloads | Downloads per month and per platform, and the followed channel that delivered most | Download archives; see Decision 3 |
| Collection growth | Tracks that arrived this year, by source | Partial: see Decision 3 |
| The shelf | The collection's BPM curve and its genre spread | Collection |
| Start now | The total length of the collection (316.103.088 seconds, about ten years), and the date you would finish it if you started now | Collection |
| The unplayed | How much of the collection nobody played this period | Collection, linked listens |
| MuMa's own year | BPM measurements done, news bulletins made, ratings given, critical alerts raised | Durable tables only |
| Coverage | As in the User tab | Always shown |

The Library tab never names a listener. It counts accounts, and it shows tracks, artists and labels.

## Empty and partial states

| Situation | Observable outcome |
|---|---|
| You have no listens in the period | The User tab shows one card: "No listens in this period", with a link to Listening stats and to the ListenBrainz import |
| The server has no listens in the period | The Library tab still shows the collection cards; the listening cards are left out |
| A card does not reach its minimum (for example fewer than three distinct artists) | The card is left out; the coverage card says so |
| A card is blocked by missing data (arrival date) | The card is left out; the coverage card says which data is missing |
| A card's data is partial (BPM on 82% of tracks) | The card shows, with a line such as "Based on 4.120 of 5.044 plays" |
| The figures are still being computed | The cards show skeletons; the page never shows zeros in their place |
| The server cannot be reached | The page says Wrapped is unavailable, with a retry |
| One card's data is missing from the answer | Only that card is left out |

## Sharing

A card can be shared as an image, drawn by the page itself (Decision 5). A shared image:

- shows only the card's headline, its sentence, the period and the MuMa mark;
- never shows a username, a server address or another listener's data;
- on the phone, goes to the Android share sheet; on the web, downloads as a PNG file.

## Acceptance Criteria

1. Wrapped opens from the sidebar on the web and from the Library tab in the app, on the User tab of
   the current year.
2. The tabs MuMa User and MuMa Library each have their own address, and a reload keeps the tab and
   the period.
3. The year choice lists only years with listens; a custom range shows the chosen dates as the title.
4. A running year is titled "so far" and states the date its figures run to.
5. The User tab shows only the reader's own listens, also when the address names another period or
   tab.
6. The Library tab counts every account's listens, including those of deleted accounts, and names no
   listener.
7. Every card that counts linked listens only says so, with the number of listens it could not count.
8. Listening time is labeled an estimate, with the measured share beside it.
9. Hours and days are in the reader's time zone.
10. A card without enough data is left out, and the coverage card lists it with the reason.
11. A track list on a card plays from its play button.
12. On a phone, each card fills the screen and the page snaps between cards; on a wide screen the
    cards sit in a grid.
13. A shared card image carries no username and no server address.
14. The page loads in under two seconds for a period that was computed before.

## Decisions

Teun accepted every recommendation below on 2026-11-12. The options stay listed so the reasons
stay readable.

1. **Which listens count?**
   - (a) Totals and the clock over all listens, rankings over linked listens only, as Listening stats
     does.
   - (b) Linked listens only, everywhere.
   - (c) All listens everywhere, ranking unlinked listens on their raw artist and title text.

   Decided 2026-11-12: (a). It matches the Listening stats page, so the two pages never disagree, and
   rankings on raw text would list the same artist under several spellings.

2. **How do the two tabs present on the phone?**
   - (a) One scrolling page per tab, each card a full screen, with scroll snap.
   - (b) A separate tap-through story mode (Spotify), plus the scrolling report (ListenBrainz).
   - (c) A scrolling report only, cards at their natural height.

   Decided 2026-11-12: (a). It gives the story feel with one layout to build and test. A story mode can
   come later on the same card components.

3. **Where does "arrived this year" come from?** Fresh vs. stock, The long wait, Impulse score and
   Collection growth need it, and no table has it.
   - (a) Add an arrival date to each track, written by the scanner when it first sees a file,
     backfilled from the download archives where they match. Label releases from before the rebuild
     stay unknown.
   - (b) Use only the download archives, so these cards cover SoundCloud and YouTube downloads and
     say so.
   - (c) Leave the four cards out of 2026 and start them for 2027.

   Decided 2026-11-12: (a), shown with its coverage. Every week without it loses arrival dates for
   good, the same lesson as the played-seconds fix.

4. **How are figures computed and kept?**
   - (a) A snapshot per account and period, computed on first request and refreshed at most once a
     day while the period is running; a closed year is frozen.
   - (b) Computed live on every request.
   - (c) A nightly job that computes every account's current year in advance.

   Decided 2026-11-12: (a). The listening side is small (50.000 rows a year), but the collection cards
   scan 358.857 tracks. A frozen year also stops a later rematch from changing a shared image.

5. **How is a card shared?**
   - (a) The page draws the card on a canvas in the browser and shares it: the Web Share API or a
     download on the web, a new `share` call in the app's system plugin on Android.
   - (b) Screenshots only; no share button.
   - (c) The server renders the image.

   Decided 2026-11-12: (a). No new dependency, no image rendering on the server, and the app gets the
   real share sheet. It needs one small change to the Android app.

6. **Which periods are offered?**
   - (a) Calendar years with listens, plus a custom range.
   - (b) Calendar years only.
   - (c) Years, a custom range, and "all time".

   Decided 2026-11-12: (a). "All time" is what Listening stats already shows.

7. **May the User tab compare you with other listeners?** The "Only you" card says that nobody else
   played a track, which tells you something about the others.
   - (a) Yes, as counts only: "nobody else played this", "4 of your tracks others played too".
   - (b) No; leave the card out.
   - (c) Yes, and name the listener you share most with.

   Decided 2026-11-12: (a). It never names anyone, and five accounts is too few for (c) to stay
   anonymous.

8. **Which time zone does a snapshot use?**
   - (a) The reader's own zone, sent by the page, stored with the snapshot.
   - (b) One server zone (Europe/Amsterdam) for everybody.

   Decided 2026-11-12: (a) for the User tab, as Listening stats does. The Library tab uses the server zone
   from the configuration, so every reader sees the same server figures.

9. **Who may see the Library tab?**
   - (a) Every signed-in account.
   - (b) Administrators only.

   Decided 2026-11-12: (a). It names nobody, and the collection is what every listener shares.

10. **Does a former listener (`deleted-<id>`) count as a listener?**
    - (a) Yes, in totals and in the listener count, shown as "former listeners".
    - (b) In totals only, not in the listener count.

    Decided 2026-11-12: (a). Their listens are part of the year, and the count says plainly what they
    are.

11. **When does the home tile appear?**
    - (a) From 1 December to 31 January, on the web and in the app, switchable in settings like the
      Memories tile.
    - (b) Never; the sidebar and Library entries only.
    - (c) All year.

    Decided 2026-11-12: (a).

12. **Where does the remixer come from?**
    - (a) The scanner writes the file's `REMIXER` tag as the credit role `remixer`; the next full scan
      fills it for the whole library.
    - (b) Wrapped reads the remixer from the played titles ("(Sub Zero Project Remix)") when it
      computes the card.
    - (c) Leave the card out.

    Decided 2026-11-12: (a). The tagger already writes `REMIXER`, so the scanner only has to read it, and
    every other page that lists credits gains it too. (b) is a fallback if the scan cannot run before
    January.
