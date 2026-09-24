# Wrapped Pre-Work — Technical Design

> Implements [functional.md](functional.md). Rationale and production measurements are in
> [research.md](research.md).
>
> Part 1 (listening fidelity) and Part 2 (channels) are both implemented. Part 3 — the physical
> folder restructure — is the one piece that moves files on disk and is tracked separately.

## Part 1 — Listening fidelity

### Data Model

`scrobble_listens` and `scrobble_unmatched_listens` each gain one column:

| Column | Type | Meaning |
|---|---|---|
| `played_secs` | `INT UNSIGNED NULL` | Seconds actually played. `NULL` means the client did not report it — every row written before this change, and any client that has not been updated. |

`source` stays `VARCHAR(50)` and changes meaning rather than shape. It carried the constant `'lms'`
for anything played through the server; it now carries where the play happened:

| Value | Origin |
|---|---|
| `frontend` | The Svelte web player (Subsonic client `spotify`) |
| `mobile` | MuMa Mobile, phone (Subsonic client `Ultrasonic`) |
| `auto` | MuMa Mobile while the phone is connected to the car |
| `lms-web` | The legacy Wt interface |
| `listenbrainz` | Imported from ListenBrainz (unchanged) |
| `manual` | API call with no origin given (unchanged default) |
| `lms` | Historical rows written before this change. Not produced any more. |

Old values are not migrated. A 2026 Wrapped reads `source` for the months after this ships and treats
`lms` as "unknown origin"; per functional.md this is accepted.

Migration: `migrate_v12_listen_played_secs.sql`, plus the same columns added defensively at startup in
`scrobbler.init_db` using the existing `SHOW COLUMNS` / `ALTER TABLE` idiom (`rbac.py:107`), so a
stack that never runs the SQL still self-heals.

### API Contract

**`POST /api/scrobble/event`** — two optional additions, no removals:

```jsonc
{
  "artist_name": "…",       // unchanged, required
  "track_title": "…",       // unchanged, required
  "username": "…",          // unchanged, required
  "listened_at": 1755939600,// unchanged, optional
  "source": "mobile",       // widened vocabulary, still optional, still defaults to "manual"
  "played_secs": 247        // NEW, optional, seconds actually played
}
```

Backwards compatible: a client that sends neither field behaves exactly as before. `played_secs` is
ignored when non-positive.

**`GET /rest/scrobble`** (OpenSubsonic, served by LMS) — two optional non-standard parameters:

| Parameter | Meaning |
|---|---|
| `playedSeconds` | Seconds actually played for this submission |
| `source` | Origin override; when absent the server derives it from the standard `c=` client parameter |

Both are optional and unknown to other Subsonic clients, which simply never send them. The mapping
from `c=` to a source is the fallback path: `spotify` → `frontend`, `Ultrasonic` → `mobile`, anything
else → the client string itself, lowercased.

### Internal changes (LMS, C++)

The played duration already reaches the backend and is discarded at
`MusicManagementBackend.cpp:70` (`(void)duration;`). Three changes:

1. `IScrobblingService::listenFinished` and `addTimedListen` take an optional origin alongside the
   duration they already take, so an entry point can say where the play happened. Defaulted, so
   existing callers compile unchanged.
2. `MusicManagementBackend::sendScrobble` writes `played_secs` and the real `source` into the payload
   instead of dropping the duration and hardcoding `"lms"`.
3. `handleScrobble` (`MediaAnnotation.cpp:176`) reads `playedSeconds` and `source`, falls back to
   deriving the origin from `c=`, and passes both down. The Wt UI path
   (`LmsApplication.cpp:532`) passes `lms-web`.

### Internal changes (MuMa Mobile, Kotlin)

Today a submission only fires on `MEDIA_ITEM_TRANSITION_REASON_AUTO` — the track ended by itself —
and on `STATE_ENDED` (`MediaPlayerManager.kt:133`, `:290`). A manual skip submits nothing, which
removes exactly the long sets that dominate this collection.

