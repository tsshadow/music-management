# Personalized Feeds (Release Radar & Daily Mix) — Functional Design

> Status: agreed in a brainstorm on 2026-09-05. **No numbers in this document have been measured
> against production.** The "Open Questions" section lists what has to be measured before the
> technical design is written; several of those measurements can still invalidate the chosen
> parameters (most of all the seven-day window).

## Overview

MuMa knows what the listener plays, what they rated, and when a track was released. It does not yet
turn any of that back into something to listen to. This feature adds two feeds:

- **Release Radar** — what came out this week, filtered and proportioned by the listener's taste.
- **Daily Mix** — a varied daily selection from the same taste, over a wider window, leaning on
  tracks they have never played and tracks they rated highly.

Both are built by one ranker with two parameter sets, so a third feed, or a different window, is a
configuration change rather than a new implementation.

The feature is for the listener on the home screen of the mobile app and on the web, and it must be
honest above all: every way this can fail — a thin profile, missing release dates, missing genre
tags — looks identical from the outside, namely a short or empty list. A feed that quietly widens
its window, or falls back to random music, to avoid looking empty is worse than one that says it has
nothing.

## User Stories

- As a listener, I want to see what was released this week in the styles I actually play, so that I
  do not have to scan every new release in a 300.000-track library by hand.
- As a listener, I want a small share of my taste (say 10% hard techno) to still be visible in that
  list, so that the feed does not collapse into the one genre I play most.
- As a listener, I want a daily mix that mostly offers me things I have never played plus the tracks
  I rated highly, so that the library keeps surfacing what I forgot I had.
- As a listener, I want to see which artists, labels and genres the feeds think I like, and be able
  to exclude one, so that a single wrong signal does not poison every feed.
- As a new listener on this server, I want a usable feed before I have any listening history, so
  that the app is not empty on the day I install it.
- As a listener, I want to be told when a feed is empty because nothing matched, so that I do not
  mistake a broken feed for a quiet week.

## Functional Flows

### The taste profile

| Situation | Observable outcome |
|---|---|
| The listener played tracks in the last 90 days | Their profile is the artists, labels and genres of those tracks, weighted by how recently and how fully each was played |
| A track carries a genre and that genre's parent (Uptempo and Hardcore) | The listen counts once, at the deepest genre — Uptempo gets the weight, Hardcore gets nothing from it |
| A track carries only the parent genre (Hardcore) | Hardcore gets the weight; it is the finest information available for that track |
| A track was matched to the listening history by a weak match (a base title, or a fuzzy match) | It still counts, but for less than an exact match |
| A genre is too small for a share of its own | It rolls up into its parent genre rather than into a catch-all bucket |
| The listener excludes an artist, label or genre | It stops contributing to both feeds immediately |
| The listener has played almost nothing | Their own profile is blended with the server's profile, weighted towards the server |

### Release Radar

| Situation | Observable outcome |
|---|---|
| Tracks were released in the last seven days | All of them are in the running — recency selects, the profile only divides the places |
| The profile is 50% Uptempo, 25% Raw, 10% Hard Techno | Roughly half the places go to Uptempo, a quarter to Raw, and Hard Techno gets its own handful rather than being crowded out |
| No track in a share was released this week | Those places are handed to the next largest share; no place is left empty, and nothing is presented as a genre it is not |
| A track released this week carries no genre tag but is on a label the listener plays | It competes for that label's dominant genre, and is explained as coming from that label |
| A track released this week has no label, no genre and an unknown artist | It competes only for the leftover places |
| A track released this week was already played by the listener | It may still be offered, but ranks below an equally matching track they have not heard |
| A release is longer than ten minutes (a DJ set) | It is not offered; these feeds are songs only |
| A release has only a year, or only a year and a month, as its release date | It cannot be placed inside a seven-day window and does not appear. It is never rounded to the first of the month, and the date the file was added to the library is never used in its place |
| A release is tagged with a date in the future | It is not offered. A release date comes from a file tag and nobody validates it; without a closed window a track mistagged 2027 would sit at the top of the radar every week, and the funnel would count it as "released this week" |
| Nothing with a known release date arrived in the window | The radar says no recent release matches this listener. It does not widen the window and does not fall back to older music |

### Daily Mix

