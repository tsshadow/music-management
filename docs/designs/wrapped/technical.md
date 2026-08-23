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

## Related Docs

- [research.md](research.md) — the production measurements this design answers
- [docs/database-design.md](../../database-design.md) — domain model the new tables join
- [docs/designs/ratings-scrobbling/](../ratings-scrobbling/) — the existing scrobble path
- [docs/open-work.md](../../open-work.md) — the deferred folder restructure