- Submit on every media item transition, not only the automatic one, and on player release.
- Attach the played position at the moment of the transition. Below a small threshold (5 s, matching
  the server's own ignore rule in `InternalBackend.cpp:43`) submit nothing: a glance is not a listen.
- Report `source` as `auto` when car presence is active (`CarModeSession`), `mobile` otherwise.

### Cross-App Impact

Per AGENTS.md rule 7 all consumers change together in this branch:

| App | Change |
|---|---|
| `music_manager` | Accepts and stores `played_secs`; wider `source` vocabulary |
| `music-management-server` (LMS) | Forwards played duration and origin; reads the two new Subsonic parameters |
| `muma-mobile` | Submits on skip, sends played seconds and `mobile`/`auto` |
| `frontend` | Sends `source=frontend` on its scrobble calls |

No breaking change: every new field is optional in both directions, and readers tolerate `NULL`.

### Technical Acceptance Criteria

1. `POST /api/scrobble/event` with `played_secs` stores it on the matched row; without it stores
   `NULL`; with a non-positive value stores `NULL`.
2. The same holds for the unmatched table.
3. `source` is persisted verbatim from the request and defaults to `manual`.
4. `init_db` adds both columns when they are missing and is a no-op when they are present.
5. A mobile skip after more than 5 seconds produces exactly one submission carrying the played
   position; a skip under 5 seconds produces none.
6. Existing scrobble tests keep passing unchanged, proving old clients still work.

## Part 2 — Channels

### The problem

`library_track_labels` currently receives the acquisition root of a file's path as if it were a
label, which is why `/api/analytics/top-labels` leads with `Soundcloud` (132.037), `Youtube`
(30.779), `Telegram` (1.556) and `__TODO` (1.243) before the first real label (Dirty Workz, 2.299).

### Proposed model

A channel is not a label and not an artist, but it usually *is* one of them wearing a platform's
clothes. Hence a table of its own with an optional link in both directions:

```
channels
  id
  platform          ENUM('soundcloud','youtube','telegram')   -- kept separate, per decision
  name                                                        -- as it appears on the platform
  normalized_name
  label_id          -> library_labels.id   NULL
  artist_id         -> library_artists.id  NULL
  UNIQUE (platform, normalized_name)

library_track_channels
  track_id -> library_tracks.id
  channel_id -> channels.id
  PRIMARY KEY (track_id, channel_id)
```

Platforms stay split, so `channels/soundcloud/dirty workz` and `channels/youtube/dirty workz` are two
rows. They converge through `label_id`: both point at the one `Dirty Workz` label, which is what makes
"your label of the year" able to count a SoundCloud upload and a YouTube upload as the same label
without pretending the two channels are one channel.

Where a channel is a person rather than an imprint, `artist_id` carries it instead. Whether both may
be set at once is an open question in functional.md.

### Tagger and scanner

The acquisition roots (`Soundcloud`, `Youtube`, `Telegram`) stop being read as labels and start being
read as channel platforms: the next path segment is the channel name. `__TODO` and `__Free&none` stop
producing a label at all — no label is better than a false one.

This is a classification change, not a file move: nothing on disk has to move for the label chart to
become correct. The physical restructure remains a separate, later, breaking change.

### Backfill

`scripts/backfill_channels.py`, which needs no rescan: it reads every `library_media_files.file_path`,
derives the channel, creates it and links the track, then deletes the track-label links pointing at a
non-label and finally the label rows themselves. It has a `--dry-run` that writes nothing, and it is
idempotent — inserts go through unique keys and the deletes are filtered by name, so a second run
finds nothing to do.

Automatically *linking* a channel to a label or artist is deliberately not part of it. That can reuse
the label-proposal pattern (`rules_label_proposals`) later: propose on strong name equality, confirm
by hand.

### Decisions taken

- **A channel may point at a label and an artist at once.** Both columns are nullable and
  independent. An artist who runs their own imprint is a real case, and forcing a choice would
  either lose one of the two facts or invent a rule that has to be undone later.
- **A channel starts out pointing at neither.** A scan records that the channel exists; deciding
  what it *is* belongs to a person. Nothing depends on the link being present, so an unlinked
  channel is a complete row, not a half-finished one.
- **Classification is read from the path, not from the tag.** `<music root>/Soundcloud/<channel>/…`
  is what the downloader wrote, so 160.000 files are classified correctly without retagging one of
  them. The publisher tag is left alone: it records where the file came from, which is true — the
  database simply stops calling that a label.

### Technical Acceptance Criteria

1. A publisher of `Soundcloud`, `Youtube`, `Telegram`, `__TODO` or `__Free&none` — in any casing —
   creates no label row and no track-label link.
2. A file under a platform folder creates a channel for the account directly below it, and links
   the track to it.
3. A file with no platform folder in its path creates no channel.
4. The same account name on two platforms is two channel rows, not one.
5. `scripts/backfill_channels.py --dry-run` reports the change without writing; without the flag it
   creates the channels and links, deletes the non-label track links, and deletes the non-label rows
   from `library_labels`.
6. Re-running the backfill changes nothing further.

## Part 3 — The folder restructure

### The layout

| From | To |
|---|---|
| `/mnt/music/EPs/<label>/<release>` | `/mnt/music/labels/<label>/<release>` |
| `/mnt/music/EPs/__Free&None/…` | `/mnt/music/songs/…` |
| `/mnt/music/EPs/__TODO/…` | `/mnt/music/import/…` |
| `/mnt/music/Soundcloud/<channel>` | `/mnt/music/channels/soundcloud/<channel>` |
| `/mnt/music/Youtube/<channel>` | `/mnt/music/channels/youtube/<channel>` |

`EPs` held three unrelated things: releases on a label, releases on none, and the intake pile. Only
the first is a label tree, which is why the other two kept appearing in the label chart. Splitting
them is what makes "the folder above a release is its label" true rather than nearly true.

It is **five directory renames, not 326.480 file moves** — every move stays inside one mount, so
each is a metadata operation, and `--revert` undoes it just as cheaply.

### What moves with it

- `library_media_files.file_path` **and** `file_path_hash`. The hash is the sha256 of the path, so
  both have to change together or the scanner treats every file as new.
- `tagger_processed_files.filepath`, so nothing is needlessly re-tagged.
- `eps_folder_path` and `import_folder_path`, which the tagger anchors on.

### What does not move with it

- **Ratings.** `rating_tracks.entity_id` is `library_tracks.track_uid`, derived from title, duration
  and primary artist — not from the path. A move cannot lose a rating. (An earlier note in this
  repository claimed the opposite; it was wrong.)
- **Listens.** `scrobble_listens.track_id` points at `library_tracks.id`, also path-independent.
- **File contents.** Nothing inside a file is rewritten.

### The trap the restructure sets

The tagger derives a label from the folders above a track. Move `__Free&None` to `/mnt/music/songs/`
and the naive answer becomes "every track in it is on a label called *songs*" — the exact pollution
Part 2 removes. `channels.path_can_carry_a_label` refuses a label for anything under a non-label root
or a platform folder, so both layouts stay correct while the move happens.

### Why it cannot be run from a developer machine alone

Every path setting reaches the worker containers through production's `.env`, as
the `x-environment-paths` and `x-environment-downloader` anchors of `docker/docker-compose.yml`
show — not through the API config store. Renaming the
folders without changing those first leaves the workers reading and writing paths that no longer
exist: the downloaders simply recreate `/mnt/music/Soundcloud`, and the tagger finds an empty intake.

### Running it

`scripts/prod-restructure-music.sh` does the whole sequence on the production host, as root:

```bash
bash scripts/prod-restructure-music.sh --dry-run   # checks everything, changes nothing
bash scripts/prod-restructure-music.sh --apply
bash scripts/prod-restructure-music.sh --revert --dry-run
```

It discovers the stack rather than hardcoding it — the database container by image, the containers to
stop by which ones actually have `/mnt/music` mounted, and the `.env` from the compose labels (the
compose files sit in a subdirectory of the checkout while `.env` sits at its root, so the parent is
checked too). It stops those containers, renames, rewrites, edits `.env`, and starts back exactly
what it stopped — from an `EXIT` trap, so the stack comes back up even if a step fails.

Two details it gets right that a hand-written `mv` would not:

- **The hash check.** `file_path_hash` is a sha256 written by Python; the script recomputes it with
  MariaDB's `SHA2()`. Before touching anything it verifies the two agree on rows that already exist,
  and refuses if they do not — otherwise the column would fill with values the scanner does not
  recognise and every file would look new.
- **`LEFT(...)`, not `LIKE`.** `__Free&None` contains underscores, which are `LIKE` wildcards:
  `LIKE '/mnt/music/EPs/__Free&None/%'` would also match `/mnt/music/EPs/XXFree&None/…`.

`scripts/restructure_music_folders.py` is the same operation for a machine that has the Python
environment but not the containers.

Afterwards, two things that are not optional:

1. **Full LMS rescan.** It keys its own library on paths, and every path just changed.
2. **Update the `PROD_ENV_FILE` CI/CD variable.** Production's `.env` is rewritten from it on every
   deploy (`scripts/ci-deploy.sh`), so without this the next deploy restores the old paths.

## Related Docs

- [research.md](research.md) — the production measurements this design answers
- [docs/database-design.md](../../database-design.md) — domain model the new tables join
- [docs/designs/ratings-scrobbling/](../ratings-scrobbling/) — the existing scrobble path
- [docs/open-work.md](../../open-work.md) — the deferred folder restructure
