# Product Goal

Why MuMa exists, who it serves, and what it deliberately does not try to be. Every other document
here describes how a part works; this one says what the parts are for. When a proposal cannot be
traced back to a line in this file, that is the signal to argue about it before building it.

## The goal

**Any combination of genre, year, artist, label, festival and rating turns into a playable list.**

That is the whole product. It is what MediaMonkey could do and what streaming services cannot:
"hardstyle from 2012", "hardcore from 2016", an arbitrary cross-section of a collection along
whichever axis matters today. Streaming catalogues offer new or popular, rarely a specific year, and
they carry almost no mixes or live sets at all.

Everything else in this repository is a means to that end. Automated downloading fills the
collection so there is something to filter. The tagger enforces metadata so the filters have
anything to match on. Owning the files is what makes both possible. None of those are the point; a
filter that returns the right tracks is.

Two capabilities follow directly from the goal and are not negotiable:

- **Year cross-sections.** Any year, any genre, on their own or combined.
- **Mixes and live sets as first-class material.** DJ sets, festival recordings and podcasts are not
  a lesser kind of track; for this collection they are often the main event.

## The second pillar: listening without a query

Filtering is the first pillar and the reason the system exists. The second is being a place where
you simply put something on, and where you can look back at what you played.

Radio mode (`docs/radio-mode.md`), news of the hour (`docs/news-mode.md`), Memories and Wrapped all
belong here. They are not scope creep and they are not decoration; they are the half of listening
that does not start with a query. They rank below the filter axes when the two compete for effort,
but they are part of what MuMa is.

## Who it is for

One owner-curator, plus a few passengers who listen.

Curation is deliberately singular: decisions about genres, labels, festivals and tagging rules are
made by one person, and the management UI is built for that person. Multi-user support exists so
others can listen, not so others can curate.

Per-user data is limited to ratings, listening history and playlists. Everything else — the library,
the rules, the curation states — is shared and owned by the curator.

## What "from 2012" means

The year axis resolves differently per kind of material:

| Material | Date used |
|---|---|
| Individual tracks | Release date |
| Released sets and mixes | Release date |
| Live sets | Performance date, falling back to release date |

The fallback is acceptable because for a live set the two dates are usually close enough that a year
filter lands in the same place.

This rule is written down here because it is currently unimplementable and nothing else records the
intent. The library holds a single date column, `release_date`. Whether something is a track, a set
or a live set is not a field at all — it is inferred from the folder a file sits in (`Livesets`,
`Podcasts`, `Top 100`, `Warm Up Mixes`; see `services/tagger/tagger.py`). `SongTypeEnum` looks like
it might carry this distinction but does not: its values are `LABEL`, `YOUTUBE`, `SOUNDCLOUD`,
`TELEGRAM` and `GENERIC`, which describe where a file came from, not what it is.

A performance date is reachable in principle: `rules_festival_editions(festival_id, year, date)`
already stores the real date of each festival edition, so a live set tagged with a festival and a
year can resolve one. That path depends entirely on festival tagging coverage.

## Where it must work

