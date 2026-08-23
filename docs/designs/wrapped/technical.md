# Wrapped Pre-Work — Technical Design

> Implements [functional.md](functional.md). Rationale and production measurements are in
> [research.md](research.md).
>
> Part 1 (listening fidelity) is implemented on this branch. Part 2 (channels) is designed here and
> deliberately **not** implemented yet — it needs sign-off on the model first (AGENTS.md rule 4).

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

## Part 2 — Channels (designed, not implemented)

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

Existing rows are re-derivable from `library_media_files.file_path`, and the followed-channel lists in
`downloads_soundcloud_accounts` / `downloads_youtube_accounts` give the channel names that are already
known to be real. Linking a channel to a label or artist can reuse the label-proposal pattern
(`rules_label_proposals`): propose on strong name equality, confirm by hand.

### Not decided

The link direction rules, the curation UI and the backfill order all need agreement before
implementation starts.

## Related Docs

- [research.md](research.md) — the production measurements this design answers
- [docs/database-design.md](../../database-design.md) — domain model the new tables join
- [docs/designs/ratings-scrobbling/](../ratings-scrobbling/) — the existing scrobble path
- [docs/open-work.md](../../open-work.md) — the deferred folder restructure