| Situation | Observable outcome |
|---|---|
| The listener opens the daily mix | It offers tracks released in the last 90 days that they have never played, plus tracks they rated 4 or 5 (superseded by bug report 131: half from the last 12 months, half older -- see [daily-mix-older-tracks](../daily-mix-older-tracks/functional.md)) |
| The listener refreshes it during the day | The order is the same; it changes once per day |
| The shares are divided | By the same profile, the same way, as the radar |

### A listener the server does not know yet

| Situation | Observable outcome |
|---|---|
| A brand new account, and the server has listening history of its own | The feed is built from the server's combined taste, and is labelled as popular on this server — not as based on the listener's own taste |
| The listener has some history but not much | Their own taste and the server's are blended, and the blend shifts towards their own as they listen more |
| Nobody on the server has ever listened to anything | The feed falls back to a configured set of starting genres |
| The listener has fewer than five distinct listens in the last 90 days and the feed shows their own profile anyway | Never happens — that is what the blend is for |

### Failure and staleness

| Situation | Observable outcome |
|---|---|
| The nightly build of a feed fails | The previous day's feed is still shown, marked stale; an error is not presented as an empty feed |
| The feed has never been built for this listener | The feed reports that it is still being prepared |
| A track in a stored feed can no longer be played | It is dropped, and the gap is not filled with an unrelated track |

## Scenarios

These are the flows above in the repository's Gherkin style, kept here because they are what was
actually agreed. They are design confirmation, not yet executable tests.

```gherkin
Feature: A listen counts once, at its deepest genre
  Uptempo is a subgenre of hardcore, so an uptempo track carries both tags.
  Counted naively, every uptempo listen also feeds hardcore, hardcore wins by
  construction, and the profile says "you like hardcore" about a listener who
  has never chosen a plain hardcore track in their life.

  Background:
    Given "Uptempo" is a subgenre of "Hardcore"
    And a listener who played 10 tracks tagged "Uptempo, Hardcore"
    And the same listener played 2 tracks tagged only "Hardcore"

  Scenario: The parent genre only gets what is genuinely its own
    When the taste profile is computed
    Then "Uptempo" carries 10 listens
    And "Hardcore" carries 2 listens
    And the profile does not claim the listener mostly plays hardcore
```

```gherkin
Feature: The profile hands out the slots, recency decides who is in the running
  A release radar is about the week, not about the score. Everything released
  in the window competes; the profile decides how the 30 places are divided.
  Ranking by score alone would fill all 30 with the dominant genre, and a taste
  that is 10% hard techno would never once be visible.

  Background:
    Given a profile of 50% Uptempo, 25% Raw, 10% Hard Techno and a scattered tail
    And 50 tracks were released in the last 7 days
    And the radar offers 30 places

  Scenario: A small share still shows up
    When the radar is built
    Then about 15 places go to Uptempo
    And about 7 places go to Raw
    And about 3 places go to Hard Techno
    And the remaining places go to the tail, rolled up to their parent genre
    And within each share the newest release comes first

  Scenario: A share nobody released this week is given away
    Given no Raw track was released in the last 7 days
    When the radar is built
    Then the 7 Raw places are handed to the next largest share
    And no place is left empty
    And no track is presented as Raw that is not Raw
```

```gherkin
Feature: A fresh rip with no genre tag still lands in the right pile
  New releases are exactly the tracks the tagger has seen least, so the radar
  cannot lean on genre tags. What it can lean on is the label: a label in this
  collection releases one style, and that style is readable from the tracks of
  that label that were tagged earlier.

  Scenario: The label supplies the genre the track lacks
    Given the label "Peacock Records" is uptempo on the tracks already tagged
    And a track released this week on "Peacock Records" carries no genre tag
    When the radar is built
    Then that track competes for the Uptempo places
    And it is explained as coming from a label the listener plays

  Scenario: A SoundCloud rip with no label competes for the leftovers
    Given a track released this week with no label and an unknown artist
    When the radar is built
    Then it competes only for the tail places
```

```gherkin
Feature: Songs, not sets, and the already-heard sinks
  Scenario: A two-hour set does not eat a share
    Given a DJ set of 2 hours was released this week
    When the radar is built
    Then the set is not offered
    And only tracks shorter than 10 minutes compete for the places

  Scenario: A release the listener already heard still counts as a release
    Given a track released this week that the listener already played
    When the radar is built
    Then the track may still be offered
    But it is ranked below an equally matching track they have not heard
```