**One definition of a filter, behaving identically in the web UI, on the phone, and in the car.** A
filter built in one place is expected to work in all of them; a filter that only exists in one
client is a filter that does not exist. Voice already covers part of this ("play hardstyle from
2012" parses today, via `services/muma-mobile/core/voice`).

The web UI and the phone carry equal weight — listening happens on both about as much — so neither
is the place a feature is allowed to land alone. A feature that exists in only one of them is not
finished.

The current state works against this. `dynamic_playlists` is a table in the MuMa database, written
and read through the `music_manager` API and edited in the web management UI
(`services/frontend/src/lib/management/tabs/PlaylistsTab.svelte`). Its `params` column is opaque
text. The C++ playback server does not know the table exists, and neither does the Android client,
so nothing a dynamic playlist defines is reachable over the Subsonic API — which is exactly the path
the phone and the car use.

## How music arrives, and why the library is noisy

Three channels feed the library, and they are not interchangeable.

**The downloaders bring volume.** Acquisition there is subscription-shaped: a SoundCloud or YouTube
channel is added (`downloads_soundcloud_accounts`, `downloads_youtube_accounts`) and everything it
publishes is taken. Nothing is filtered at download time. That is deliberate — missing a release is
worse than storing one you never play, so the collection takes everything and curation happens
afterwards, which is what the tagger's rules and the genre curation states are for. It is also the
direct cause of the two things anyone notices first: the size of the library and the volume of junk
genres arriving with it. Both are the accepted price of not missing anything, not defects.

**The importer brings quality.** Label promo pools arrive as archives with a folder structure that
carries the label and the catalog number, so this is the channel with the best metadata and with
releases that exist nowhere else. Correctness matters more here than anywhere upstream: this is the
material the collection is actually built on, and it is where the `__TODO` label damage landed.

**Telegram brings the live sets.** Rips of Defqon and comparable events are shared there and are not
on YouTube or SoundCloud. It is a small channel by volume and the only source for material the goal
calls non-negotiable, so it is load-bearing despite its size. It is a downloader in code
(`services/downloader/telegram`) and, until now, absent from every document.

## The rules are the source of truth

Neither the file nor the database is authoritative. **The rules are**, and both the tags in the files
and the rows in the database are output derived from them.

The property that makes this work is idempotence: applying the rules twice produces the same result
as applying them once. A rule run is therefore always safe to repeat, and the state of the library
is always explainable by pointing at a rule rather than at the history of what happened to a file.

The consequence is that a manual correction has to become a rule. An edit made directly to a file or
a row, with no rule behind it, is not a correction — it is something the next run will overwrite.
This is what the curation edit pages exist for.

## Ownership of ratings and history

**MuMa is the archive; LMS is the working copy.** Ratings, listens and stats live permanently in the
MuMa database and drive the filters. LMS holds a copy for playback.

The accepted consequence: rebuilding or wiping the LMS database loses the stars in the player, on
the phone included, while MuMa still holds every one of them. Nothing pushes them back today, and
that is a deliberate position rather than an unfinished feature. `docs/architecture/responsibilities.md`
claims MuMa "can re-push" ratings to LMS and
`docs/designs/ratings-scrobbling/functional.md` leaves bidirectional sync as an open question; both
are outdated by this line.

## What the ML analyzer is for

The intended purpose is **automatic genre classification** — closing the coverage gap on the axis
that matters most, without hand-curating every unknown genre.

It has not got there, and since 2026-09-25 it is deprecated and disabled, with the code kept
([services/ml-analyzer/DEPRECATED.md](../services/ml-analyzer/DEPRECATED.md)). What it did
extract was BPM, loudness, spectral centroid and duration (`services/ml-analyzer/`); the genre and subgenre models sketched in `docs/machine-learning.md` were
never built, because the training and inference cost in RAM and CPU stalled the work. There is a
learning-exercise element to the service as well, and that is fine.

Two consequences worth being explicit about: nothing in the product currently depends on ML output
beyond BPM, and reviving genre classification is a hardware question before it is a modelling
question.

On hardware generally: buying capacity is allowed when the price is reasonable, and at current
prices it is not. The working assumption is therefore what already exists. Both this and the backup
gap below are blocked on that, rather than rejected.

## Risk order

Not all failures are equal here, and the ordering is not the obvious one.

**Irreversible loss comes first.** Music files, ratings and listening history cannot be recreated. A
destructive action on the library, a rating table wiped by a rebuild, a listen that was never
written down — these are permanent, and no amount of later work recovers them.

**Runtime failures come second.** An incomplete playlist, a crashed app, a playback server that will
not start: annoying, visible, and fixed within a day.

The consequence is that the writing services — tagger, downloader, importer, scanner — carry a
heavier burden of proof than the playback path. They touch files and tags directly and their
mistakes are silent and permanent. The playback server is replaceable; the files are not.

**The largest risk in this document currently has no mitigation.** The database is well covered:
`tools/db_backup.py` dumps, verifies and prunes, three systemd timers in `scripts/backup/systemd/`
run the nightly dump, a staleness check and a weekly restore drill, and `scripts/restore_db.sh`
brings it back. The music itself — over 6 TB — is not backed up anywhere. What exists as raw capacity is a 5 TB external disk and an
offline 27 TB NAS that could go offsite; what has blocked it is the assumption that a copy needs
version history, which at this size is expensive.

That assumption is worth re-examining before the problem is treated as unsolvable. A music
collection is close to append-only, so per-file version history is not what protects it; what
protects it is a mirror that does not blindly replay deletions, plus snapshots on the receiving side
(btrfs or zfs), which cost only what actually changes. That is a design in its own right and is not
decided here.

## Non-goals

Hard, and not open for reconsideration without changing this document:

- **Anything social.** Public profiles, shared playlists, following other listeners, activity feeds.
  The product is effectively single-user; none of this serves filtering a personal collection.
- **Building a player.** LMS and the Ultrasonic-derived mobile client are an adequate base. Playback
  is a commodity and the engine is expected to be replaceable; investing in streaming internals is
  effort spent away from the goal.

## Soft goals

Desirable, never blocking:

- **A complete collection.** More of the genre is better, but no filter result is wrong because
  something was never downloaded.
- **Perfect metadata.** Good enough is good enough. The axes that get filtered — genre, year,
  artist, label, festival, rating — need to be right; the rest can stay imperfect indefinitely.
  There is deliberately no coverage percentage to hit. As much filled in as possible is the
  ambition, a filter that misses something is not a failure, and whether a result feels right is
  judged rather than measured. That is consistent with the risk order: an incomplete list is a
  runtime problem, not a permanent one.

## Phase 2: deliberately open

Statistics-driven mixes in the style Spotify does well: daily mixes, a release radar, "not heard in
a long time", surfacing favourites. The appeal is a random-but-familiar mix drawn from material you
already like.

The direction is agreed. The contents are not, and are intentionally left undecided here rather than
guessed at. Candidate material is catalogued in `docs/designs/wrapped/research.md` and the research
note on daily mixes; what any of it becomes is a later design.

Phase 1 is the axis list above: genre, year, artist, label, festival, rating. BPM is unplaced —
the ML analyzer produced it for part of the library (deprecated since 2026-09-25, so new tracks
get none) and filtering on it is clearly useful ("uptempo above 190"), but
it was not named as a phase 1 axis. Treat it as available rather than required.

## What the goal implies about today's state

Five gaps sit between the current system and the goal as stated. They are listed here because the
goal makes them load-bearing, not because they are new.

- **Form is not a field.** Track, set and live set are inferred from folder names, so no filter can
  ask for one and exclude the others.
- **There is no performance-date path.** `release_date` is the only date column; the live-set rule
  above cannot be applied.
- **The release-date backfill has not been run against production.**
  `scripts/backfill_release_dates.py` exists and its design is in
  `docs/superpowers/specs/2026-08-17-release-date-precision-design.md`; the run itself is not
  recorded as done, and file ACLs on the NAS blocked it when attempted. The year axis is only as
  good as this coverage.
- **Festival coverage is partial.** The performance-date fallback and every festival filter depend
  on sets carrying a festival tag, and a large share of them do not. Lineups are hand-maintained by
  decision (`docs/festival-lineups.md` and the festival rules tables), so coverage grows by hand.
- **Dynamic playlists do not reach the phone or the car.** See "Where it must work" above.