```gherkin
Feature: An empty radar says it is empty
  Every way this feature fails looks the same from the outside: a short list, or
  no list. A radar that quietly widens its window to fill itself is worse than
  one that admits there was nothing.

  Scenario: Nothing was released that matches
    Given no track with a known release date arrived in the last 7 days
    When the radar is built
    Then the radar reports that no recent release matches the listener
    And it does not fall back to older music
    And it does not fall back to the date the file was added to the library
```

```gherkin
Feature: A listener the server does not know yet borrows the server's taste
  A new account has no history, and a radar built on nothing is either empty or
  random. What the server does have is everyone else's listening, which on this
  installation is the house taste rather than a global average.

  Scenario: A brand new listener gets the server's profile
    Given a listener with no listening history
    And the server has listening history of its own
    When the radar is built
    Then the shares are divided by the server's profile
    And the radar is presented as popular on this server
    And it is not presented as based on the listener's own taste

  Scenario: The listener's own taste takes over as it accumulates
    Given a listener with some listening history but not much
    When the radar is built
    Then their own profile and the server profile are blended
    And the blend shifts towards their own profile as they listen more

  Scenario: A server with no history at all falls back to a configured taste
    Given a server where nobody has listened to anything
    When the radar is built
    Then the shares are divided by the configured starting genres
```

```gherkin
Feature: The daily mix is the same ranker with a wider window
  Scenario: A mix of the unheard and the loved
    Given a profile computed from the last 90 days
    And tracks released in the last 90 days
    When the daily mix is built
    Then it offers tracks the listener has never played
    And tracks the listener rated 4 or 5
    And the shares are divided by the same profile as the radar
    And the order is stable for the whole day
```

## Acceptance Criteria

1. A listener with listening history sees a Release Radar containing only tracks whose release date
   falls inside the configured window, shorter than ten minutes, ordered newest first within each
   genre share.
2. Given a profile whose shares are 50/25/10 with a scattered tail, a 30-place radar allocates
   approximately 15/7/3 places to those genres, and the smallest of the three is present at least
   once whenever the window contains a qualifying track.
3. A track tagged with both a genre and that genre's ancestor contributes its listening weight to
   the deepest genre only.
4. A track released inside the window with no genre tag, on a label whose already-tagged catalogue
   is unambiguously one genre, competes for that genre's places and is explained by its label.
5. A share with no qualifying release is redistributed; the returned list never contains empty
   places, and never labels a track with a genre it does not have.
6. A release date of year-only or year-and-month precision never appears in a seven-day radar, and
   `created_at` never substitutes for a missing release date anywhere in either feed.
7. A radar with no qualifying candidate returns an explicit "no recent release matches" state, which
   the clients render differently from a build failure and from a not-yet-built feed.
8. The daily mix offers only tracks released in the last 90 days that the listener has either never
   played or rated 4 or 5, and returns the same order for the whole day. *(Superseded by bug report
   131: every daily mix except the artist mix is now half recent, half older -- see
   [daily-mix-older-tracks](../daily-mix-older-tracks/functional.md).)*
9. A listener with no listening history receives a feed built from the server's aggregate profile,
   labelled as popular on this server; a listener with partial history receives a blend that shifts
   towards their own profile as their history grows.
10. The listener can see their top artists, labels and genres, and excluding one removes its
    influence from both feeds on the next build.
11. A failed nightly build leaves the previous feed in place, marked stale, rather than returning an
    empty list.
12. Both the web frontend and the mobile app render the same feed content from the same source; they
    do not each compute their own.

## Daily mixes v2 — the spectrum

The request, roughly: five daily mixes that are not all the same — one soft on the spectrum (for
the first listener, euphoric hardstyle), one in the middle (mainstream or raw hardstyle), one hard, and two free.
"If soft/hard is hard to determine, give genres a statistic, a kind of hardness."

### The statistic

`rules_genres` gains `hardness`, 0-100, the same kind of curated fact `genre_tint` is for colour and
`state` is for whether a genre exists at all. It is seeded from a hand-picked anchor list — Deep
House 10 up to Speedcore/Extratone/Splittercore 100, with Hardstyle at 45 and Hardcore at 70 roughly
in the middle — and every other curated genre inherits its nearest anchor ancestor through
`rules_subgenre_hierarchy`, the same graph `deepest()` already walks. A genre with no anchor
ancestor at all stays unscored. Editable afterwards from the genre edit page, exactly where the
hierarchy already is, and a curator's own edit is never silently reset by the seed running again.

**Every anchor value is a proposed default, not a measurement.** Nobody has checked, for instance,
that Uptempo Hardcore at 85 sits where a listener would actually place it by ear next to Zaagtempo
at 88. The seed exists so the feature ships with *something* consistent rather than nothing; see
"Open Questions" below for what still needs checking against real reactions.

### A track's own hardness

Most tracks do not carry a scored genre outright — 28% of the library carries any genre at all, and
coverage is worse on exactly the tracks least likely to be re-tagged soon. A track's hardness is
therefore a fallback chain: its own genres' hardness (weighted by `library_track_genres.weight`),
then its label's mean hardness (over that label's other tracks with a known hardness, at least five
of them so one outlier release cannot decide it), then its primary artist's mean the same way, then
a straight mapping from tempo (`library_track_audio_features.tempo` or `bpm_tag`) — soft below 140,
hard at 200 and above, linear in between. A track that resolves nothing at any step is excluded from
the three spectrum mixes rather than guessed into one; the two free mixes below never filter on
hardness at all, so they are unaffected either way.

### Three mixes on the spectrum, two free

`daily-mix-soft`, `-mid` and `-hard` are the existing daily mix — the same pool of unheard
and highly-rated tracks (90 days until bug report 131; now half from the last year and half older,
see [daily-mix-older-tracks](../daily-mix-older-tracks/functional.md)), the same genre-share bucketing — with the candidate set additionally
narrowed to one third of the hardness spectrum. The two edges (soft/mid and mid/hard) are **fixed
on the genre anchors**, the same 50/75 for every listener, not measured from any one listener's own
history. An earlier version derived them from that listener's own weighted 33rd/67th percentile
instead (with a 40/70 cold-start fallback and a median ± 15 widening below a 15-point gap); measured
on production for one listener right after that version shipped (0.63.0), his own listening put those edges
at 62.5/92.5 — "Zachter" ended up meaning raw hardstyle, techno and mainstream hardstyle (800
candidates), "Middenin" meant uptempo hardcore, bouncy uptempo and zaagtempo (579), and "Harder"
shrank to only terror and speedcore (71 candidates, the release window relaxed to 365 days, 13
places filled from unknown hardness). That is backwards: a listener who plays a lot of one style
must not see that style redefine what "hard" means, because then the person whose taste needs the
spectrum split the least (they already only hear their own style) is exactly the one for whom the
split stops working. Soft/mid/hard describe the music, not the listener; the listener's own taste
still decides *which* tracks within a band a mix picks (`profile.py`'s shares, unchanged), just not
where a band starts. The two edges are exposed as a runtime setting
(`feeds_hardness_edges`, `services/common/config_store.py`) for retuning without a deploy; garbage
or an unset value falls back to 50/75. The listener's own weighted percentiles are still computed
and shown (on the profile view, and in `scripts/feeds_dryrun.py`'s output) as information about
where their own taste sits — they simply no longer decide anything.

If a band still has too few candidates once filtered (fewer than 15), the mix widens its own
90-day window to 365 days, then to no window at all, before giving up on the band as such —
reported so the client can say why a mix looks thin rather than pretending it never happened. If,
even after that, the mix would still come up short of its 30 places, the remaining places are
filled from candidates whose hardness could not be resolved at all, rather than leaving the mix
short or empty: a library with thin genre coverage still gets a full mix, and the response says how
many places were filled this way (`filled_from_unknown`). This is a deliberate second line of
defence, decided after the first version of this shipped and lost tracks on exactly the schema a
CI test seeds: a band that excludes every unscored track can go empty long before "no more window
to widen" is the real problem — genre coverage is 28% of the library, so most tracks start with no
hardness at all.

`daily-mix-artist` and `daily-mix-label` are the two free slots (since bug report 131 the label mix
splits recent/older like the others and counts its labels over the whole library; the artist mix
keeps what follows): the same daily-mix pool, restricted
to one artist or one label chosen from the listener's own top 10 by a hash of their username and
today's date, so it visibly rotates day to day without needing a job to pick it. Only a name with at
least 15 playable songs (a file on disk, unheard or loved, one per song) is ever drawn: when the
drawn name has fewer in the last 90 days its window widens to a year, then to all time, the same
ladder a band uses; when it has fewer even then, the next name in the top 10 is taken; and when no
name in the top 10 qualifies at all, the mix is shown as empty that day rather than with two or
three tracks (bug report 110). The artist mix is not capped at three tracks per artist — every track
in it is by that artist.

`daily-mix` — the slug the car and the phone already call — keeps working exactly as it always has:
the same, unrestricted policy, filtered on nothing about hardness. It is **not** one of the three
spectrum mixes and not an alias of any of them; an early version of this feature aliased it to
`daily-mix-mid` and that meant a track with no scored genre could lose its place on the one slug
already shipped to production, on a server whose tagger has not caught up yet. `GET /api/feeds`
lists it alongside the five new slugs, titled "Klassiek", so a client discovering feeds sees all six
and can explain the difference; nothing already shipped needs to change either way, since the slug's
behaviour has not.

## Open Questions / Not Yet Decided

Nothing below blocks agreement on behavior, but all of it blocks the technical design.

- **Every parameter is a guess until measured.** The seven-day radar window, the 90-day profile
  window, the 30 places, the ten-minute song ceiling, the rating threshold of 4, and the blend ramp
  for a thin profile are all proposed defaults. They must be exposed as configuration, and the
  starting values must come from the measurements below.
- **Measurements required before the technical design.** How many tracks carry a release date with
  day precision, and how many arrive per week at 7/14/30/90 days; genre and label coverage over the
  tracks this listener actually played, rather than over the library; how populated
  `rules_subgenre_hierarchy` is (an absent `Uptempo -> Hardcore` row silently reinstates the
  double-counting this design exists to prevent); how many labels have an unambiguous dominant
  genre; how the rating values are actually distributed; and how many listens exist per source and
  match method.
- **The seven-day window may not be viable.** If day-precision release dates are rare, the radar is
  empty by construction. In that case the decision to reopen is the window (14 or 30 days), not a
  fallback to `created_at`, which was explicitly rejected.
- **An uncurated genre splits the profile, and V1 ships with it.** The feeds count every genre that
  is not blacklisted, which means curated genres *and* ones nobody has ruled on yet. A curated
  "Uptempo Hardcore" and an undecided raw "uptempo" are two different genres to this feature: the
  listener's weight for one style is divided between them, and the raw one — having no place in the
  subgenre hierarchy — cannot roll up into its parent and drops into the leftovers.

  It presents as a **thin profile, never as an error**: the shares look reasonable and the style
  simply gets fewer places than the listening earns. Where it is visible is the profile view and the
  dry run's share table, as the same style appearing twice under two spellings. Fixing it means
  teaching the curation model that the raw name means the curated one, and a wrong entry there
  silently merges two genres that are not the same thing, in every profile built afterwards. That is
  curation work with its own review, so it is deliberately out of scope here; the measurement of how
  much it actually costs comes first.

- **The hardness anchors are still unmeasured.** The anchor list (Deep House 10, Hardstyle 45,
  Terror 95, ...) is a proposed ordering nobody has checked against how listeners here actually rank
  these genres by ear. The band split itself is no longer a per-listener guess — it is fixed at
  50/75 on those same anchors, adjustable via the `feeds_hardness_edges` setting — but the anchors
  underneath it are: `scripts/feeds_dryrun.py --slug daily-mix-soft` is still the tool for judging
  whether a given anchor sits where a listener would place it by ear.
- **Playback identity is unproven.** Both clients play through LMS, which does not know a MuMa
  `track_uid`; the existing bridge between the two is the file path, and that path prefix has broken
  this integration before. This must be demonstrated on a sample before any UI work starts.
- **Deferred deliberately:** DJ sets (possibly their own feed later), more than one daily mix,
  collaborative filtering, audio-similarity or BPM matching, listener-adjustable weights, and any
  discovery of releases that are not already in the library.

## Related Docs

- [`docs/designs/genre-curation/`](../genre-curation/) — the genre state model and
  `rules_subgenre_hierarchy`, which this feature reads and does not extend.
- [`docs/designs/memories/`](../memories/) — the precedent for a server-generated feed rendered by
  both clients.
- [`docs/designs/ratings-scrobbling/`](../ratings-scrobbling/) — where the listening history and the
  ratings this profile is built from come from.
